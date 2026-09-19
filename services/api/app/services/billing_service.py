"""
Billing ledger: append-only, hash-chained. Charges are recorded here whether they are real
(Stripe) or simulated (BILLING_MODE=simulate) — the `kind` and `status` say which, so a
simulated charge can never be mistaken for money received.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import utcnow
from app.core.tenancy import platform_scope
from app.models.platform import BillingEvent
from app.modules import registry

GENESIS = "0" * 64


def gst_for(amount_cents: int) -> int:
    return round(amount_cents * settings.GST_RATE_BPS / 10_000)


def indicative_price_cents(module_key: str) -> int | None:
    """Monthly ex-GST price where one has been set. Base plan = BASE_PLAN_PRICE_CENTS; modules from the manifest."""
    if module_key in registry.BASE_BUNDLE:
        return settings.BASE_PLAN_PRICE_CENTS if module_key == "crm" else 0
    m = registry.get_module(module_key)
    from_aud = (m.get("pricing") or {}).get("fromAud")
    return int(round(from_aud * 100)) if from_aud else None


def record(db: Session, *, tenant_id: uuid.UUID, kind: str, module_key: str | None = None, amount_cents: int = 0, status: str = "recorded",
           detail: dict[str, Any] | None = None, stripe_ref: str | None = None) -> BillingEvent:
    with platform_scope():
        last = db.execute(select(BillingEvent.hash).order_by(BillingEvent.id.desc()).limit(1)).scalar_one_or_none()
    prev = last or GENESIS
    gst = gst_for(amount_cents)
    now = utcnow()
    body = {"tenant_id": str(tenant_id), "module_key": module_key, "kind": kind, "amount_cents": amount_cents, "gst_cents": gst, "total_cents": amount_cents + gst,
            "currency": "AUD", "status": status, "detail": detail or {}, "stripe_ref": stripe_ref, "created_at": now.isoformat()}
    h = hashlib.sha256((prev + json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)).encode()).hexdigest()
    ev = BillingEvent(tenant_id=tenant_id, module_key=module_key, kind=kind, amount_cents=amount_cents, gst_cents=gst, total_cents=amount_cents + gst,
                      status=status, detail=detail or {}, stripe_ref=stripe_ref, prev_hash=prev, hash=h, created_at=now)
    db.add(ev)
    db.flush()
    return ev


def verify_chain(db: Session) -> dict[str, Any]:
    with platform_scope():
        rows = db.execute(select(BillingEvent).order_by(BillingEvent.id)).scalars().all()
    prev = GENESIS
    for r in rows:
        body = {"tenant_id": str(r.tenant_id), "module_key": r.module_key, "kind": r.kind, "amount_cents": r.amount_cents, "gst_cents": r.gst_cents, "total_cents": r.total_cents,
                "currency": r.currency, "status": r.status, "detail": r.detail or {}, "stripe_ref": r.stripe_ref, "created_at": r.created_at.isoformat()}
        expect = hashlib.sha256((prev + json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)).encode()).hexdigest()
        if r.prev_hash != prev or r.hash != expect:
            return {"ok": False, "events": len(rows), "first_break_id": r.id}
        prev = r.hash
    return {"ok": True, "events": len(rows), "head": prev}


def events_for(db: Session, tenant_id: uuid.UUID, limit: int = 50) -> list[BillingEvent]:
    return list(db.execute(select(BillingEvent).where(BillingEvent.tenant_id == tenant_id).order_by(BillingEvent.id.desc()).limit(limit)).scalars())
