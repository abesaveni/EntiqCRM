"""
Domain events → the shared client timeline, plus in-process subscribers.

Every module calls `emit()` when something a practice would want to see on the client
record happens. The CRM renders the result; the module owns the meaning. Subscribers
(notifications, later webhooks) run synchronously inside the same transaction, so a
notification never exists for an action that rolled back. `subscribe()` takes a glob
over the event kind, e.g. "task.*" or "agreement.completed".
"""
from __future__ import annotations

import fnmatch
import logging
import uuid
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.crm import TimelineEvent

log = logging.getLogger("entiq.events")
Handler = Callable[[Session, TimelineEvent], None]
_subscribers: list[tuple[str, Handler]] = []


def subscribe(kind_glob: str, handler: Handler) -> None:
    if (kind_glob, handler) not in _subscribers:
        _subscribers.append((kind_glob, handler))


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
    for pattern, handler in _subscribers:
        if fnmatch.fnmatch(kind, pattern):
            try:
                handler(db, ev)
            except Exception:  # noqa: BLE001 — a subscriber must never break the originating action
                log.exception("event subscriber failed for %s", kind)
    return ev
