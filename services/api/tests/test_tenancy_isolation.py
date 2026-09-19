"""The rules that make multi-tenancy safe, tested at the ORM layer AND through the API."""
import pytest
from sqlalchemy import select

from app.core import audit
from app.core.database import SessionLocal
from app.core.tenancy import TenantContextMissing, TenantIsolationError, platform_scope, tenant_scope
from app.models.subscription import TenantSubscription
from tests.conftest import auth, signup


def test_read_filter_isolates_tenants(client):
    a = signup(client, practice="A Co", email="a@a.example")
    b = signup(client, practice="B Co", email="b@b.example")
    client.post("/api/v1/subscriptions", headers=auth(a["tokens"]), json={"module_key": "verify"})
    with SessionLocal() as db:
        with tenant_scope(__import__("uuid").UUID(a["session"]["tenant"]["id"])):
            keys_a = {s.module_key for s in db.execute(select(TenantSubscription)).scalars()}
        with tenant_scope(__import__("uuid").UUID(b["session"]["tenant"]["id"])):
            keys_b = {s.module_key for s in db.execute(select(TenantSubscription)).scalars()}
    assert "verify" in keys_a and "verify" not in keys_b
    # and via the API — B never sees A's rows
    subs_b = {x["module_key"] for x in client.get("/api/v1/subscriptions", headers=auth(b["tokens"])).json()}
    assert subs_b == {"hq", "crm", "billing"}


def test_scoped_query_without_context_fails_closed(client):
    signup(client)
    with SessionLocal() as db:
        with pytest.raises(TenantContextMissing):
            db.execute(select(TenantSubscription)).scalars().all()


def test_write_guard_refuses_cross_tenant_write(client):
    import uuid
    from app.core.security import utcnow
    a = signup(client, practice="A Co", email="a@a.example")
    b = signup(client, practice="B Co", email="b@b.example")
    ta, tb = uuid.UUID(a["session"]["tenant"]["id"]), uuid.UUID(b["session"]["tenant"]["id"])
    with SessionLocal() as db:
        with tenant_scope(ta):
            db.add(TenantSubscription(tenant_id=tb, module_key="sign", status="active", started_at=utcnow()))
            with pytest.raises(TenantIsolationError):
                db.flush()
            db.rollback()
        with tenant_scope(ta):  # tenant_id auto-stamped from context when omitted
            row = TenantSubscription(module_key="academy", status="active", started_at=utcnow())
            db.add(row)
            db.flush()
            assert row.tenant_id == ta
            db.rollback()


def test_token_for_tenant_a_cannot_read_tenant_b(client):
    """The principal decides the tenant. No header or query parameter can change it."""
    a = signup(client, practice="A Co", email="a@a.example")
    b = signup(client, practice="B Co", email="b@b.example")
    r = client.get("/api/v1/tenant", headers={**auth(a["tokens"]), "X-Tenant-Id": b["session"]["tenant"]["id"]}, params={"tenant": b["session"]["tenant"]["slug"]})
    assert r.status_code == 200 and r.json()["name"] == "A Co"


def test_audit_chain_verifies_and_detects_tamper(client):
    out = signup(client)
    h = auth(out["tokens"])
    client.post("/api/v1/subscriptions", headers=h, json={"module_key": "sign"})
    with SessionLocal() as db:
        assert audit.verify_chain(db)["ok"] is True
        with platform_scope():
            from app.models.audit import AuditEvent
            ev = db.execute(select(AuditEvent).order_by(AuditEvent.id).limit(1)).scalar_one()
            ev.detail = {"tampered": True}
            db.commit()
        res = audit.verify_chain(db)
        assert res["ok"] is False and res["first_break_id"] == ev.id


def test_audit_endpoint_is_tenant_scoped(client):
    a = signup(client, practice="A Co", email="a@a.example")
    b = signup(client, practice="B Co", email="b@b.example")
    ev_a = client.get("/api/v1/audit", headers=auth(a["tokens"])).json()
    ev_b = client.get("/api/v1/audit", headers=auth(b["tokens"])).json()
    assert {e["action"] for e in ev_a} == {"tenant.created", "user.signup"}
    assert all(e["detail"].get("name", "A Co") == "A Co" for e in ev_a if e["action"] == "tenant.created")
    assert all(e["detail"].get("name", "B Co") == "B Co" for e in ev_b if e["action"] == "tenant.created")
