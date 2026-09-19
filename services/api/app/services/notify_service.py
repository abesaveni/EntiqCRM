"""In-app notifications + the event subscribers that create them and queue emails."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import events, mailer
from app.core.config import settings
from app.core.security import utcnow
from app.core.tenancy import platform_scope
from app.models.crm import Client, TimelineEvent
from app.models.identity import Membership, User
from app.models.platform import Notification
from app.notify import templates


def notify(db: Session, *, tenant_id: uuid.UUID, membership_id: uuid.UUID, kind: str, title: str, body: str | None = None, link: str | None = None, module_key: str = "hq") -> Notification:
    n = Notification(tenant_id=tenant_id, membership_id=membership_id, kind=kind, title=title[:200], body=(body or "")[:1000] or None, link=link, module_key=module_key, created_at=utcnow())
    db.add(n)
    db.flush()
    return n


def notify_roles(db: Session, *, tenant_id: uuid.UUID, roles: tuple[str, ...], exclude: uuid.UUID | None = None, **kw) -> list[Notification]:
    with platform_scope():
        mids = [mid for (mid,) in db.execute(select(Membership.id).where(Membership.tenant_id == tenant_id, Membership.role.in_(roles), Membership.status == "active")).all()]
    return [notify(db, tenant_id=tenant_id, membership_id=m, **kw) for m in mids if m != exclude]


def unread_count(db: Session, membership_id: uuid.UUID) -> int:
    return db.execute(select(func.count()).select_from(Notification).where(Notification.membership_id == membership_id, Notification.read_at.is_(None))).scalar_one()


def owners(db: Session, tenant_id: uuid.UUID) -> list[tuple[Membership, User]]:
    with platform_scope():
        return db.execute(select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.tenant_id == tenant_id, Membership.role == "owner", Membership.status == "active")).all()


def member_user(db: Session, membership_id: uuid.UUID) -> tuple[Membership, User] | None:
    with platform_scope():
        row = db.execute(select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.id == membership_id)).first()
    return (row[0], row[1]) if row else None


# ------------------------------------------------------------------ subscribers
def _on_task_created(db: Session, ev: TimelineEvent) -> None:
    assignee = ev.detail.get("assignee_membership_id")
    if not assignee or str(assignee) == str(ev.actor_membership_id):
        return
    mid = uuid.UUID(str(assignee))
    client_name = None
    if ev.client_id:
        client_name = db.execute(select(Client.name).where(Client.id == ev.client_id)).scalar_one_or_none()
    title = ev.detail.get("title") or ev.summary.removeprefix("Task: ")
    notify(db, tenant_id=ev.tenant_id, membership_id=mid, kind="task.assigned", title=f"Task assigned: {title}", body=f"For {client_name}" if client_name else None, link="/tasks", module_key="crm")
    mu = member_user(db, mid)
    if mu:
        subject, text, html = templates.task_assigned(name=mu[1].full_name.split()[0], title=title, client_name=client_name, assigned_by=ev.actor_label, app_url=settings.APP_PUBLIC_URL)
        mailer.queue_email(db, tenant_id=ev.tenant_id, to=mu[1].email, subject=subject, text=text, html=html, template="task_assigned", ref_type="task", ref_id=ev.ref_id)


def _on_stage_changed(db: Session, ev: TimelineEvent) -> None:
    owner = ev.detail.get("owner_membership_id")
    if not owner or str(owner) == str(ev.actor_membership_id):
        return
    client_name = db.execute(select(Client.name).where(Client.id == ev.client_id)).scalar_one_or_none() if ev.client_id else None
    notify(db, tenant_id=ev.tenant_id, membership_id=uuid.UUID(str(owner)), kind="stage.changed", title=f"{client_name or 'A client'} moved to {ev.detail.get('to')}", body=ev.summary, link=f"/clients/{ev.client_id}" if ev.client_id else None, module_key="crm")


def _on_import_completed(db: Session, ev: TimelineEvent) -> None:
    notify_roles(db, tenant_id=ev.tenant_id, roles=("owner", "admin"), exclude=ev.actor_membership_id, kind="import.completed", title=ev.summary, link="/clients", module_key="crm")


_registered = False


def register() -> None:
    """Attach subscribers once per process (called from the app lifespan)."""
    global _registered
    if _registered:
        return
    events.subscribe("task.created", _on_task_created)
    events.subscribe("stage.changed", _on_stage_changed)
    events.subscribe("import.completed", _on_import_completed)
    _registered = True
