"""EnTIQ Sign — module 05. Staff routes behind require_module('sign'); the signer routes are public, tokened and rate-limited."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.core.limiter import limiter
from app.core.tenancy import platform_scope
from app.modules.sign import schemas as S
from app.modules.sign import service as svc
from app.modules.sign.models import Agreement
from app.services.crm_service import client_name_map, member_names

router = APIRouter(prefix="/sign", tags=["sign"])
public = APIRouter(prefix="/sign/public", tags=["sign-public"])
view = require_module("sign")
edit = require_module("sign", write=True)


def _agreement(db: Session, agreement_id: uuid.UUID) -> Agreement:
    a = db.get(Agreement, agreement_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "agreement_not_found"})
    return a


def _ip(req: Request) -> str | None:
    return (req.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (req.client.host if req.client else None)


# ------------------------------------------------------------------ staff
@router.get("/overview", response_model=S.OverviewOut)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.overview(db)


@router.get("/agreements", response_model=list[S.AgreementOut])
def list_agreements(status_: str | None = Query(None, alias="status"), client_id: uuid.UUID | None = None, limit: int = Query(100, ge=1, le=500), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Agreement)
    if status_:
        stmt = stmt.where(Agreement.status == status_)
    if client_id:
        stmt = stmt.where(Agreement.client_id == client_id)
    rows = db.execute(stmt.order_by(Agreement.created_at.desc()).limit(limit)).scalars().all()
    names = member_names(db, {a.created_by_membership_id for a in rows})
    cn = client_name_map(db, {a.client_id for a in rows})
    return [svc.agreement_out(db, a, names, cn) for a in rows]


@router.post("/agreements", response_model=S.AgreementDetail, status_code=status.HTTP_201_CREATED)
def create_agreement(body: S.AgreementIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("sign:send")), db: Session = Depends(get_db)):
    try:
        a = svc.create(db, p.tenant, body, p.membership.id, p.user.full_name)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_agreement", "message": str(e)})
    db.commit()
    db.refresh(a)
    return svc.agreement_detail(db, a)


@router.get("/agreements/{agreement_id}", response_model=S.AgreementDetail)
def get_agreement(agreement_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.agreement_detail(db, _agreement(db, agreement_id))


@router.post("/agreements/{agreement_id}/send", response_model=S.AgreementDetail)
def send_agreement(agreement_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("sign:send")), db: Session = Depends(get_db)):
    a = _agreement(db, agreement_id)
    try:
        svc.send(db, p.tenant, a, p.membership.id, p.user.full_name)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "cannot_send", "message": str(e)})
    db.commit()
    return svc.agreement_detail(db, a)


@router.post("/agreements/{agreement_id}/remind", response_model=S.AgreementDetail)
def remind(agreement_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("sign:send")), db: Session = Depends(get_db)):
    a = _agreement(db, agreement_id)
    try:
        svc.send(db, p.tenant, a, p.membership.id, p.user.full_name, reminder=True)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "cannot_remind", "message": str(e)})
    db.commit()
    return svc.agreement_detail(db, a)


@router.post("/agreements/{agreement_id}/void", response_model=S.AgreementDetail)
def void_agreement(agreement_id: uuid.UUID, body: S.VoidIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("sign:void")), db: Session = Depends(get_db)):
    a = _agreement(db, agreement_id)
    try:
        svc.void(db, a, body.reason, p.membership.id, p.user.full_name)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "cannot_void", "message": str(e)})
    db.commit()
    return svc.agreement_detail(db, a)


@router.get("/agreements/{agreement_id}/verify-chain")
def verify_chain(agreement_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.verify_chain(db, _agreement(db, agreement_id))


@router.get("/agreements/{agreement_id}/certificate.pdf")
def certificate_pdf(agreement_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    a = _agreement(db, agreement_id)
    if a.status != "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "not_completed"})
    pdf = svc.certificate_pdf(a, p.tenant)
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="certificate-{a.id}.pdf"', "Cache-Control": "private, no-store"})


# ------------------------------------------------------------------ public signer surface
def _load(db: Session, token: str):
    try:
        return svc.load_by_token(db, token)
    except svc.TokenError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND if str(e) == "invalid_link" else status.HTTP_410_GONE, detail={"error": str(e)})


@public.get("/{token}", response_model=S.PublicSignerView)
@limiter.limit("60/minute")
def public_view(request: Request, token: str, db: Session = Depends(get_db)):
    s, a, t, d = _load(db, token)
    svc.record_view(db, s, a, _ip(request), request.headers.get("user-agent"))
    db.commit()
    return svc.public_view(db, s, a, t, d)


@public.get("/{token}/document")
@limiter.limit("30/minute")
def public_document(request: Request, token: str, db: Session = Depends(get_db)):
    s, a, t, d = _load(db, token)
    data = svc.document_bytes(d)
    return Response(content=data, media_type=d.content_type, headers={"Content-Disposition": f'inline; filename="{d.filename.replace(chr(34), "")}"', "X-Content-SHA256": d.sha256, "Cache-Control": "private, no-store"})


@public.post("/{token}/sign", response_model=S.PublicSignerView)
@limiter.limit("10/minute")
def public_sign(request: Request, token: str, body: S.PublicSignIn, db: Session = Depends(get_db)):
    s, a, t, d = _load(db, token)
    try:
        svc.sign(db, s, a, t, d, body, _ip(request), request.headers.get("user-agent"))
    except svc.TokenError as e:
        code = {"consent_required": 400, "identity_required": 403, "drawn_signature_must_be_png": 400}.get(str(e), 409)
        raise HTTPException(code, detail={"error": str(e)})
    db.commit()
    return svc.public_view(db, s, a, t, d)


@public.post("/{token}/decline", response_model=S.PublicSignerView)
@limiter.limit("10/minute")
def public_decline(request: Request, token: str, body: S.PublicDeclineIn, db: Session = Depends(get_db)):
    s, a, t, d = _load(db, token)
    try:
        svc.decline(db, s, a, t, body, _ip(request), request.headers.get("user-agent"))
    except svc.TokenError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": str(e)})
    db.commit()
    return svc.public_view(db, s, a, t, d)
