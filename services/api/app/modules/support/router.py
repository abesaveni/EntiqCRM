"""EnTIQ Support: tenant side under /hq/support (any member), operator side under /control/support (operators only)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import events, mailer
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, get_principal, require_operator, require_writable
from app.core.security import utcnow
from app.core.tenancy import platform_scope
from app.models.identity import Membership, User
from app.models.tenant import Tenant
from app.modules.support.models import CATEGORIES, PRIORITIES, SLA, TICKET_STATUSES, SupportComment, SupportTicket
from app.notify import templates
from app.services import notify_service

tenant_router = APIRouter(prefix="/hq/support", tags=["support"])
operator_router = APIRouter(prefix="/control/support", tags=["control-support"])


# ------------------------------------------------------------------ schemas
class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=5, max_length=8000)
    category: Literal["question", "problem", "billing", "feature", "onboarding", "security"] = "question"
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    module_key: str | None = Field(default=None, max_length=32)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    internal: bool = False


class StatusIn(BaseModel):
    status: Literal["open", "pending", "resolved", "closed"]
    satisfaction: int | None = Field(default=None, ge=1, le=5)


class AssignIn(BaseModel):
    operator_user_id: uuid.UUID | None


class PriorityIn(BaseModel):
    priority: Literal["low", "medium", "high", "urgent"]


class CommentOut(BaseModel):
    id: uuid.UUID
    author_name: str
    is_operator: bool
    internal: bool
    body: str
    created_at: datetime


class TicketOut(BaseModel):
    id: uuid.UUID
    number: int
    tenant_id: uuid.UUID
    practice_name: str | None = None
    subject: str
    body: str
    category: str
    priority: str
    status: str
    module_key: str | None
    created_by_name: str | None
    assigned_operator_name: str | None
    first_response_due_at: datetime | None
    resolution_due_at: datetime | None
    first_response_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    sla_breached: bool
    sla_state: str            # ok · at_risk · breached · met
    satisfaction: int | None
    comment_count: int
    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketOut):
    comments: list[CommentOut]


class QueueStats(BaseModel):
    open: int
    pending: int
    unassigned: int
    breached: int
    at_risk: int
    resolved_7d: int
    median_first_response_minutes: float | None
    by_category: dict[str, int]


# ------------------------------------------------------------------ helpers
def _sla_state(t: SupportTicket, now: datetime) -> str:
    if t.status in ("resolved", "closed"):
        return "breached" if t.sla_breached else "met"
    due = t.first_response_due_at if t.first_response_at is None else t.resolution_due_at
    if due is None:
        return "ok"
    if now > due:
        return "breached"
    total = (t.resolution_due_at - t.created_at).total_seconds() if t.first_response_at else (t.first_response_due_at - t.created_at).total_seconds()
    return "at_risk" if (due - now).total_seconds() < max(total * 0.25, 900) else "ok"


def _out(db: Session, t: SupportTicket, *, include_internal: bool, names: dict[uuid.UUID, str] | None = None, practices: dict | None = None) -> TicketDetail:
    now = utcnow()
    names = names if names is not None else _user_names(db, {t.created_by_user_id, t.assigned_operator_id})
    comments = [CommentOut(id=c.id, author_name=c.author_name, is_operator=c.is_operator, internal=c.internal, body=c.body, created_at=c.created_at) for c in t.comments if include_internal or not c.internal]
    return TicketDetail(id=t.id, number=t.number, tenant_id=t.tenant_id, practice_name=(practices or {}).get(t.tenant_id), subject=t.subject, body=t.body, category=t.category, priority=t.priority, status=t.status, module_key=t.module_key,
                        created_by_name=names.get(t.created_by_user_id), assigned_operator_name=names.get(t.assigned_operator_id), first_response_due_at=t.first_response_due_at, resolution_due_at=t.resolution_due_at,
                        first_response_at=t.first_response_at, resolved_at=t.resolved_at, closed_at=t.closed_at, sla_breached=t.sla_breached or _sla_state(t, now) == "breached", sla_state=_sla_state(t, now), satisfaction=t.satisfaction,
                        comment_count=len(comments), created_at=t.created_at, updated_at=t.updated_at, comments=comments)


def _user_names(db: Session, ids: set) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    with platform_scope():
        return {u.id: u.full_name for u in db.execute(select(User).where(User.id.in_(ids))).scalars()}


def _next_number(db: Session) -> int:
    with platform_scope():
        return (db.execute(select(func.max(SupportTicket.number))).scalar_one() or 1000) + 1


def _tenant_ticket(db: Session, ticket_id: uuid.UUID) -> SupportTicket:
    t = db.get(SupportTicket, ticket_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "ticket_not_found"})
    return t


# ------------------------------------------------------------------ tenant side
@tenant_router.get("", response_model=list[TicketOut])
def my_tickets(status_: str | None = Query(None, alias="status"), p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    stmt = select(SupportTicket)
    if status_:
        stmt = stmt.where(SupportTicket.status == status_)
    rows = db.execute(stmt.order_by(SupportTicket.updated_at.desc())).scalars().all()
    names = _user_names(db, {r.created_by_user_id for r in rows} | {r.assigned_operator_id for r in rows})
    return [_out(db, r, include_internal=False, names=names) for r in rows]


@tenant_router.post("", response_model=TicketDetail, status_code=status.HTTP_201_CREATED)
def raise_ticket(body: TicketIn, p: Principal = Depends(get_principal), _w: Principal = Depends(require_writable), db: Session = Depends(get_db)):
    now = utcnow()
    fr, res = SLA[body.priority]
    t = SupportTicket(tenant_id=p.tenant.id, number=_next_number(db), subject=body.subject.strip(), body=body.body.strip(), category=body.category, priority=body.priority, module_key=body.module_key,
                      created_by_membership_id=p.membership.id, created_by_user_id=p.user.id, first_response_due_at=now + timedelta(minutes=fr), resolution_due_at=now + timedelta(minutes=res))
    db.add(t)
    db.flush()
    subject, text, html = templates.support_ack(name=p.user.full_name.split()[0], number=t.number, subject=t.subject, priority=t.priority, first_response_hours=round(fr / 60, 1))
    mailer.queue_email(db, tenant_id=p.tenant.id, to=p.user.email, subject=subject, text=text, html=html, template="support_ack", ref_type="support_ticket", ref_id=t.id)
    events.emit(db, tenant_id=p.tenant.id, module_key="hq", kind="support.ticket_raised", summary=f"Support ticket #{t.number} raised: {t.subject}", actor_membership_id=p.membership.id, actor_label=p.user.full_name, ref_type="support_ticket", ref_id=t.id)
    db.commit()
    db.refresh(t)
    return _out(db, t, include_internal=False)


@tenant_router.get("/{ticket_id}", response_model=TicketDetail)
def my_ticket(ticket_id: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return _out(db, _tenant_ticket(db, ticket_id), include_internal=False)


@tenant_router.post("/{ticket_id}/comments", response_model=TicketDetail)
def my_comment(ticket_id: uuid.UUID, body: CommentIn, p: Principal = Depends(get_principal), _w: Principal = Depends(require_writable), db: Session = Depends(get_db)):
    t = _tenant_ticket(db, ticket_id)
    if t.status == "closed":
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "ticket_closed"})
    db.add(SupportComment(tenant_id=t.tenant_id, ticket_id=t.id, author_user_id=p.user.id, author_name=p.user.full_name, is_operator=False, internal=False, body=body.body.strip(), created_at=utcnow()))
    if t.status in ("pending", "resolved"):
        t.status = "open"     # customer replied → back in the queue
    db.commit()
    db.refresh(t)
    return _out(db, t, include_internal=False)


@tenant_router.post("/{ticket_id}/close", response_model=TicketDetail)
def my_close(ticket_id: uuid.UUID, body: StatusIn, p: Principal = Depends(get_principal), _w: Principal = Depends(require_writable), db: Session = Depends(get_db)):
    t = _tenant_ticket(db, ticket_id)
    t.status, t.closed_at, t.satisfaction = "closed", utcnow(), body.satisfaction
    if t.resolved_at is None:
        t.resolved_at = t.closed_at
    db.commit()
    return _out(db, t, include_internal=False)


# ------------------------------------------------------------------ operator side (Control Centre)
def _op_ticket(db: Session, ticket_id: uuid.UUID) -> SupportTicket:
    with platform_scope():
        t = db.get(SupportTicket, ticket_id)
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "ticket_not_found"})
        _ = t.comments   # load inside the bypass
    return t


@operator_router.get("/stats", response_model=QueueStats)
def stats(_p: Principal = Depends(require_operator), db: Session = Depends(get_db)):
    now = utcnow()
    with platform_scope():
        rows = db.execute(select(SupportTicket)).scalars().all()
    open_ = [t for t in rows if t.status == "open"]
    states = {t.id: _sla_state(t, now) for t in rows if t.status in ("open", "pending")}
    fr = [(t.first_response_at - t.created_at).total_seconds() / 60 for t in rows if t.first_response_at]
    fr.sort()
    by_cat: dict[str, int] = {}
    for t in rows:
        if t.status in ("open", "pending"):
            by_cat[t.category] = by_cat.get(t.category, 0) + 1
    return QueueStats(open=len(open_), pending=sum(1 for t in rows if t.status == "pending"), unassigned=sum(1 for t in open_ if not t.assigned_operator_id), breached=sum(1 for s in states.values() if s == "breached"),
                      at_risk=sum(1 for s in states.values() if s == "at_risk"), resolved_7d=sum(1 for t in rows if t.resolved_at and t.resolved_at >= now - timedelta(days=7)),
                      median_first_response_minutes=round(fr[len(fr) // 2], 1) if fr else None, by_category=by_cat)


@operator_router.get("", response_model=list[TicketOut])
def queue(status_: str | None = Query("open", alias="status"), mine: bool = False, p: Principal = Depends(require_operator), db: Session = Depends(get_db)):
    with platform_scope():
        stmt = select(SupportTicket)
        if status_ and status_ != "all":
            stmt = stmt.where(SupportTicket.status == status_)
        if mine:
            stmt = stmt.where(SupportTicket.assigned_operator_id == p.user.id)
        rows = db.execute(stmt.order_by(SupportTicket.status, SupportTicket.priority.desc(), SupportTicket.created_at)).scalars().all()
        practices = {t.id: t.name for t in db.execute(select(Tenant).where(Tenant.id.in_({r.tenant_id for r in rows}))).scalars()} if rows else {}
        for r in rows:
            _ = r.comments
    names = _user_names(db, {r.created_by_user_id for r in rows} | {r.assigned_operator_id for r in rows})
    order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    rows.sort(key=lambda t: (t.status != "open", order.get(t.priority, 9), t.created_at))
    with platform_scope():
        return [_out(db, r, include_internal=True, names=names, practices=practices) for r in rows]


@operator_router.get("/{ticket_id}", response_model=TicketDetail)
def op_ticket(ticket_id: uuid.UUID, _p: Principal = Depends(require_operator), db: Session = Depends(get_db)):
    t = _op_ticket(db, ticket_id)
    with platform_scope():
        practices = {t.tenant_id: db.get(Tenant, t.tenant_id).name}
    with platform_scope():
        return _out(db, t, include_internal=True, practices=practices)


@operator_router.post("/{ticket_id}/comments", response_model=TicketDetail)
def op_comment(ticket_id: uuid.UUID, body: CommentIn, p: Principal = Depends(require_operator), db: Session = Depends(get_db)):
    t = _op_ticket(db, ticket_id)
    now = utcnow()
    with platform_scope():
        db.add(SupportComment(tenant_id=t.tenant_id, ticket_id=t.id, author_user_id=p.user.id, author_name=p.user.full_name, is_operator=True, internal=body.internal, body=body.body.strip(), created_at=now))
        if not body.internal:
            if t.first_response_at is None:
                t.first_response_at = now
                if t.first_response_due_at and now > t.first_response_due_at:
                    t.sla_breached = True
            if t.assigned_operator_id is None:
                t.assigned_operator_id = p.user.id
            if t.status == "open":
                t.status = "pending"
            # tell the practice user who raised it
            if t.created_by_membership_id:
                notify_service.notify(db, tenant_id=t.tenant_id, membership_id=t.created_by_membership_id, kind="support.reply", title=f"EnTIQ Support replied on #{t.number}", body=body.body.strip()[:200], link=f"/hq/support/{t.id}", module_key="hq")
            u = db.get(User, t.created_by_user_id) if t.created_by_user_id else None
            if u:
                subject, text, html = templates.support_reply(name=u.full_name.split()[0], number=t.number, subject=t.subject, author=p.user.full_name, body=body.body.strip(), url=f"{settings.APP_PUBLIC_URL.rstrip('/')}/hq/support/{t.id}")
                mailer.queue_email(db, tenant_id=t.tenant_id, to=u.email, subject=subject, text=text, html=html, template="support_reply", ref_type="support_ticket", ref_id=t.id)
        db.commit()
        db.refresh(t)
        practices = {t.tenant_id: db.get(Tenant, t.tenant_id).name}
    with platform_scope():
        return _out(db, t, include_internal=True, practices=practices)


@operator_router.post("/{ticket_id}/status", response_model=TicketDetail)
def op_status(ticket_id: uuid.UUID, body: StatusIn, p: Principal = Depends(require_operator), db: Session = Depends(get_db)):
    t = _op_ticket(db, ticket_id)
    now = utcnow()
    with platform_scope():
        t.status = body.status
        if body.status == "resolved":
            t.resolved_at = now
            if t.resolution_due_at and now > t.resolution_due_at:
                t.sla_breached = True
            if t.created_by_membership_id:
                notify_service.notify(db, tenant_id=t.tenant_id, membership_id=t.created_by_membership_id, kind="support.resolved", title=f"Ticket #{t.number} resolved", body=t.subject, link=f"/hq/support/{t.id}", module_key="hq")
        elif body.status == "closed":
            t.closed_at = now
            t.resolved_at = t.resolved_at or now
        elif body.status == "open":
            t.resolved_at = t.closed_at = None
        db.commit()
        db.refresh(t)
        practices = {t.tenant_id: db.get(Tenant, t.tenant_id).name}
    with platform_scope():
        return _out(db, t, include_internal=True, practices=practices)


@operator_router.post("/{ticket_id}/assign", response_model=TicketDetail)
def op_assign(ticket_id: uuid.UUID, body: AssignIn, p: Principal = Depends(require_operator), db: Session = Depends(get_db)):
    t = _op_ticket(db, ticket_id)
    with platform_scope():
        if body.operator_user_id:
            u = db.get(User, body.operator_user_id)
            if u is None or not u.is_operator:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "not_an_operator"})
        t.assigned_operator_id = body.operator_user_id
        db.commit()
        db.refresh(t)
        practices = {t.tenant_id: db.get(Tenant, t.tenant_id).name}
    with platform_scope():
        return _out(db, t, include_internal=True, practices=practices)


@operator_router.post("/{ticket_id}/priority", response_model=TicketDetail)
def op_priority(ticket_id: uuid.UUID, body: PriorityIn, p: Principal = Depends(require_operator), db: Session = Depends(get_db)):
    t = _op_ticket(db, ticket_id)
    with platform_scope():
        fr, res = SLA[body.priority]
        t.priority = body.priority
        t.first_response_due_at, t.resolution_due_at = t.created_at + timedelta(minutes=fr), t.created_at + timedelta(minutes=res)
        db.commit()
        db.refresh(t)
        practices = {t.tenant_id: db.get(Tenant, t.tenant_id).name}
    with platform_scope():
        return _out(db, t, include_internal=True, practices=practices)


@operator_router.get("/meta/operators")
def operators(_p: Principal = Depends(require_operator), db: Session = Depends(get_db)):
    with platform_scope():
        return [{"id": str(u.id), "name": u.full_name} for u in db.execute(select(User).where(User.is_operator.is_(True), User.is_active.is_(True)).order_by(User.full_name)).scalars()]


__all__ = ["tenant_router", "operator_router", "TICKET_STATUSES", "PRIORITIES", "CATEGORIES", "Membership"]
