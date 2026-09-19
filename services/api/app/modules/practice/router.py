"""EnTIQ Practice — module 09."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.modules.practice import schemas as S
from app.modules.practice import service as svc
from app.modules.practice.models import JOB_TYPES, OPEN_STATUSES, Job, RecurringJob, TimeEntry
from app.services.crm_service import client_name_map, member_names

router = APIRouter(prefix="/practice", tags=["practice"])
view = require_module("practice")
edit = require_module("practice", write=True)


def _job(db: Session, job_id: uuid.UUID) -> Job:
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "job_not_found"})
    return j


@router.get("/overview", response_model=S.OverviewOut)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.overview(db, p.tenant.id)


@router.get("/meta")
def meta(p: Principal = Depends(view)):
    return {"job_types": JOB_TYPES, "statuses": ["not_started", "in_progress", "waiting_client", "review", "complete", "cancelled"], "frequencies": ["monthly", "quarterly", "biannual", "annual"], "default_checklists": svc.DEFAULT_CHECKLISTS}


@router.get("/jobs", response_model=list[S.JobOut])
def list_jobs(status_: str | None = Query(None, alias="status"), client_id: uuid.UUID | None = None, assignee: uuid.UUID | None = None, job_type: str | None = None, mine: bool = False,
              open_only: bool = Query(False, alias="open"), limit: int = Query(200, ge=1, le=1000), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Job)
    if status_:
        stmt = stmt.where(Job.status == status_)
    if open_only:
        stmt = stmt.where(Job.status.in_(OPEN_STATUSES))
    if client_id:
        stmt = stmt.where(Job.client_id == client_id)
    if assignee:
        stmt = stmt.where(Job.assignee_membership_id == assignee)
    if mine:
        stmt = stmt.where(Job.assignee_membership_id == p.membership.id)
    if job_type:
        stmt = stmt.where(Job.job_type == job_type)
    rows = db.execute(stmt.order_by(Job.due_on.is_(None), Job.due_on, Job.created_at.desc()).limit(limit)).scalars().all()
    return svc.jobs_out(db, rows)


@router.post("/jobs", response_model=S.JobOut, status_code=status.HTTP_201_CREATED)
def create_job(body: S.JobIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("practice:jobs")), db: Session = Depends(get_db)):
    try:
        j = svc.create_job(db, p.tenant.id, body, p.membership.id, p.user.full_name)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_job", "message": str(e)})
    db.commit()
    return svc.jobs_out(db, [j])[0]


@router.get("/jobs/{job_id}", response_model=S.JobOut)
def get_job(job_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.jobs_out(db, [_job(db, job_id)])[0]


@router.patch("/jobs/{job_id}", response_model=S.JobOut)
def patch_job(job_id: uuid.UUID, body: S.JobPatch, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("practice:jobs")), db: Session = Depends(get_db)):
    j = _job(db, job_id)
    if body.assignee_membership_id is not None and body.assignee_membership_id != j.assignee_membership_id and not p.can("practice:assign"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "permission_denied", "permission": "practice:assign"})
    try:
        svc.patch_job(db, j, body, p.membership.id, p.user.full_name)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_job", "message": str(e)})
    db.commit()
    return svc.jobs_out(db, [j])[0]


@router.post("/jobs/{job_id}/status", response_model=S.JobOut)
def set_status(job_id: uuid.UUID, body: S.StatusIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("practice:jobs")), db: Session = Depends(get_db)):
    j = svc.set_status(db, _job(db, job_id), body.status, body.note, p.membership.id, p.user.full_name)
    db.commit()
    return svc.jobs_out(db, [j])[0]


@router.get("/jobs/{job_id}/time", response_model=list[S.TimeOut])
def list_time(job_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    _job(db, job_id)
    rows = db.execute(select(TimeEntry).where(TimeEntry.job_id == job_id).order_by(TimeEntry.worked_on.desc(), TimeEntry.created_at.desc())).scalars().all()
    return svc.time_out(db, rows)


@router.post("/jobs/{job_id}/time", response_model=S.TimeOut, status_code=status.HTTP_201_CREATED)
def add_time(job_id: uuid.UUID, body: S.TimeIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("practice:time")), db: Session = Depends(get_db)):
    t = svc.add_time(db, _job(db, job_id), body, p.membership.id)
    db.commit()
    return svc.time_out(db, [t])[0]


# ------------------------------------------------------------------ recurring
@router.get("/recurring", response_model=list[S.RecurringOut])
def list_recurring(client_id: uuid.UUID | None = None, p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(RecurringJob).order_by(RecurringJob.next_due_on)
    if client_id:
        stmt = stmt.where(RecurringJob.client_id == client_id)
    rows = db.execute(stmt).scalars().all()
    names = member_names(db, {r.assignee_membership_id for r in rows})
    cn = client_name_map(db, {r.client_id for r in rows})
    return [svc.recurring_out(r, names, cn) for r in rows]


@router.post("/recurring", response_model=S.RecurringOut, status_code=status.HTTP_201_CREATED)
def create_recurring(body: S.RecurringIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("practice:jobs")), db: Session = Depends(get_db)):
    try:
        r = svc.create_recurring(db, p.tenant.id, body, p.membership.id, p.user.full_name)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_recurring", "message": str(e)})
    db.commit()
    return svc.recurring_out(r, member_names(db, {r.assignee_membership_id}), client_name_map(db, {r.client_id}))


@router.post("/recurring/{recurring_id}/toggle", response_model=S.RecurringOut)
def toggle_recurring(recurring_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("practice:jobs")), db: Session = Depends(get_db)):
    r = db.get(RecurringJob, recurring_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    r.is_active = not r.is_active
    db.commit()
    return svc.recurring_out(r, member_names(db, {r.assignee_membership_id}), client_name_map(db, {r.client_id}))


@router.post("/recurring/generate")
def generate(as_of: date | None = None, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("practice:jobs")), db: Session = Depends(get_db)):
    """Create due recurring jobs now (the lifecycle job does this daily; this is the manual trigger)."""
    n = svc.generate_recurring(db, p.tenant.id, as_of)
    db.commit()
    return {"created": n}


# ------------------------------------------------------------------ views
@router.get("/deadlines", response_model=list[S.DeadlineOut])
def deadlines(days: int = Query(90, ge=7, le=400), p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.deadlines(db, days)


@router.get("/team", response_model=list[S.TeamMember])
def team(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.team(db, p.tenant.id)
