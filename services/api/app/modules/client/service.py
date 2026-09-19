from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import entitlements, events, mailer
from app.core.config import settings
from app.core.database import bind_tenant
from app.core.security import hash_token, new_opaque_token, utcnow
from app.core.tenancy import platform_scope, set_tenant
from app.models.crm import Client, Contact, TimelineEvent
from app.models.identity import Membership
from app.models.platform import Document
from app.models.tenant import Tenant
from app.modules.client import schemas as S
from app.modules.client.models import PortalLoginToken, PortalMessage, PortalSession
from app.notify import templates
from app.services import notify_service
from app.services.crm_service import member_names

PORTAL_TOKEN_HOURS = 12
# Timeline kinds a client may see about themselves (never internal notes, risk, screening, staff assignment)
CLIENT_VISIBLE_KINDS = ("document.uploaded", "agreement.sent", "agreement.completed", "request.sent", "request.completed", "request.item_reviewed", "job.completed", "onboarding.activated", "stage.changed")


class PortalError(Exception):
    def __init__(self, error: str, message: str | None = None):
        super().__init__(message or error)
        self.error, self.message = error, message or error


# ------------------------------------------------------------------ staff: access management
def portal_contacts(db: Session, client_id: uuid.UUID | None = None) -> list[S.PortalContactOut]:
    stmt = select(Contact).where(Contact.archived_at.is_(None))
    if client_id:
        stmt = stmt.where(Contact.client_id == client_id)
    else:
        stmt = stmt.where(Contact.portal_access.is_(True))
    rows = db.execute(stmt.order_by(Contact.created_at)).scalars().all()
    if not rows:
        return []
    clients = {c.id: c.name for c in db.execute(select(Client).where(Client.id.in_({r.client_id for r in rows}))).scalars()}
    sessions = dict(db.execute(select(PortalSession.contact_id, func.count()).where(PortalSession.contact_id.in_([r.id for r in rows]), PortalSession.revoked.is_(False), PortalSession.expires_at > utcnow()).group_by(PortalSession.contact_id)).all())
    last = dict(db.execute(select(PortalSession.contact_id, func.max(PortalSession.created_at)).where(PortalSession.contact_id.in_([r.id for r in rows])).group_by(PortalSession.contact_id)).all())
    invited = dict(db.execute(select(PortalLoginToken.contact_id, func.max(PortalLoginToken.created_at)).where(PortalLoginToken.contact_id.in_([r.id for r in rows]), PortalLoginToken.purpose == "invite").group_by(PortalLoginToken.contact_id)).all())
    return [S.PortalContactOut(contact_id=r.id, client_id=r.client_id, client_name=clients.get(r.client_id, "—"), name=r.full_name, email=r.email, role=r.role, has_portal_access=r.portal_access, invited_at=invited.get(r.id), last_login_at=last.get(r.id), active_sessions=int(sessions.get(r.id, 0))) for r in rows]


def _login_url(raw: str) -> str:
    return f"{settings.APP_PUBLIC_URL.rstrip('/')}/portal/login/{raw}"


def invite(db: Session, tenant: Tenant, contact: Contact, actor_mid: uuid.UUID, actor_label: str) -> str:
    if not contact.email:
        raise PortalError("no_email", "The contact needs an email address")
    contact.portal_access = True
    raw, h = new_opaque_token()
    db.add(PortalLoginToken(tenant_id=tenant.id, contact_id=contact.id, token_hash=h, purpose="invite", expires_at=utcnow() + timedelta(days=14), created_at=utcnow()))
    c = db.get(Client, contact.client_id)
    url = _login_url(raw)
    subject, text, html = templates.portal_invite(name=contact.first_name, practice=tenant.name, client=c.name, url=url)
    mailer.queue_email(db, tenant_id=tenant.id, to=contact.email, subject=subject, text=text, html=html, template="portal_invite", ref_type="contact", ref_id=contact.id)
    events.emit(db, tenant_id=tenant.id, client_id=contact.client_id, module_key="client", kind="portal.invited", summary=f"{contact.full_name} invited to the client portal", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="contact", ref_id=contact.id)
    db.flush()
    return url


def revoke(db: Session, contact: Contact, actor_mid: uuid.UUID, actor_label: str) -> None:
    contact.portal_access = False
    for s in db.execute(select(PortalSession).where(PortalSession.contact_id == contact.id, PortalSession.revoked.is_(False))).scalars():
        s.revoked = True
    events.emit(db, tenant_id=contact.tenant_id, client_id=contact.client_id, module_key="client", kind="portal.revoked", summary=f"Portal access removed for {contact.full_name}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="contact", ref_id=contact.id)
    db.flush()


def staff_overview(db: Session, tenant_id: uuid.UUID) -> S.StaffOverview:
    since = utcnow() - timedelta(days=30)
    contacts = db.execute(select(Contact).where(Contact.portal_access.is_(True), Contact.archived_at.is_(None))).scalars().all()
    return S.StaffOverview(contacts_with_access=len(contacts), clients_with_access=len({c.client_id for c in contacts}),
                           logins_30d=db.execute(select(func.count()).select_from(PortalSession).where(PortalSession.created_at >= since)).scalar_one(),
                           unread_messages=db.execute(select(func.count()).select_from(PortalMessage).where(PortalMessage.contact_id.is_not(None), PortalMessage.read_by_practice_at.is_(None))).scalar_one(),
                           shared_documents=db.execute(select(func.count()).select_from(Document).where(Document.visible_to_client.is_(True), Document.deleted_at.is_(None))).scalar_one())


# ------------------------------------------------------------------ messages (both sides)
def thread(db: Session, client_id: uuid.UUID, *, for_client: bool) -> list[S.ThreadMessage]:
    rows = db.execute(select(PortalMessage).where(PortalMessage.client_id == client_id).order_by(PortalMessage.created_at)).scalars().all()
    names = member_names(db, {m.membership_id for m in rows})
    contacts = {c.id: c.full_name for c in db.execute(select(Contact).where(Contact.id.in_({m.contact_id for m in rows if m.contact_id}))).scalars()} if any(m.contact_id for m in rows) else {}
    out = []
    for m in rows:
        from_client = m.contact_id is not None
        author = contacts.get(m.contact_id, "Client") if from_client else names.get(m.membership_id, "Practice")
        read = (m.read_by_client_at is not None) if (not from_client) else (m.read_by_practice_at is not None)
        out.append(S.ThreadMessage(id=m.id, from_client=from_client, author=author, body=m.body, created_at=m.created_at, read=read))
    return out


def mark_read(db: Session, client_id: uuid.UUID, *, by_client: bool) -> None:
    now = utcnow()
    for m in db.execute(select(PortalMessage).where(PortalMessage.client_id == client_id)).scalars():
        if by_client and m.membership_id is not None and m.read_by_client_at is None:
            m.read_by_client_at = now
        if not by_client and m.contact_id is not None and m.read_by_practice_at is None:
            m.read_by_practice_at = now
    db.flush()


def post_from_staff(db: Session, tenant: Tenant, client: Client, body: str, actor_mid: uuid.UUID, actor_label: str) -> PortalMessage:
    m = PortalMessage(tenant_id=tenant.id, client_id=client.id, membership_id=actor_mid, body=body.strip(), read_by_practice_at=utcnow())
    db.add(m)
    db.flush()
    for ct in db.execute(select(Contact).where(Contact.client_id == client.id, Contact.portal_access.is_(True), Contact.archived_at.is_(None))).scalars():
        if ct.email:
            subject, text, html = templates.portal_message(name=ct.first_name, practice=tenant.name, author=actor_label, body=body.strip(), url=f"{settings.APP_PUBLIC_URL.rstrip('/')}/portal")
            mailer.queue_email(db, tenant_id=tenant.id, to=ct.email, subject=subject, text=text, html=html, template="portal_message", ref_type="portal_message", ref_id=m.id)
    return m


def post_from_client(db: Session, tenant: Tenant, contact: Contact, body: str) -> PortalMessage:
    m = PortalMessage(tenant_id=tenant.id, client_id=contact.client_id, contact_id=contact.id, body=body.strip(), read_by_client_at=utcnow())
    db.add(m)
    db.flush()
    c = db.get(Client, contact.client_id)
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="client", kind="portal.message", summary=f"Message from {contact.full_name}: {body.strip()[:120]}", actor_label=contact.full_name, ref_type="portal_message", ref_id=m.id)
    targets = [c.owner_membership_id] if c.owner_membership_id else [mm.id for mm in db.execute(select(Membership).where(Membership.tenant_id == tenant.id, Membership.status == "active", Membership.role.in_(["owner", "admin"]))).scalars()]
    for mid in targets:
        notify_service.notify(db, tenant_id=tenant.id, membership_id=mid, kind="portal.message", title=f"Message from {contact.full_name} ({c.name})", body=body.strip()[:200], link=f"/clients/{c.id}", module_key="client")
    return m


# ------------------------------------------------------------------ portal auth
def request_login_link(db: Session, email: str) -> int:
    """Send a magic link to every portal-enabled contact with this email (one per practice). Always returns silently."""
    email = email.strip().lower()
    n = 0
    with platform_scope():
        contacts = db.execute(select(Contact).where(func.lower(Contact.email) == email, Contact.portal_access.is_(True), Contact.archived_at.is_(None))).scalars().all()
        for ct in contacts:
            t = db.get(Tenant, ct.tenant_id)
            try:
                entitlements.check(db, t, "client")
            except entitlements.NotEntitled:
                continue
            c = db.get(Client, ct.client_id)
            raw, h = new_opaque_token()
            db.add(PortalLoginToken(tenant_id=ct.tenant_id, contact_id=ct.id, token_hash=h, purpose="login", expires_at=utcnow() + timedelta(minutes=30), created_at=utcnow()))
            subject, text, html = templates.portal_login(name=ct.first_name, practice=t.name, client=c.name, url=_login_url(raw))
            mailer.queue_email(db, tenant_id=ct.tenant_id, to=ct.email, subject=subject, text=text, html=html, template="portal_login", ref_type="contact", ref_id=ct.id)
            n += 1
    return n


def exchange(db: Session, raw: str, ip: str | None, ua: str | None) -> tuple[str, PortalSession, Tenant, Client, Contact]:
    with platform_scope():
        tok = db.execute(select(PortalLoginToken).where(PortalLoginToken.token_hash == hash_token(raw))).scalar_one_or_none()
        if tok is None or tok.used_at is not None or tok.expires_at < utcnow():
            raise PortalError("invalid_link", "This link is not valid or has expired")
        ct = db.get(Contact, tok.contact_id)
        t = db.get(Tenant, tok.tenant_id)
        c = db.get(Client, ct.client_id) if ct else None
        if ct is None or not ct.portal_access or ct.archived_at is not None or c is None:
            raise PortalError("access_revoked", "Portal access has been removed")
        try:
            entitlements.check(db, t, "client")
        except entitlements.NotEntitled:
            raise PortalError("portal_unavailable", "The practice's client portal is not active")
        tok.used_at = utcnow()
        jti = uuid.uuid4().hex
        exp = utcnow() + timedelta(hours=PORTAL_TOKEN_HOURS)
        db.add(PortalSession(tenant_id=t.id, contact_id=ct.id, jti=jti, user_agent=(ua or "")[:300] or None, ip=ip, created_at=utcnow(), expires_at=exp))
        db.flush()
        token = jwt.encode({"sub": str(ct.id), "tid": str(t.id), "cid": str(c.id), "jti": jti, "typ": "portal", "iat": int(utcnow().timestamp()), "exp": int(exp.timestamp())}, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        sess = db.execute(select(PortalSession).where(PortalSession.jti == jti)).scalar_one()
    events.emit(db, tenant_id=t.id, client_id=c.id, module_key="client", kind="portal.login", summary=f"{ct.full_name} signed in to the portal", actor_label=ct.full_name, ref_type="contact", ref_id=ct.id)
    return token, sess, t, c, ct


def authenticate(db: Session, token: str) -> tuple[Tenant, Client, Contact, PortalSession]:
    try:
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], options={"require": ["sub", "tid", "cid", "jti", "exp"]})
    except jwt.InvalidTokenError:
        raise PortalError("unauthenticated")
    if claims.get("typ") != "portal":
        raise PortalError("unauthenticated")
    with platform_scope():
        sess = db.execute(select(PortalSession).where(PortalSession.jti == claims["jti"])).scalar_one_or_none()
        if sess is None or sess.revoked or sess.expires_at < utcnow():
            raise PortalError("unauthenticated")
        t = db.get(Tenant, uuid.UUID(claims["tid"]))
        ct = db.get(Contact, uuid.UUID(claims["sub"]))
        c = db.get(Client, uuid.UUID(claims["cid"]))
        if not t or not ct or not c or not ct.portal_access or ct.client_id != c.id:
            raise PortalError("unauthenticated")
        try:
            entitlements.check(db, t, "client")
        except entitlements.NotEntitled:
            raise PortalError("portal_unavailable")
        sess.last_seen_at = utcnow()
    bind_tenant(db, t.id)
    set_tenant(t.id)
    return t, c, ct, sess


# ------------------------------------------------------------------ portal home
def _entitled(db: Session, t: Tenant, key: str) -> bool:
    try:
        entitlements.check(db, t, key)
        return True
    except entitlements.NotEntitled:
        return False


def me(db: Session, t: Tenant, c: Client, ct: Contact) -> S.PortalMe:
    from app.modules.requests.models import RequestPack
    from app.modules.sign.models import Agreement, Signer
    feats = {"documents": True, "messages": True, "requests": _entitled(db, t, "requests"), "agreements": _entitled(db, t, "sign"), "jobs": _entitled(db, t, "practice")}
    counts = {
        "shared_documents": db.execute(select(func.count()).select_from(Document).where(Document.client_id == c.id, Document.visible_to_client.is_(True), Document.deleted_at.is_(None))).scalar_one(),
        "unread_messages": db.execute(select(func.count()).select_from(PortalMessage).where(PortalMessage.client_id == c.id, PortalMessage.membership_id.is_not(None), PortalMessage.read_by_client_at.is_(None))).scalar_one(),
        "open_requests": db.execute(select(func.count()).select_from(RequestPack).where(RequestPack.client_id == c.id, RequestPack.status.in_(["sent", "in_progress"]))).scalar_one() if feats["requests"] else 0,
        "awaiting_signature": db.execute(select(func.count()).select_from(Signer).join(Agreement, Agreement.id == Signer.agreement_id).where(Agreement.client_id == c.id, func.lower(Signer.email) == (ct.email or "").lower(), Signer.status.in_(["sent", "viewed"]), Agreement.status.in_(["sent", "partially_signed"]))).scalar_one() if feats["agreements"] else 0,
    }
    return S.PortalMe(contact_id=ct.id, name=ct.full_name, email=ct.email, client_id=c.id, client_name=c.name, client_type=c.client_type, practice_name=t.name, practice_email=getattr(t, "contact_email", None), practice_phone=getattr(t, "phone", None), features=feats, counts=counts)


def home(db: Session, t: Tenant, c: Client, ct: Contact) -> S.PortalHome:
    from app.modules.requests import service as req_svc
    from app.modules.requests.models import RequestPack
    from app.modules.sign.models import Agreement
    from app.modules.practice.models import Job
    m = me(db, t, c, ct)
    reqs, agrs, jobs = [], [], []
    if m.features["requests"]:
        for p in db.execute(select(RequestPack).where(RequestPack.client_id == c.id, RequestPack.status != "cancelled").order_by(RequestPack.created_at.desc()).limit(20)).scalars():
            done = sum(1 for i in p.items if i.status in ("accepted", "not_applicable"))
            reqs.append(S.PortalRequest(id=p.id, title=p.title, purpose=p.purpose, status=p.status, due_on=p.due_on, overdue=bool(p.due_on and p.due_on < date.today() and p.status in ("sent", "in_progress")), items_total=len(p.items), items_done=done, outstanding=len(req_svc.outstanding(p))))
    if m.features["agreements"]:
        for a in db.execute(select(Agreement).where(Agreement.client_id == c.id, Agreement.status != "draft").order_by(Agreement.created_at.desc()).limit(20)).scalars():
            mine = next((s for s in a.signers if (s.email or "").lower() == (ct.email or "").lower()), None)
            agrs.append(S.PortalAgreement(id=a.id, title=a.title, kind=a.kind, status=a.status, my_status=mine.status if mine else "n/a", sent_at=a.sent_at, completed_at=a.completed_at, expires_at=a.expires_at))
    if m.features["jobs"]:
        for j in db.execute(select(Job).where(Job.client_id == c.id, Job.status != "cancelled").order_by(Job.due_on.is_(None), Job.due_on).limit(20)).scalars():
            jobs.append(S.PortalJob(id=j.id, title=j.title, job_type=j.job_type, period_label=j.period_label, status=j.status, due_on=j.due_on, completed_at=j.completed_at))
    recent = [S.PortalActivity(kind=e.kind, summary=e.summary, module_key=e.module_key, occurred_at=e.occurred_at) for e in db.execute(select(TimelineEvent).where(TimelineEvent.client_id == c.id, TimelineEvent.kind.in_(CLIENT_VISIBLE_KINDS)).order_by(TimelineEvent.occurred_at.desc()).limit(15)).scalars()]
    return S.PortalHome(me=m, requests=reqs, agreements=agrs, jobs=jobs, recent=recent, messages=thread(db, c.id, for_client=True))


def documents(db: Session, c: Client) -> list[S.PortalDocument]:
    rows = db.execute(select(Document).where(Document.client_id == c.id, Document.visible_to_client.is_(True), Document.deleted_at.is_(None)).order_by(Document.created_at.desc())).scalars().all()
    return [S.PortalDocument(id=d.id, filename=d.filename, kind=d.kind, size_bytes=d.size_bytes, content_type=d.content_type, uploaded_by="You" if d.uploaded_by_membership_id is None else "Practice", created_at=d.created_at) for d in rows]


def portal_document(db: Session, c: Client, doc_id: uuid.UUID) -> Document:
    d = db.get(Document, doc_id)
    if d is None or d.client_id != c.id or not d.visible_to_client or d.deleted_at is not None:
        raise PortalError("not_found")
    return d


def resend_signing_link(db: Session, t: Tenant, c: Client, ct: Contact, agreement_id: uuid.UUID) -> int:
    from app.modules.sign import service as sign_svc
    from app.modules.sign.models import Agreement
    a = db.get(Agreement, agreement_id)
    if a is None or a.client_id != c.id:
        raise PortalError("not_found")
    if not any((s.email or "").lower() == (ct.email or "").lower() for s in a.signers):
        raise PortalError("not_a_signer")
    try:
        return sign_svc.send(db, t, a, None, ct.full_name, reminder=True)
    except ValueError as e:
        raise PortalError("cannot_resend", str(e))
