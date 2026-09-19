"""CRM queries and mutations. Everything here runs with the tenant already bound to the session."""
from __future__ import annotations

import re
import uuid
from datetime import timedelta

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app import schemas_crm as S
from app.core import events
from app.core.security import utcnow
from app.core.tenancy import platform_scope
from app.models.crm import Client, Contact, Note, Relationship, Segment, Task, TimelineEvent
from app.models.identity import Membership, User

_SUFFIXES = re.compile(r"\b(pty|ltd|limited|proprietary|the|trust|family|atf|as trustee for|inc|co|company)\b\.?", re.I)


def normalise_name(name: str) -> str:
    s = name.lower()
    s = _SUFFIXES.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def format_abn(abn: str | None) -> str | None:
    if not abn or len(abn) != 11:
        return abn
    return f"{abn[:2]} {abn[2:5]} {abn[5:8]} {abn[8:]}"


# ------------------------------------------------------------------ member names (for owners / assignees / authors)
def member_names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    with platform_scope():
        rows = db.execute(select(Membership.id, User.full_name).join(User, User.id == Membership.user_id).where(Membership.id.in_(ids))).all()
    return {mid: name for mid, name in rows}


def staff(db: Session, tenant_id: uuid.UUID) -> list[S.StaffOut]:
    with platform_scope():
        rows = db.execute(
            select(Membership, User).join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant_id, Membership.status == "active").order_by(User.full_name)
        ).all()
    return [S.StaffOut(membership_id=m.id, name=u.full_name, email=u.email, role=m.role) for m, u in rows]


# ------------------------------------------------------------------ serialisers
def contact_out(c: Contact) -> S.ContactOut:
    return S.ContactOut(id=c.id, client_id=c.client_id, first_name=c.first_name, last_name=c.last_name, full_name=c.full_name, email=c.email,
                        phone=c.phone, role=c.role, is_primary=c.is_primary, notes=c.notes, has_portal_access=c.portal_access, created_at=c.created_at)


def clients_out(db: Session, clients: list[Client], *, with_aggregates: bool = True) -> list[S.ClientOut]:
    if not clients:
        return []
    ids = [c.id for c in clients]
    names = member_names(db, {c.owner_membership_id for c in clients if c.owner_membership_id})
    contact_counts: dict[uuid.UUID, int] = {}
    task_counts: dict[uuid.UUID, int] = {}
    doc_counts: dict[uuid.UUID, int] = {}
    primaries: dict[uuid.UUID, Contact] = {}
    if with_aggregates:
        from app.models.platform import Document
        for cid, n in db.execute(select(Document.client_id, func.count()).where(Document.client_id.in_(ids), Document.deleted_at.is_(None)).group_by(Document.client_id)).all():
            doc_counts[cid] = n
        for cid, n in db.execute(select(Contact.client_id, func.count()).where(Contact.client_id.in_(ids), Contact.archived_at.is_(None)).group_by(Contact.client_id)).all():
            contact_counts[cid] = n
        for cid, n in db.execute(select(Task.client_id, func.count()).where(Task.client_id.in_(ids), Task.status == "open").group_by(Task.client_id)).all():
            task_counts[cid] = n
        for c in db.execute(select(Contact).where(Contact.client_id.in_(ids), Contact.is_primary.is_(True), Contact.archived_at.is_(None))).scalars():
            primaries.setdefault(c.client_id, c)
    out = []
    for c in clients:
        out.append(S.ClientOut(
            id=c.id, name=c.name, legal_name=c.legal_name, client_type=c.client_type, abn=c.abn, abn_formatted=format_abn(c.abn), acn=c.acn,
            stage=c.stage, owner_membership_id=c.owner_membership_id, owner_name=names.get(c.owner_membership_id) if c.owner_membership_id else None,
            risk_rating=c.risk_rating, risk_assessed_at=c.risk_assessed_at, since=c.since, email=c.email, phone=c.phone, website=c.website,
            address_line1=c.address_line1, address_line2=c.address_line2, suburb=c.suburb, state=c.state, postcode=c.postcode, country=c.country,
            source=c.source, external_ref=c.external_ref, tags=list(c.tags or []), custom=dict(c.custom or {}), archived_at=c.archived_at,
            created_at=c.created_at, updated_at=c.updated_at,
            contact_count=contact_counts.get(c.id, 0), open_task_count=task_counts.get(c.id, 0), document_count=doc_counts.get(c.id, 0),
            primary_contact=contact_out(primaries[c.id]) if c.id in primaries else None,
        ))
    return out


def task_out(t: Task, client_names: dict[uuid.UUID, str], member: dict[uuid.UUID, str]) -> S.TaskOut:
    now = utcnow()
    return S.TaskOut(id=t.id, client_id=t.client_id, client_name=client_names.get(t.client_id) if t.client_id else None, title=t.title, description=t.description,
                     due_at=t.due_at, priority=t.priority, status=t.status, assignee_membership_id=t.assignee_membership_id,
                     assignee_name=member.get(t.assignee_membership_id) if t.assignee_membership_id else None, module_key=t.module_key, done_at=t.done_at,
                     created_at=t.created_at, overdue=bool(t.status == "open" and t.due_at and t.due_at < now))


def timeline_out(ev: TimelineEvent, client_names: dict[uuid.UUID, str] | None = None) -> S.TimelineOut:
    return S.TimelineOut(id=ev.id, client_id=ev.client_id, client_name=(client_names or {}).get(ev.client_id) if ev.client_id else None, module_key=ev.module_key,
                         kind=ev.kind, summary=ev.summary, detail=ev.detail or {}, actor_label=ev.actor_label, ref_type=ev.ref_type, ref_id=ev.ref_id, occurred_at=ev.occurred_at)


def client_name_map(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {cid: n for cid, n in db.execute(select(Client.id, Client.name).where(Client.id.in_(ids))).all()}


# ------------------------------------------------------------------ client queries
def apply_filters(stmt, f: dict):
    if f.get("q"):
        needle = f"%{normalise_name(f['q'])}%"
        raw = f"%{f['q'].lower()}%"
        stmt = stmt.where(or_(Client.name_normalised.like(needle), func.lower(Client.name).like(raw), Client.abn.like(f"%{''.join(ch for ch in f['q'] if ch.isdigit())}%") if any(ch.isdigit() for ch in f["q"]) else False, func.lower(Client.email).like(raw)))
    if f.get("stage"):
        stmt = stmt.where(Client.stage == f["stage"])
    if f.get("client_type"):
        stmt = stmt.where(Client.client_type == f["client_type"])
    if f.get("owner"):
        stmt = stmt.where(Client.owner_membership_id == f["owner"])
    if f.get("risk") == "elevated":
        stmt = stmt.where(Client.risk_rating.in_(["Medium", "High"]))
    elif f.get("risk"):
        stmt = stmt.where(Client.risk_rating == f["risk"])
    if f.get("tag"):
        stmt = stmt.where(func.lower(cast(Client.tags, String)).like(f"%{f['tag'].lower()}%"))
    if not f.get("include_archived"):
        stmt = stmt.where(Client.archived_at.is_(None))
    return stmt


SORTS = {"name": Client.name, "-name": Client.name.desc(), "since": Client.since, "-since": Client.since.desc(), "updated": Client.updated_at, "-updated": Client.updated_at.desc(), "stage": Client.stage}


def list_clients(db: Session, f: dict, page: int, size: int, sort: str) -> tuple[list[Client], int]:
    base = apply_filters(select(Client), f)
    # Count FROM the table with the same filters — never through .subquery(), which hides the
    # table from the tenant filter (see core.database._tenant_read_filter).
    total = db.execute(apply_filters(select(func.count()).select_from(Client), f)).scalar_one()
    rows = db.execute(base.order_by(SORTS.get(sort, Client.name)).offset((page - 1) * size).limit(size)).scalars().all()
    return list(rows), total


def create_client(db: Session, tenant_id: uuid.UUID, body: S.ClientIn, actor_mid: uuid.UUID | None, actor_label: str) -> Client:
    c = Client(tenant_id=tenant_id, **body.model_dump(), name_normalised=normalise_name(body.name))
    db.add(c)
    db.flush()
    events.emit(db, tenant_id=tenant_id, client_id=c.id, module_key="crm", kind="client.created", summary=f"{c.name} added as a {c.stage.lower()}",
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="client", ref_id=c.id)
    return c


def update_client(db: Session, c: Client, body: S.ClientPatch, actor_mid: uuid.UUID | None, actor_label: str) -> Client:
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(c, k, v)
    if "name" in changes:
        c.name_normalised = normalise_name(c.name)
    if changes:
        events.emit(db, tenant_id=c.tenant_id, client_id=c.id, module_key="crm", kind="client.updated", summary=f"Details updated: {', '.join(changes)}",
                    detail={"fields": sorted(changes)}, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="client", ref_id=c.id)
    return c


def change_stage(db: Session, c: Client, stage: str, reason: str | None, actor_mid: uuid.UUID | None, actor_label: str) -> Client:
    if stage == c.stage:
        return c
    old = c.stage
    c.stage = stage
    if stage == "Active" and c.since is None:
        c.since = utcnow().date()
    events.emit(db, tenant_id=c.tenant_id, client_id=c.id, module_key="crm", kind="stage.changed", summary=f"Moved from {old} to {stage}" + (f" — {reason}" if reason else ""),
                detail={"from": old, "to": stage, "reason": reason, "owner_membership_id": str(c.owner_membership_id) if c.owner_membership_id else None},
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="client", ref_id=c.id)
    return c


def archive_client(db: Session, c: Client, actor_mid: uuid.UUID | None, actor_label: str) -> Client:
    c.archived_at = utcnow()
    events.emit(db, tenant_id=c.tenant_id, client_id=c.id, module_key="crm", kind="client.archived", summary=f"{c.name} archived",
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="client", ref_id=c.id)
    return c


# ------------------------------------------------------------------ contacts
def add_contact(db: Session, c: Client, body: S.ContactIn, actor_mid, actor_label) -> Contact:
    if body.is_primary:
        for other in db.execute(select(Contact).where(Contact.client_id == c.id, Contact.is_primary.is_(True))).scalars():
            other.is_primary = False
    ct = Contact(tenant_id=c.tenant_id, client_id=c.id, **body.model_dump())
    db.add(ct)
    db.flush()
    events.emit(db, tenant_id=c.tenant_id, client_id=c.id, module_key="crm", kind="contact.added", summary=f"{ct.full_name} added" + (f" as {ct.role}" if ct.role else ""),
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="contact", ref_id=ct.id)
    return ct


def update_contact(db: Session, ct: Contact, body: S.ContactPatch) -> Contact:
    changes = body.model_dump(exclude_unset=True)
    if changes.get("is_primary"):
        for other in db.execute(select(Contact).where(Contact.client_id == ct.client_id, Contact.is_primary.is_(True), Contact.id != ct.id)).scalars():
            other.is_primary = False
    for k, v in changes.items():
        setattr(ct, k, v)
    return ct


# ------------------------------------------------------------------ relationships
def party_label(db: Session, kind: str, pid: uuid.UUID) -> str:
    if kind == "client":
        return db.execute(select(Client.name).where(Client.id == pid)).scalar_one_or_none() or "Unknown client"
    ct = db.get(Contact, pid)
    return ct.full_name if ct else "Unknown contact"


def relationship_out(db: Session, r: Relationship) -> S.RelationshipOut:
    return S.RelationshipOut(id=r.id, from_type=r.from_type, from_id=r.from_id, from_label=party_label(db, r.from_type, r.from_id), to_type=r.to_type, to_id=r.to_id,
                             to_label=party_label(db, r.to_type, r.to_id), kind=r.kind, percentage=r.percentage, notes=r.notes, ended_at=r.ended_at)


def relationships_for_client(db: Session, client_id: uuid.UUID) -> list[Relationship]:
    contact_ids = [cid for (cid,) in db.execute(select(Contact.id).where(Contact.client_id == client_id)).all()]
    party_ids = [client_id, *contact_ids]
    return list(db.execute(select(Relationship).where(or_(Relationship.from_id.in_(party_ids), Relationship.to_id.in_(party_ids)), Relationship.ended_at.is_(None)).order_by(Relationship.kind)).scalars())


# ------------------------------------------------------------------ tasks / notes
def complete_task(db: Session, t: Task, actor_mid, actor_label) -> Task:
    if t.status == "done":
        return t
    t.status, t.done_at = "done", utcnow()
    events.emit(db, tenant_id=t.tenant_id, client_id=t.client_id, module_key=t.module_key, kind="task.completed", summary=f"Completed: {t.title}",
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="task", ref_id=t.id)
    return t


def add_note(db: Session, c: Client, body: S.NoteIn, actor_mid, actor_label) -> Note:
    n = Note(tenant_id=c.tenant_id, client_id=c.id, body=body.body, pinned=body.pinned, author_membership_id=actor_mid)
    db.add(n)
    db.flush()
    preview = body.body.strip().splitlines()[0][:140] if body.body.strip() else "Note"
    events.emit(db, tenant_id=c.tenant_id, client_id=c.id, module_key="crm", kind="note.added", summary=preview, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="note", ref_id=n.id)
    return n


# ------------------------------------------------------------------ pipeline / home / segments / search / duplicates
PIPELINE_STAGES = ("Lead", "Proposal", "Onboarding", "Active", "Review", "Dormant")


def pipeline(db: Session) -> list[S.PipelineColumn]:
    cols = []
    for st in PIPELINE_STAGES:
        rows = db.execute(select(Client).where(Client.stage == st, Client.archived_at.is_(None)).order_by(Client.updated_at.desc()).limit(50)).scalars().all()
        count = db.execute(select(func.count()).select_from(Client).where(Client.stage == st, Client.archived_at.is_(None))).scalar_one()
        cols.append(S.PipelineColumn(stage=st, count=count, clients=clients_out(db, list(rows), with_aggregates=True)))
    return cols


def home(db: Session, tenant_id: uuid.UUID, membership_id: uuid.UUID) -> S.HomeOut:
    now = utcnow()
    week = now + timedelta(days=7)
    open_tasks = db.execute(select(Task).where(Task.status == "open").order_by(Task.due_at.asc().nulls_last()).limit(200)).scalars().all()
    overdue = [t for t in open_tasks if t.due_at and t.due_at < now]
    soon = [t for t in open_tasks if t.due_at and now <= t.due_at <= week]
    risks = db.execute(select(Client).where(Client.risk_rating.in_(["Medium", "High"]), Client.archived_at.is_(None)).order_by(Client.risk_rating.desc()).limit(8)).scalars().all()
    in_pipeline = db.execute(select(func.count()).select_from(Client).where(Client.stage.in_(["Lead", "Proposal", "Onboarding"]), Client.archived_at.is_(None))).scalar_one()
    total = db.execute(select(func.count()).select_from(Client).where(Client.archived_at.is_(None))).scalar_one()
    recent = db.execute(select(TimelineEvent).order_by(TimelineEvent.occurred_at.desc()).limit(10)).scalars().all()
    shown = (overdue + soon + [t for t in open_tasks if not t.due_at])[:8]
    cn = client_name_map(db, {t.client_id for t in shown} | {e.client_id for e in recent})
    mn = member_names(db, {t.assignee_membership_id for t in shown})
    return S.HomeOut(overdue_tasks=len(overdue), due_this_week=len(soon), elevated_risk=len(risks), in_pipeline=in_pipeline, total_clients=total,
                     tasks=[task_out(t, cn, mn) for t in shown], risks=clients_out(db, list(risks), with_aggregates=False), recent=[timeline_out(e, cn) for e in recent])


def segment_count(db: Session, seg: Segment) -> int:
    return db.execute(apply_filters(select(func.count()).select_from(Client), seg.filters or {})).scalar_one()


def search(db: Session, q: str, limit: int = 12) -> list[S.SearchHit]:
    hits: list[S.SearchHit] = []
    if not q.strip():
        return hits
    for c in list_clients(db, {"q": q}, 1, limit, "name")[0]:
        hits.append(S.SearchHit(type="client", id=c.id, client_id=c.id, label=c.name, sublabel=f"{c.client_type}" + (f" · ABN {format_abn(c.abn)}" if c.abn else "")))
    raw = f"%{q.lower()}%"
    contacts = db.execute(select(Contact).where(Contact.archived_at.is_(None), or_(func.lower(Contact.first_name + " " + func.coalesce(Contact.last_name, "")).like(raw), func.lower(Contact.email).like(raw))).limit(limit)).scalars().all()
    cn = client_name_map(db, {c.client_id for c in contacts})
    for ct in contacts:
        hits.append(S.SearchHit(type="contact", id=ct.id, client_id=ct.client_id, label=ct.full_name, sublabel=f"{ct.role or 'Contact'} · {cn.get(ct.client_id, '')}"))
    return hits[: limit * 2]


def duplicates(db: Session) -> list[S.DuplicateGroup]:
    groups: list[S.DuplicateGroup] = []
    live = select(Client).where(Client.archived_at.is_(None))
    for abn, n in db.execute(select(Client.abn, func.count()).where(Client.abn.is_not(None), Client.archived_at.is_(None)).group_by(Client.abn).having(func.count() > 1)).all():
        rows = db.execute(live.where(Client.abn == abn)).scalars().all()
        groups.append(S.DuplicateGroup(reason="abn", key=format_abn(abn) or abn, clients=clients_out(db, list(rows), with_aggregates=False)))
    for nn, n in db.execute(select(Client.name_normalised, func.count()).where(Client.archived_at.is_(None)).group_by(Client.name_normalised).having(func.count() > 1)).all():
        rows = db.execute(live.where(Client.name_normalised == nn)).scalars().all()
        abns = {r.abn for r in rows if r.abn}
        if len(abns) == 1 and all(r.abn for r in rows):
            continue  # every row shares one ABN → already reported as an ABN group
        groups.append(S.DuplicateGroup(reason="name", key=nn, clients=clients_out(db, list(rows), with_aggregates=False)))
    return groups
