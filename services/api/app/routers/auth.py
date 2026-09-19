"""Sign-up, login, refresh, logout, tenant switch, invitation accept. Everything here runs BEFORE tenant context."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.core import audit, entitlements
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, get_principal
from app.core.limiter import limiter
from app.core.security import hash_password, hash_token, password_problems, utcnow, verify_password
from app.core.tenancy import platform_scope
from app.models.identity import Invitation, Membership, ModuleGrant, RefreshToken, RevokedToken, User
from app.models.tenant import Tenant
from app.services import session_service as svc

router = APIRouter(prefix="/auth", tags=["auth"])


def _ip(req: Request) -> str | None:
    return req.client.host if req.client else None


@router.post("/signup", response_model=schemas.LoginOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def signup(request: Request, body: schemas.SignUpIn, db: Session = Depends(get_db)):
    """
    Create practice + owner. Card is captured at signup, $0 charged; the tenant starts `trialing`
    with trial_ends_at = now + TRIAL_DAYS. Base bundle rows are provisioned like any other module.
    """
    if problems := password_problems(body.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"error": "weak_password", "needs": problems})
    with platform_scope():
        if db.execute(select(User.id).where(User.email == body.email)).first():
            raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "email_in_use", "hint": "Sign in and create another practice from your account."})

        now = utcnow()
        tenant = Tenant(name=body.practice_name.strip(), slug=svc.slugify(body.practice_name, db), abn=(body.abn or "").strip() or None,
                        status="trialing", status_changed_at=now, trial_ends_at=entitlements.trial_end_for_new_tenant(),
                        card_on_file=True, card_brand=body.payment_method.brand, card_last4=body.payment_method.last4)
        user = User(email=body.email, password_hash=hash_password(body.password), full_name=body.full_name.strip(), last_login_at=now)
        db.add_all([tenant, user])
        db.flush()
        membership = Membership(user_id=user.id, tenant_id=tenant.id, role="owner", status="active", joined_at=now)
        db.add(membership)
        db.flush()
        entitlements.provision_base_bundle(db, tenant)

        audit.record(db, action="tenant.created", actor_user_id=user.id, tenant_id=tenant.id, target_type="tenant", target_id=str(tenant.id),
                     detail={"name": tenant.name, "trial_ends_at": tenant.trial_ends_at.isoformat(), "card_last4": tenant.card_last4}, ip=_ip(request))
        audit.record(db, action="user.signup", actor_user_id=user.id, tenant_id=tenant.id, target_type="user", target_id=str(user.id), detail={"email": user.email}, ip=_ip(request))
        tokens = svc.issue_pair(db, user, tenant, membership, request.headers.get("user-agent"))
        db.commit()
    return schemas.LoginOut(tokens=tokens, session=svc.build_session(db, user, tenant, membership))


@router.post("/login", response_model=schemas.LoginOut)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def login(request: Request, body: schemas.LoginIn, db: Session = Depends(get_db)):
    generic = HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"error": "invalid_credentials"})
    with platform_scope():
        user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
        if user is None or not user.is_active or not user.password_hash:
            raise generic
        if user.locked_until and user.locked_until > utcnow():
            raise HTTPException(status.HTTP_423_LOCKED, detail={"error": "account_locked", "until": user.locked_until.isoformat()})
        if not verify_password(body.password, user.password_hash):
            user.failed_login_count += 1
            if user.failed_login_count >= settings.LOGIN_MAX_FAILURES:
                user.locked_until = utcnow() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
                user.failed_login_count = 0
                audit.record(db, action="user.locked", actor_user_id=None, tenant_id=None, target_type="user", target_id=str(user.id), ip=_ip(request))
            db.commit()
            raise generic
        user.failed_login_count, user.locked_until, user.last_login_at = 0, None, utcnow()

        choices = svc.tenant_choices(db, user)
        if not choices:
            db.commit()
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "no_practice", "hint": "You are not a member of any practice."})
        chosen = None
        if body.tenant_id:
            chosen = next((c for c in choices if c.id == body.tenant_id), None)
            if chosen is None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "not_a_member"})
        elif len(choices) == 1:
            chosen = choices[0]
        if chosen is None:
            db.commit()
            return schemas.LoginOut(requires_tenant_selection=True, tenants=choices)

        tenant = db.get(Tenant, chosen.id)
        membership = db.execute(select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == tenant.id)).scalar_one()
        audit.record(db, action="user.login", actor_user_id=user.id, tenant_id=tenant.id, target_type="user", target_id=str(user.id), ip=_ip(request))
        tokens = svc.issue_pair(db, user, tenant, membership, request.headers.get("user-agent"))
        db.commit()
    return schemas.LoginOut(tokens=tokens, session=svc.build_session(db, user, tenant, membership))


@router.post("/refresh", response_model=schemas.TokenPair)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def refresh(request: Request, body: schemas.RefreshIn, db: Session = Depends(get_db)):
    """Rotating refresh: the presented token is revoked and a new pair issued."""
    with platform_scope():
        rt = db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token))).scalar_one_or_none()
        if rt is None or rt.revoked_at is not None or rt.expires_at < utcnow():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"error": "invalid_refresh_token"})
        user, tenant = db.get(User, rt.user_id), db.get(Tenant, rt.tenant_id)
        membership = db.execute(select(Membership).where(Membership.user_id == rt.user_id, Membership.tenant_id == rt.tenant_id, Membership.status == "active")).scalar_one_or_none()
        if user is None or tenant is None or membership is None or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"error": "session_ended"})
        rt.revoked_at = utcnow()
        tokens = svc.issue_pair(db, user, tenant, membership, request.headers.get("user-agent"))
        db.commit()
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: schemas.RefreshIn | None = None, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    with platform_scope():
        db.add(RevokedToken(jti=p.jti, expires_at=utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)))
        if body and body.refresh_token:
            rt = db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token))).scalar_one_or_none()
            if rt and rt.user_id == p.user.id:
                rt.revoked_at = utcnow()
        db.commit()


@router.post("/switch-tenant", response_model=schemas.LoginOut)
def switch_tenant(request: Request, body: schemas.SwitchTenantIn, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    with platform_scope():
        membership = db.execute(select(Membership).where(Membership.user_id == p.user.id, Membership.tenant_id == body.tenant_id, Membership.status == "active")).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "not_a_member"})
        tenant = db.get(Tenant, body.tenant_id)
        tokens = svc.issue_pair(db, p.user, tenant, membership, request.headers.get("user-agent"))
        db.commit()
    return schemas.LoginOut(tokens=tokens, session=svc.build_session(db, p.user, tenant, membership))


@router.get("/tenants", response_model=list[schemas.TenantChoice])
def my_tenants(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return svc.tenant_choices(db, p.user)


@router.post("/accept-invite", response_model=schemas.LoginOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def accept_invite(request: Request, body: schemas.AcceptInviteIn, db: Session = Depends(get_db)):
    if problems := password_problems(body.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"error": "weak_password", "needs": problems})
    with platform_scope():
        inv = db.execute(select(Invitation).where(Invitation.token_hash == hash_token(body.token))).scalar_one_or_none()
        if inv is None or inv.accepted_at is not None or inv.expires_at < utcnow():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_or_expired_invitation"})
        tenant = db.get(Tenant, inv.tenant_id)
        now = utcnow()
        user = db.execute(select(User).where(User.email == inv.email)).scalar_one_or_none()
        if user is None:
            user = User(email=inv.email, password_hash=hash_password(body.password), full_name=body.full_name.strip(), email_verified_at=now, last_login_at=now)
            db.add(user)
            db.flush()
        membership = db.execute(select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == tenant.id)).scalar_one_or_none()
        if membership is None:
            membership = Membership(user_id=user.id, tenant_id=tenant.id, role=inv.role, status="active", joined_at=now)
            db.add(membership)
            db.flush()
        else:
            membership.status, membership.role, membership.joined_at = "active", inv.role, now
        for key in [k for k in inv.module_keys.split(",") if k]:
            db.add(ModuleGrant(membership_id=membership.id, tenant_id=tenant.id, module_key=key, granted_by=inv.invited_by, granted_at=now))
        inv.accepted_at = now
        audit.record(db, action="invitation.accepted", actor_user_id=user.id, tenant_id=tenant.id, target_type="membership", target_id=str(membership.id), detail={"role": inv.role}, ip=_ip(request))
        tokens = svc.issue_pair(db, user, tenant, membership, request.headers.get("user-agent"))
        db.commit()
    return schemas.LoginOut(tokens=tokens, session=svc.build_session(db, user, tenant, membership))
