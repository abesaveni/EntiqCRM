"""EnTIQ CRM — module 16, part of the base plan. Every route sits behind require_module('crm')."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas_crm as S
from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.models.crm import Client, Contact, Note, Relationship, Segment, Task, TimelineEvent, ImportJob
from app.services import crm_service as svc
from app.services import import_service

router = APIRouter(prefix="/crm", tags=["crm"])

view = require_module("crm")
edit = require_module("crm", write=True)


def _client_or_404(db: Session, client_id: uuid.UUID) -> Client:
    c = db.get(Client, client_id)  # tenant filter applies via the Session binding
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "client_not_found"})
    return c


def _label(p: Principal) -> str:
    return p.user.full_name


# ------------------------------------------------------------------ home / search / staff
@router.get("/home", response_model=S.HomeOut)
def home(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.home(db, p.tenant.id, p.membership.id)


@router.get("/search", response_model=list[S.SearchHit])
def search(q: str = Query("", max_length=120), p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.search(db, q)


@router.get("/staff", response_model=list[S.StaffOut])
def staff(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.staff(db, p.tenant.id)


# ------------------------------------------------------------------ clients
@router.get("/clients", response_model=S.ClientPage)
def list_clients(
    q: str | None = None, stage: str | None = None, client_type: str | None = None, owner: uuid.UUID | None = None, risk: str | None = None,
    tag: str | None = None, include_archived: bool = False, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200), sort: str = "name",
    p: Principal = Depends(view), db: Session = Depends(get_db),
):
    rows, total = svc.list_clients(db, {"q": q, "stage": stage, "client_type": client_type, "owner": owner, "risk": risk, "tag": tag, "include_archived": include_archived}, page, size, sort)
    return S.ClientPage(items=svc.clients_out(db, rows), total=total, page=page, size=size)


@router.post("/clients", response_model=S.ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(body: S.ClientIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    c = svc.create_client(db, p.tenant.id, body, p.membership.id, _label(p))
    db.commit()
    return svc.clients_out(db, [c])[0]


@router.get("/clients/{client_id}", response_model=S.ClientOut)
def get_client(client_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.clients_out(db, [_client_or_404(db, client_id)])[0]


@router.patch("/clients/{client_id}", response_model=S.ClientOut)
def patch_client(client_id: uuid.UUID, body: S.ClientPatch, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    c = svc.update_client(db, _client_or_404(db, client_id), body, p.membership.id, _label(p))
    db.commit()
    return svc.clients_out(db, [c])[0]


@router.post("/clients/{client_id}/stage", response_model=S.ClientOut)
def set_stage(client_id: uuid.UUID, body: S.StageIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:pipeline")), db: Session = Depends(get_db)):
    c = svc.change_stage(db, _client_or_404(db, client_id), body.stage, body.reason, p.membership.id, _label(p))
    db.commit()
    return svc.clients_out(db, [c])[0]


@router.delete("/clients/{client_id}", response_model=S.ClientOut)
def archive_client(client_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:delete")), db: Session = Depends(get_db)):
    """Archive, never delete. The record and its history stay; it leaves lists and search."""
    c = svc.archive_client(db, _client_or_404(db, client_id), p.membership.id, _label(p))
    db.commit()
    return svc.clients_out(db, [c])[0]


@router.get("/clients/{client_id}/timeline", response_model=list[S.TimelineOut])
def client_timeline(client_id: uuid.UUID, limit: int = Query(50, ge=1, le=200), p: Principal = Depends(view), db: Session = Depends(get_db)):
    _client_or_404(db, client_id)
    rows = db.execute(select(TimelineEvent).where(TimelineEvent.client_id == client_id).order_by(TimelineEvent.occurred_at.desc()).limit(limit)).scalars().all()
    return [svc.timeline_out(e) for e in rows]


# ------------------------------------------------------------------ contacts
@router.get("/clients/{client_id}/contacts", response_model=list[S.ContactOut])
def list_contacts(client_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    _client_or_404(db, client_id)
    rows = db.execute(select(Contact).where(Contact.client_id == client_id, Contact.archived_at.is_(None)).order_by(Contact.is_primary.desc(), Contact.first_name)).scalars().all()
    return [svc.contact_out(c) for c in rows]


@router.post("/clients/{client_id}/contacts", response_model=S.ContactOut, status_code=status.HTTP_201_CREATED)
def add_contact(client_id: uuid.UUID, body: S.ContactIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    ct = svc.add_contact(db, _client_or_404(db, client_id), body, p.membership.id, _label(p))
    db.commit()
    return svc.contact_out(ct)


@router.get("/contacts", response_model=list[S.ContactOut])
def contacts_directory(q: str | None = None, limit: int = Query(100, ge=1, le=500), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Contact).where(Contact.archived_at.is_(None))
    if q:
        from sqlalchemy import func, or_
        raw = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Contact.first_name).like(raw), func.lower(Contact.last_name).like(raw), func.lower(Contact.email).like(raw)))
    rows = db.execute(stmt.order_by(Contact.first_name, Contact.last_name).limit(limit)).scalars().all()
    return [svc.contact_out(c) for c in rows]


@router.patch("/contacts/{contact_id}", response_model=S.ContactOut)
def patch_contact(contact_id: uuid.UUID, body: S.ContactPatch, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    ct = db.get(Contact, contact_id)
    if ct is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    svc.update_contact(db, ct, body)
    db.commit()
    return svc.contact_out(ct)


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_contact(contact_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    ct = db.get(Contact, contact_id)
    if ct is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    from app.core.security import utcnow
    ct.archived_at, ct.is_primary = utcnow(), False
    db.commit()


# ------------------------------------------------------------------ relationships
@router.get("/clients/{client_id}/relationships", response_model=list[S.RelationshipOut])
def list_relationships(client_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    _client_or_404(db, client_id)
    return [svc.relationship_out(db, r) for r in svc.relationships_for_client(db, client_id)]


@router.post("/relationships", response_model=S.RelationshipOut, status_code=status.HTTP_201_CREATED)
def add_relationship(body: S.RelationshipIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    for t, i in ((body.from_type, body.from_id), (body.to_type, body.to_id)):
        if (db.get(Client, i) if t == "client" else db.get(Contact, i)) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": f"{t}_not_found", "id": str(i)})
    r = Relationship(tenant_id=p.tenant.id, **body.model_dump())
    db.add(r)
    db.flush()
    out = svc.relationship_out(db, r)
    client_id = body.to_id if body.to_type == "client" else (body.from_id if body.from_type == "client" else None)
    from app.core import events
    events.emit(db, tenant_id=p.tenant.id, client_id=client_id, module_key="crm", kind="relationship.added", summary=f"{out.from_label} is {body.kind.replace('_', ' ')} {out.to_label}",
                actor_membership_id=p.membership.id, actor_label=_label(p), ref_type="relationship", ref_id=r.id)
    db.commit()
    return out


@router.delete("/relationships/{rel_id}", status_code=status.HTTP_204_NO_CONTENT)
def end_relationship(rel_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    r = db.get(Relationship, rel_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    from app.core.security import utcnow
    r.ended_at = utcnow()
    db.commit()


# ------------------------------------------------------------------ tasks
@router.get("/tasks", response_model=list[S.TaskOut])
def list_tasks(status_: str | None = Query("open", alias="status"), client_id: uuid.UUID | None = None, assignee: uuid.UUID | None = None, mine: bool = False,
               limit: int = Query(200, ge=1, le=500), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Task)
    if status_ and status_ != "all":
        stmt = stmt.where(Task.status == status_)
    if client_id:
        stmt = stmt.where(Task.client_id == client_id)
    if assignee:
        stmt = stmt.where(Task.assignee_membership_id == assignee)
    if mine:
        stmt = stmt.where(Task.assignee_membership_id == p.membership.id)
    rows = db.execute(stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc()).limit(limit)).scalars().all()
    cn = svc.client_name_map(db, {t.client_id for t in rows})
    mn = svc.member_names(db, {t.assignee_membership_id for t in rows})
    return [svc.task_out(t, cn, mn) for t in rows]


@router.post("/tasks", response_model=S.TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(body: S.TaskIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    if body.client_id:
        _client_or_404(db, body.client_id)
    t = Task(tenant_id=p.tenant.id, created_by_membership_id=p.membership.id, module_key="crm", **body.model_dump())
    db.add(t)
    db.flush()
    from app.core import events
    events.emit(db, tenant_id=p.tenant.id, client_id=t.client_id, module_key="crm", kind="task.created", summary=f"Task: {t.title}",
                detail={"title": t.title, "assignee_membership_id": str(t.assignee_membership_id) if t.assignee_membership_id else None, "due_at": t.due_at.isoformat() if t.due_at else None},
                actor_membership_id=p.membership.id, actor_label=_label(p), ref_type="task", ref_id=t.id)
    db.commit()
    cn = svc.client_name_map(db, {t.client_id})
    return svc.task_out(t, cn, svc.member_names(db, {t.assignee_membership_id}))


@router.patch("/tasks/{task_id}", response_model=S.TaskOut)
def patch_task(task_id: uuid.UUID, body: S.TaskPatch, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("status") == "done":
        svc.complete_task(db, t, p.membership.id, _label(p))
        changes.pop("status")
    for k, v in changes.items():
        setattr(t, k, v)
    db.commit()
    return svc.task_out(t, svc.client_name_map(db, {t.client_id}), svc.member_names(db, {t.assignee_membership_id}))


@router.post("/tasks/{task_id}/complete", response_model=S.TaskOut)
def complete_task(task_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    svc.complete_task(db, t, p.membership.id, _label(p))
    db.commit()
    return svc.task_out(t, svc.client_name_map(db, {t.client_id}), svc.member_names(db, {t.assignee_membership_id}))


# ------------------------------------------------------------------ notes
@router.get("/clients/{client_id}/notes", response_model=list[S.NoteOut])
def list_notes(client_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    _client_or_404(db, client_id)
    rows = db.execute(select(Note).where(Note.client_id == client_id).order_by(Note.pinned.desc(), Note.created_at.desc())).scalars().all()
    names = svc.member_names(db, {n.author_membership_id for n in rows})
    return [S.NoteOut(id=n.id, client_id=n.client_id, body=n.body, author_name=names.get(n.author_membership_id) if n.author_membership_id else None, pinned=n.pinned, created_at=n.created_at, updated_at=n.updated_at) for n in rows]


@router.post("/clients/{client_id}/notes", response_model=S.NoteOut, status_code=status.HTTP_201_CREATED)
def add_note(client_id: uuid.UUID, body: S.NoteIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    n = svc.add_note(db, _client_or_404(db, client_id), body, p.membership.id, _label(p))
    db.commit()
    return S.NoteOut(id=n.id, client_id=n.client_id, body=n.body, author_name=_label(p), pinned=n.pinned, created_at=n.created_at, updated_at=n.updated_at)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    n = db.get(Note, note_id)
    if n is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    db.delete(n)
    db.commit()


# ------------------------------------------------------------------ pipeline / segments / duplicates
@router.get("/pipeline", response_model=list[S.PipelineColumn])
def pipeline(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.pipeline(db)


@router.get("/segments", response_model=list[S.SegmentOut])
def list_segments(p: Principal = Depends(view), db: Session = Depends(get_db)):
    rows = db.execute(select(Segment).order_by(Segment.name)).scalars().all()
    return [S.SegmentOut(id=s.id, name=s.name, description=s.description, filters=s.filters, member_count=svc.segment_count(db, s), created_at=s.created_at) for s in rows]


@router.post("/segments", response_model=S.SegmentOut, status_code=status.HTTP_201_CREATED)
def create_segment(body: S.SegmentIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:segments")), db: Session = Depends(get_db)):
    s = Segment(tenant_id=p.tenant.id, created_by_membership_id=p.membership.id, **body.model_dump())
    db.add(s)
    db.commit()
    return S.SegmentOut(id=s.id, name=s.name, description=s.description, filters=s.filters, member_count=svc.segment_count(db, s), created_at=s.created_at)


@router.get("/segments/{segment_id}/members", response_model=S.ClientPage)
def segment_members(segment_id: uuid.UUID, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200), p: Principal = Depends(view), db: Session = Depends(get_db)):
    s = db.get(Segment, segment_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    rows, total = svc.list_clients(db, s.filters or {}, page, size, "name")
    return S.ClientPage(items=svc.clients_out(db, rows), total=total, page=page, size=size)


@router.delete("/segments/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_segment(segment_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:segments")), db: Session = Depends(get_db)):
    s = db.get(Segment, segment_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    db.delete(s)
    db.commit()


@router.get("/duplicates", response_model=list[S.DuplicateGroup])
def duplicates(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.duplicates(db)


# ------------------------------------------------------------------ import
@router.post("/import/preview", response_model=S.ImportPreview, status_code=status.HTTP_201_CREATED)
async def import_preview(file: UploadFile = File(...), p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail={"error": "file_too_large", "max_mb": 10})
    try:
        _job, preview = import_service.start_job(db, p.tenant.id, file.filename or "clients.csv", data, p.membership.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "unreadable_file", "message": str(e)})
    db.commit()
    return preview


@router.post("/import/{job_id}/commit", response_model=S.ImportResult)
def import_commit(job_id: uuid.UUID, body: S.ImportCommitIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        result = import_service.commit_job(db, job, body, p.membership.id, _label(p))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_mapping", "message": str(e)})
    db.commit()
    return result


@router.get("/import/{job_id}", response_model=S.ImportResult)
def import_status(job_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return S.ImportResult(job_id=job.id, status=job.status, row_count=job.row_count, created_count=job.created_count, updated_count=job.updated_count, skipped_count=job.skipped_count, errors=job.errors)
