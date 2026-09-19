"""EnTIQ Start — module 03. Practice routes behind require_module('start'); prospect routes are public and tokened."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.core.limiter import limiter
from app.modules.start import schemas as S
from app.modules.start import service as svc
from app.modules.start.models import Onboarding, ServiceOffering
from app.services import document_service
from app.services.crm_service import member_names

router = APIRouter(prefix="/start", tags=["start"])
public = APIRouter(prefix="/start/public", tags=["start-public"])
view = require_module("start")
edit = require_module("start", write=True)


def _onb(db: Session, onboarding_id: uuid.UUID) -> Onboarding:
    o = db.get(Onboarding, onboarding_id)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "onboarding_not_found"})
    return o


def _stage_http(e: svc.StageError) -> HTTPException:
    code = {"stage_order": 409, "already_completed": 409, "closed": 409, "onboarding_exists": 409, "client_not_found": 404, "unknown_document_request": 404}.get(e.error, 400)
    return HTTPException(code, detail={"error": e.error, "message": e.message})


# ------------------------------------------------------------------ practice
@router.get("/overview", response_model=S.OverviewOut)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.overview(db)


@router.get("/onboardings", response_model=list[S.OnboardingOut])
def list_onboardings(status_: str | None = Query(None, alias="status"), open_only: bool = Query(True, alias="open"), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Onboarding)
    if status_:
        stmt = stmt.where(Onboarding.status == status_)
    elif open_only:
        stmt = stmt.where(Onboarding.status.notin_(["activated", "withdrawn"]))
    rows = db.execute(stmt.order_by(Onboarding.updated_at.desc())).scalars().all()
    names = member_names(db, {o.owner_membership_id for o in rows})
    return [svc.out(db, o, names) for o in rows]


@router.post("/onboardings", response_model=S.OnboardingDetail, status_code=status.HTTP_201_CREATED)
def create_onboarding(body: S.OnboardingIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:invite")), db: Session = Depends(get_db)):
    try:
        o, url = svc.create(db, p.tenant, body, p.membership.id, p.user.full_name)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    db.refresh(o)
    return svc.detail(db, o, url)


@router.get("/onboardings/{onboarding_id}", response_model=S.OnboardingDetail)
def get_onboarding(onboarding_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.detail(db, _onb(db, onboarding_id))


@router.post("/onboardings/{onboarding_id}/invite", response_model=S.OnboardingDetail)
def reinvite(onboarding_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:invite")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        url = svc.invite(db, p.tenant, o, p.membership.id, p.user.full_name)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o, url)


@router.post("/onboardings/{onboarding_id}/withdraw", response_model=S.OnboardingDetail)
def withdraw(onboarding_id: uuid.UUID, body: S.WithdrawIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.withdraw(db, o, body.reason, p.membership.id, p.user.full_name)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


# Practice may complete the prospect stages on their behalf (phone onboarding, walk-in)
@router.post("/onboardings/{onboarding_id}/stages/2", response_model=S.OnboardingDetail)
def s2(onboarding_id: uuid.UUID, body: S.EntityDetailsIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.complete_entity_details(db, o, body, p.user.full_name, p.membership.id)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/stages/3", response_model=S.OnboardingDetail)
def s3(onboarding_id: uuid.UUID, body: S.QuestionnaireIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.complete_questionnaire(db, o, body, p.user.full_name)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/documents/{req_key}/verify", response_model=S.OnboardingDetail)
def verify_doc(onboarding_id: uuid.UUID, req_key: str, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.verify_document(db, o, req_key, p.user.full_name)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/stages/4", response_model=S.OnboardingDetail)
def s4(onboarding_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.complete_documents(db, o, p.user.full_name, practice=True)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/stages/5", response_model=S.OnboardingDetail)
def s5(onboarding_id: uuid.UUID, body: S.RelatedPartiesIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.complete_related_parties(db, o, body, p.user.full_name, p.membership.id)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/stages/6", response_model=S.OnboardingDetail)
def s6(onboarding_id: uuid.UUID, body: S.ServiceSelectionIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.complete_service_selection(db, o, body, p.user.full_name)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/proposal", response_model=S.OnboardingDetail)
def issue_proposal(onboarding_id: uuid.UUID, body: S.ProposalIssueIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.issue_proposal(db, o, body, p.user.full_name, p.membership.id)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/stages/7", response_model=S.OnboardingDetail)
def s7(onboarding_id: uuid.UUID, body: S.ProposalAcceptIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    """Record acceptance given verbally/in writing, on the prospect's behalf."""
    o = _onb(db, onboarding_id)
    try:
        svc.accept_proposal(db, o, body, p.user.full_name)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/stages/8", response_model=S.OnboardingDetail)
def s8(onboarding_id: uuid.UUID, body: S.EngagementPrepIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.prepare_engagement(db, p.tenant, o, body, p.membership.id, p.user.full_name)
    except (svc.StageError, ValueError) as e:
        raise _stage_http(e) if isinstance(e, svc.StageError) else HTTPException(400, detail={"error": "invalid_agreement", "message": str(e)})
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/gates/run", response_model=S.OnboardingDetail)
def run_gates(onboarding_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.run_gates(db, p.tenant, o, p.user.full_name)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/mandate", response_model=S.OnboardingDetail)
def mandate(onboarding_id: uuid.UUID, body: S.MandateIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.record_mandate(db, o, body, p.user.full_name)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/stages/10", response_model=S.OnboardingDetail)
def s10(onboarding_id: uuid.UUID, body: S.AcceptanceIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:accept")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.accept_internally(db, o, body, p.membership.id, p.user.full_name)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


@router.post("/onboardings/{onboarding_id}/stages/11", response_model=S.OnboardingDetail)
def s11(onboarding_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:activate")), db: Session = Depends(get_db)):
    o = _onb(db, onboarding_id)
    try:
        svc.activate(db, p.tenant, o, p.membership.id, p.user.full_name)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.detail(db, o)


# ------------------------------------------------------------------ catalogue
@router.get("/services", response_model=list[S.ServiceOut])
def list_services(include_inactive: bool = False, p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(ServiceOffering).order_by(ServiceOffering.sort, ServiceOffering.name)
    if not include_inactive:
        stmt = stmt.where(ServiceOffering.is_active.is_(True))
    return [svc.service_out(s) for s in db.execute(stmt).scalars().all()]


@router.post("/services/defaults", response_model=list[S.ServiceOut])
def seed_services(p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    svc.seed_default_services(db, p.tenant.id)
    db.commit()
    return [svc.service_out(s) for s in db.execute(select(ServiceOffering).order_by(ServiceOffering.sort)).scalars().all()]


@router.post("/services", response_model=S.ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(body: S.ServiceIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    s = ServiceOffering(tenant_id=p.tenant.id, **body.model_dump())
    db.add(s)
    db.commit()
    return svc.service_out(s)


@router.put("/services/{service_id}", response_model=S.ServiceOut)
def update_service(service_id: uuid.UUID, body: S.ServiceIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("start:review")), db: Session = Depends(get_db)):
    s = db.get(ServiceOffering, service_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "service_not_found"})
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return svc.service_out(s)


# ------------------------------------------------------------------ prospect (public, tokened)
def _load(db: Session, token: str):
    try:
        return svc.load_by_token(db, token)
    except svc.TokenError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND if str(e) == "invalid_link" else status.HTTP_410_GONE, detail={"error": str(e)})


@public.get("/{token}", response_model=S.PublicView)
@limiter.limit("60/minute")
def public_view(request: Request, token: str, db: Session = Depends(get_db)):
    o, t = _load(db, token)
    svc.mark_opened(db, o)
    db.commit()
    return svc.public_view(db, o, t)


def _public_stage(db: Session, token: str, fn):
    o, t = _load(db, token)
    try:
        fn(o, t)
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.public_view(db, o, t)


@public.post("/{token}/stages/2", response_model=S.PublicView)
@limiter.limit("30/minute")
def p2(request: Request, token: str, body: S.EntityDetailsIn, db: Session = Depends(get_db)):
    return _public_stage(db, token, lambda o, t: svc.complete_entity_details(db, o, body, "Prospect"))


@public.post("/{token}/stages/3", response_model=S.PublicView)
@limiter.limit("30/minute")
def p3(request: Request, token: str, body: S.QuestionnaireIn, db: Session = Depends(get_db)):
    return _public_stage(db, token, lambda o, t: svc.complete_questionnaire(db, o, body, "Prospect"))


@public.post("/{token}/documents/{req_key}", response_model=S.PublicView)
@limiter.limit("30/minute")
async def p4_upload(request: Request, token: str, req_key: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    o, t = _load(db, token)
    data = await file.read()
    try:
        d = document_service.store(db, tenant_id=o.tenant_id, data=data, filename=file.filename or "upload", content_type=file.content_type, client_id=o.client_id, module_key="start", kind="onboarding",
                                   uploaded_by_membership_id=None, actor_label="Prospect", description=f"Onboarding: {req_key}")
        svc.attach_document(db, o, req_key, d, "Prospect")
    except document_service.UploadRefused as e:
        raise HTTPException({"malware_detected": 422, "file_too_large": 413, "scan_unavailable": 503}.get(e.error, 400), detail={"error": e.error, **e.extra})
    except svc.StageError as e:
        raise _stage_http(e)
    db.commit()
    return svc.public_view(db, o, t)


@public.post("/{token}/stages/4", response_model=S.PublicView)
@limiter.limit("30/minute")
def p4(request: Request, token: str, db: Session = Depends(get_db)):
    return _public_stage(db, token, lambda o, t: svc.complete_documents(db, o, "Prospect", practice=False))


@public.post("/{token}/stages/5", response_model=S.PublicView)
@limiter.limit("30/minute")
def p5(request: Request, token: str, body: S.RelatedPartiesIn, db: Session = Depends(get_db)):
    return _public_stage(db, token, lambda o, t: svc.complete_related_parties(db, o, body, "Prospect"))


@public.post("/{token}/stages/6", response_model=S.PublicView)
@limiter.limit("30/minute")
def p6(request: Request, token: str, body: S.ServiceSelectionIn, db: Session = Depends(get_db)):
    return _public_stage(db, token, lambda o, t: svc.complete_service_selection(db, o, body, "Prospect"))


@public.post("/{token}/stages/7", response_model=S.PublicView)
@limiter.limit("30/minute")
def p7(request: Request, token: str, body: S.ProposalAcceptIn, db: Session = Depends(get_db)):
    return _public_stage(db, token, lambda o, t: svc.accept_proposal(db, o, body, "Prospect"))


@public.post("/{token}/mandate", response_model=S.PublicView)
@limiter.limit("30/minute")
def p_mandate(request: Request, token: str, body: S.MandateIn, db: Session = Depends(get_db)):
    return _public_stage(db, token, lambda o, t: svc.record_mandate(db, o, body, "Prospect"))
