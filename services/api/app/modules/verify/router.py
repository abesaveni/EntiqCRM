"""EnTIQ Verify — module 04. Every staff route sits behind require_module('verify'); the provider webhook is public + signed."""
from __future__ import annotations

import hashlib
import hmac
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.core.tenancy import platform_scope
from app.models.crm import Client
from app.modules.verify import schemas as S
from app.modules.verify import service as svc
from app.modules.verify.models import RiskAssessment, Screening, Verification
from app.services.crm_service import client_name_map, member_names

router = APIRouter(prefix="/verify", tags=["verify"])
view = require_module("verify")
run = require_module("verify", write=True)


def _client(db: Session, client_id: uuid.UUID) -> Client:
    c = db.get(Client, client_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "client_not_found"})
    return c


@router.get("/overview", response_model=S.OverviewOut)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.overview(db)


@router.get("/clients/{client_id}", response_model=S.ClientVerifyOut)
def client_view(client_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.client_view(db, _client(db, client_id))


# ------------------------------------------------------------------ identity
@router.post("/clients/{client_id}/verifications", response_model=S.VerificationOut, status_code=status.HTTP_201_CREATED)
def start_verification(client_id: uuid.UUID, body: S.StartVerificationIn, p: Principal = Depends(run), _perm: Principal = Depends(require_permission("verify:run")), db: Session = Depends(get_db)):
    try:
        v = svc.start_verification(db, _client(db, client_id), body, p.membership.id, p.user.full_name)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_request", "message": str(e)})
    db.commit()
    return svc.verification_out(v, {p.membership.id: p.user.full_name})


@router.get("/verifications", response_model=list[S.VerificationOut])
def list_verifications(status_: str | None = Query(None, alias="status"), limit: int = Query(100, ge=1, le=500), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Verification)
    if status_:
        stmt = stmt.where(Verification.status == status_)
    rows = db.execute(stmt.order_by(Verification.created_at.desc()).limit(limit)).scalars().all()
    names = member_names(db, {v.started_by_membership_id for v in rows})
    return [svc.verification_out(v, names) for v in rows]


@router.post("/verifications/{verification_id}/refresh", response_model=S.VerificationOut)
def refresh(verification_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    v = db.get(Verification, verification_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    svc.refresh_verification(db, v)
    db.commit()
    return svc.verification_out(v, member_names(db, {v.started_by_membership_id}))


@router.post("/verifications/{verification_id}/cancel", response_model=S.VerificationOut)
def cancel(verification_id: uuid.UUID, p: Principal = Depends(run), _perm: Principal = Depends(require_permission("verify:run")), db: Session = Depends(get_db)):
    v = db.get(Verification, verification_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if v.status in ("pending", "in_progress"):
        v.status = "cancelled"
        db.commit()
    return svc.verification_out(v, member_names(db, {v.started_by_membership_id}))


# ------------------------------------------------------------------ screening
@router.post("/clients/{client_id}/screen", response_model=S.ScreeningOut, status_code=status.HTTP_201_CREATED)
def screen(client_id: uuid.UUID, body: S.ScreenIn, p: Principal = Depends(run), _perm: Principal = Depends(require_permission("verify:run")), db: Session = Depends(get_db)):
    s = svc.screen(db, _client(db, client_id), body, p.membership.id, p.user.full_name)
    db.commit()
    return svc.screening_out(s, {})


@router.get("/screenings", response_model=list[S.ScreeningOut])
def list_screenings(status_: str | None = Query(None, alias="status"), review_queue: bool = False, limit: int = Query(100, ge=1, le=500), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Screening)
    if review_queue:
        stmt = stmt.where(Screening.status == "potential_match", Screening.review_decision.is_(None))
    elif status_:
        stmt = stmt.where(Screening.status == status_)
    rows = db.execute(stmt.order_by(Screening.screened_at.desc()).limit(limit)).scalars().all()
    return [svc.screening_out(s, member_names(db, {s.reviewed_by_membership_id for s in rows}), client_name_map(db, {s.client_id for s in rows})) for s in rows]


@router.post("/screenings/{screening_id}/review", response_model=S.ScreeningOut)
def review(screening_id: uuid.UUID, body: S.ReviewIn, p: Principal = Depends(run), _perm: Principal = Depends(require_permission("verify:review")), db: Session = Depends(get_db)):
    s = db.get(Screening, screening_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if s.status not in ("potential_match", "confirmed_match", "false_positive"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "nothing_to_review"})
    svc.review_screening(db, s, body, p.membership.id, p.user.full_name)
    # A decision changes the client's risk; re-assess so the rating on the record is never stale.
    svc.assess_risk(db, _client(db, s.client_id), S.AssessIn(notes=f"Re-assessed after screening review ({body.decision})"), p.membership.id, p.user.full_name)
    db.commit()
    return svc.screening_out(s, {p.membership.id: p.user.full_name})


# ------------------------------------------------------------------ risk
@router.post("/clients/{client_id}/assess", response_model=S.RiskOut, status_code=status.HTTP_201_CREATED)
def assess(client_id: uuid.UUID, body: S.AssessIn, p: Principal = Depends(run), _perm: Principal = Depends(require_permission("verify:approve")), db: Session = Depends(get_db)):
    r = svc.assess_risk(db, _client(db, client_id), body, p.membership.id, p.user.full_name)
    db.commit()
    return svc.risk_out(r, {p.membership.id: p.user.full_name})


@router.get("/clients/{client_id}/risk-history", response_model=list[S.RiskOut])
def risk_history(client_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    _client(db, client_id)
    rows = db.execute(select(RiskAssessment).where(RiskAssessment.client_id == client_id).order_by(RiskAssessment.assessed_at.desc())).scalars().all()
    return [svc.risk_out(r, member_names(db, {r.assessed_by_membership_id for r in rows})) for r in rows]


@router.get("/reviews-due", response_model=list[S.ReviewDueOut])
def reviews_due(days: int = Query(30, ge=0, le=365), p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.reviews_due(db, days)


# ------------------------------------------------------------------ provider webhook (public, signed)
@router.post("/webhooks/didit", status_code=status.HTTP_202_ACCEPTED, include_in_schema=False)
async def didit_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if settings.DIDIT_WEBHOOK_SECRET:
        sig = request.headers.get("x-signature") or request.headers.get("x-didit-signature") or ""
        expected = hmac.new(settings.DIDIT_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig.lower(), expected.lower()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"error": "bad_signature"})
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_json"})
    ref = str(payload.get("session_id") or payload.get("id") or "")
    raw_status = str(payload.get("status") or (payload.get("decision") or {}).get("status") or "").lower()
    mapped = {"approved": "verified", "verified": "verified", "declined": "failed", "rejected": "failed", "expired": "expired", "abandoned": "expired"}.get(raw_status, "in_progress")
    with platform_scope():  # no tenant on a webhook; the verification row carries it
        v = svc.apply_webhook(db, "didit", ref, mapped, {"raw_status": raw_status, "webhook": True})
        db.commit()
    return {"received": True, "matched": v is not None}
