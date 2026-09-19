"""
Domain events → the shared client timeline.

Every module calls `emit()` when something a practice would want to see on the client
record happens. The CRM renders the result; the module owns the meaning. This is the
in-process seam that later grows an outbox + subscribers (notifications, webhooks) in M4 —
the signature stays the same.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.crm import TimelineEvent


def emit(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    module_key: str,
    kind: str,
    summary: str,
    client_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
    actor_membership_id: uuid.UUID | None = None,
    actor_label: str | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
) -> TimelineEvent:
    ev = TimelineEvent(
        tenant_id=tenant_id, client_id=client_id, module_key=module_key, kind=kind, summary=summary[:500],
        detail=detail or {}, actor_membership_id=actor_membership_id,
        actor_label=(actor_label or ("Staff" if actor_membership_id else "System"))[:120],
        ref_type=ref_type, ref_id=str(ref_id) if ref_id else None, occurred_at=utcnow(),
    )
    db.add(ev)
    db.flush()
    return ev
