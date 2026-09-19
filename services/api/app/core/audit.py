from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.core.tenancy import platform_scope
from app.models.audit import AuditEvent

GENESIS = "0" * 64


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def record(
    db: Session,
    *,
    action: str,
    actor_user_id: uuid.UUID | None,
    tenant_id: uuid.UUID | None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
) -> AuditEvent:
    """Append one event, chaining onto the last. Flushes so the chain order is committed order."""
    with platform_scope():
        last = db.execute(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)).scalar_one_or_none()
    prev = last or GENESIS
    now = utcnow()
    body = {
        "tenant_id": str(tenant_id) if tenant_id else None,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "detail": detail or {},
        "created_at": now.isoformat(),
    }
    h = hashlib.sha256((prev + _canonical(body)).encode()).hexdigest()
    ev = AuditEvent(
        tenant_id=tenant_id, actor_user_id=actor_user_id, action=action, target_type=target_type,
        target_id=target_id, detail=detail or {}, ip=ip, prev_hash=prev, hash=h, created_at=now,
    )
    db.add(ev)
    db.flush()
    return ev


def verify_chain(db: Session) -> dict[str, Any]:
    """Walk the whole chain; report ok or the first break."""
    with platform_scope():
        rows = db.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars().all()
    prev = GENESIS
    for r in rows:
        body = {
            "tenant_id": str(r.tenant_id) if r.tenant_id else None,
            "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None,
            "action": r.action, "target_type": r.target_type, "target_id": r.target_id,
            "detail": r.detail or {}, "created_at": r.created_at.isoformat(),
        }
        expect = hashlib.sha256((prev + _canonical(body)).encode()).hexdigest()
        if r.prev_hash != prev or r.hash != expect:
            return {"ok": False, "events": len(rows), "first_break_id": r.id}
        prev = r.hash
    return {"ok": True, "events": len(rows), "head": prev}
