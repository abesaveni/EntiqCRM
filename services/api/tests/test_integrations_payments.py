"""M8: the integration hub reports what is actually configured, and the trial charge goes through a gateway."""
from datetime import timedelta

from tests.conftest import auth, signup

C = "/api/v1"


def test_integration_hub_reports_real_configuration(client):
    out = signup(client)
    h = auth(out["tokens"])
    rows = {r["key"]: r for r in client.get(f"{C}/integrations", headers=h).json()}
    assert {"didit", "opensanctions", "xero", "stripe", "smtp", "storage", "clamav", "openai"} <= set(rows)
    # the test environment runs everything in simulation, and the hub says so rather than claiming a connection
    assert rows["didit"]["status"] == "simulated" and "DIDIT_API_KEY" in rows["didit"]["missing"]
    assert rows["opensanctions"]["status"] == "simulated" and rows["stripe"]["status"] == "simulated"
    assert "STRIPE_SECRET_KEY" in rows["stripe"]["missing"] and "BILLING_MODE=stripe" in rows["stripe"]["missing"]
    assert rows["xero"]["status"] == "not_connected" and rows["xero"]["scope"] == "practice" and rows["xero"]["configurable_here"] is True
    assert rows["clamav"]["status"] == "attention" and rows["storage"]["status"] == "simulated"
    # used_by only lists modules this practice actually holds
    assert rows["didit"]["used_by"] == [] or set(rows["didit"]["used_by"]) <= {"hq"}
    client.post(f"{C}/subscriptions", headers=h, json={"module_key": "verify"})
    rows = {r["key"]: r for r in client.get(f"{C}/integrations", headers=h).json()}
    assert "verify" in rows["didit"]["used_by"]

    s = client.get(f"{C}/integrations/summary", headers=h).json()
    assert s["simulated"] >= 3 and s["production_ready"] is False and "STRIPE_SECRET_KEY" in s["blocking"]

    # connecting a client ledger shows up as a practice-scoped connection
    client.post(f"{C}/subscriptions", headers=h, json={"module_key": "workpapers"})
    c = client.post(f"{C}/crm/clients", headers=h, json={"name": "Bluegum Pty Ltd", "client_type": "Company"}).json()
    client.post(f"{C}/workpapers/ledger/connect", headers=h, json={"client_id": c["id"]})
    xero = {r["key"]: r for r in client.get(f"{C}/integrations", headers=h).json()}["xero"]
    assert xero["connections"] == 1 and xero["status"] == "simulated" and "simulation driver" in xero["detail"]


def test_trial_conversion_uses_the_payment_gateway(client):
    from app.core.database import SessionLocal
    from app.core.security import utcnow
    from app.jobs import lifecycle
    out = signup(client)
    h = auth(out["tokens"])
    with SessionLocal() as db:
        stats = lifecycle.run(db, now=utcnow() + timedelta(days=16))
    assert stats["activated"] == 1 and stats.get("charge_failed", 0) == 0
    sess = client.get(f"{C}/me", headers=h).json()
    assert sess["tenant"]["status"] == "active"
    ev = [e for e in client.get(f"{C}/billing/events", headers=h).json() if e["kind"].startswith("charge.")]
    assert len(ev) == 1 and ev[0]["kind"] == "charge.simulated" and ev[0]["status"] == "simulated"
    assert ev[0]["detail"]["provider"] == "simulation" and "no money moved" in ev[0]["detail"]["note"]
    assert ev[0]["amount_cents"] == 9900 and ev[0]["total_cents"] == 10890


def test_failed_charge_starts_dunning(client, monkeypatch):
    """With a gateway that declines, the trial does not silently activate: the practice goes past_due and is emailed."""
    from app.core.database import SessionLocal
    from app.core.security import utcnow
    from app.jobs import lifecycle
    from app.services import payments

    out = signup(client)
    h = auth(out["tokens"])

    class Declining:
        name = "stripe"
        def ensure_customer(self, **kw):
            return "cus_test"
        def charge(self, **kw):
            return payments.ChargeResult(ok=False, simulated=False, provider="stripe", status="failed", failure_code="card_declined", failure_message="Your card was declined.")

    monkeypatch.setattr(payments, "gateway", lambda: Declining())
    with SessionLocal() as db:
        stats = lifecycle.run(db, now=utcnow() + timedelta(days=16))
    assert stats["charge_failed"] == 1 and stats["activated"] == 0
    sess = client.get(f"{C}/me", headers=h).json()
    assert sess["tenant"]["status"] == "past_due"
    ev = [e for e in client.get(f"{C}/billing/events", headers=h).json() if e["kind"] == "charge.failed"]
    assert len(ev) == 1 and ev[0]["detail"]["code"] == "card_declined" and ev[0]["status"] == "failed"
    assert any(m["template"] == "payment_failed" for m in client.get(f"{C}/dev/outbound", headers=h).json())
    # the practice is still readable and writable during the grace period
    assert client.get(f"{C}/crm/clients", headers=h).status_code == 200
    assert client.post(f"{C}/crm/clients", headers=h, json={"name": "Still working"}).status_code == 201


def test_billing_ledger_hash_chain_survives_the_charge(client):
    from datetime import timedelta as td
    from app.core.database import SessionLocal
    from app.core.security import utcnow
    from app.jobs import lifecycle
    out = signup(client)
    h = auth(out["tokens"])
    client.post(f"{C}/subscriptions", headers=h, json={"module_key": "verify"})
    with SessionLocal() as db:
        lifecycle.run(db, now=utcnow() + td(days=16))
    # the operator verification endpoint walks the chain
    from app.services import billing_service
    with SessionLocal() as db:
        assert billing_service.verify_chain(db)["ok"] is True
