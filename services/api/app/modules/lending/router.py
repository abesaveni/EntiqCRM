"""EnTIQ Lending — module 20."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.modules.lending import schemas as S
from app.modules.lending import service as svc
from app.modules.lending.models import TERMINAL, Application, Condition
from app.services.crm_service import client_name_map, member_names

router = APIRouter(prefix="/lending", tags=["lending"])
view = require_module("lending")
edit = require_module("lending", write=True)


def _app(db: Session, application_id: uuid.UUID) -> Application:
    a = db.get(Application, application_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "application_not_found"})
    return a


def _err(e: svc.LendingError) -> HTTPException:
    return HTTPException({"client_not_found": 404, "closed": 409, "already_closed": 409, "conditions_open": 409, "not_approved": 409, "documents_outstanding": 409}.get(e.error, 400),
                         detail={"error": e.error, "message": e.message})


@router.get("/overview", response_model=S.OverviewOut)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.overview(db)


@router.get("/applications", response_model=list[S.ApplicationOut])
def list_applications(stage: str | None = None, client_id: uuid.UUID | None = None, open_only: bool = Query(False, alias="open"), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Application).order_by(Application.updated_at.desc())
    if stage:
        stmt = stmt.where(Application.stage == stage)
    if open_only:
        stmt = stmt.where(Application.stage.notin_(list(TERMINAL)))
    if client_id:
        stmt = stmt.where(Application.client_id == client_id)
    rows = db.execute(stmt).scalars().all()
    names = member_names(db, {a.owner_membership_id for a in rows})
    cn = client_name_map(db, {a.client_id for a in rows})
    return [svc.application_out(db, a, names, cn) for a in rows]


@router.post("/applications", response_model=S.ApplicationDetail, status_code=status.HTTP_201_CREATED)
def create(body: S.ApplicationIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("lending:intake")), db: Session = Depends(get_db)):
    try:
        a = svc.create(db, p.tenant, body, p.membership.id, p.user.full_name)
    except svc.LendingError as e:
        raise _err(e)
    db.commit()
    db.refresh(a)
    return svc.detail(db, a)


@router.get("/applications/{application_id}", response_model=S.ApplicationDetail)
def get_application(application_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.detail(db, _app(db, application_id))


@router.patch("/applications/{application_id}", response_model=S.ApplicationDetail)
def patch(application_id: uuid.UUID, body: S.ApplicationPatch, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("lending:intake")), db: Session = Depends(get_db)):
    a = _app(db, application_id)
    svc.patch(db, a, body)
    db.commit()
    return svc.detail(db, a)


@router.post("/applications/{application_id}/request", response_model=S.ApplicationDetail)
def open_request(application_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("lending:intake")), db: Session = Depends(get_db)):
    a = _app(db, application_id)
    pack_id = svc.open_request(db, p.tenant, a, p.membership.id, p.user.full_name)
    if pack_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "requests_required", "message": "Collecting the lending checklist needs the Requests module"})
    db.commit()
    return svc.detail(db, a)


@router.post("/applications/{application_id}/assess", response_model=S.ApplicationDetail)
def assess(application_id: uuid.UUID, body: S.ServiceabilityIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("lending:intake")), db: Session = Depends(get_db)):
    a = _app(db, application_id)
    svc.assess(db, a, body, p.user.full_name)
    db.commit()
    return svc.detail(db, a)


@router.post("/applications/{application_id}/stage", response_model=S.ApplicationDetail)
def set_stage(application_id: uuid.UUID, body: S.StageIn, p: Principal = Depends(edit), db: Session = Depends(get_db)):
    a = _app(db, application_id)
    needed = "lending:settle" if body.stage == "settled" else "lending:approve" if body.stage in ("approved", "declined") else "lending:intake"
    if not p.can(needed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "permission_denied", "permission": needed})
    try:
        svc.set_stage(db, p.tenant, a, body.stage, body.note, p.membership.id, p.user.full_name)
    except svc.LendingError as e:
        raise _err(e)
    db.commit()
    return svc.detail(db, a)


@router.post("/applications/{application_id}/conditions", response_model=S.ApplicationDetail, status_code=status.HTTP_201_CREATED)
def add_condition(application_id: uuid.UUID, body: S.ConditionIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("lending:approve")), db: Session = Depends(get_db)):
    a = _app(db, application_id)
    svc.add_condition(db, a, body, p.user.full_name)
    db.commit()
    return svc.detail(db, a)


@router.post("/applications/{application_id}/conditions/{condition_id}/satisfy", response_model=S.ApplicationDetail)
def satisfy_condition(application_id: uuid.UUID, condition_id: uuid.UUID, body: S.ConditionSatisfyIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("lending:intake")), db: Session = Depends(get_db)):
    a = _app(db, application_id)
    c = next((x for x in a.conditions if x.id == condition_id), None)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "condition_not_found"})
    if body.waive and not p.can("lending:approve"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "permission_denied", "permission": "lending:approve"})
    try:
        svc.satisfy_condition(db, a, c, body, p.membership.id, p.user.full_name)
    except svc.LendingError as e:
        raise _err(e)
    db.commit()
    return svc.detail(db, a)
