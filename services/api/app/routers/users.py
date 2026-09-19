"""Practice HQ: user directory, invitations, the access matrix (module grants), roles."""
from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.core import audit
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, get_principal, require_permission, require_writable
from app.core.security import new_opaque_token, utcnow
from app.core.tenancy import platform_scope
from app.models.identity import Invitation, Membership, ModuleGrant, User
from app.modules import registry

router = APIRouter(prefix="/users", tags=["users"])


def _members(db: Session, tenant_id: uuid.UUID) -> list[schemas.MemberOut]:
    with platform_scope():
        rows = db.execute(select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.tenant_id == tenant_id).order_by(User.full_name)).all()
    grants = {}
    for g in db.execute(select(ModuleGrant)).scalars():  # tenant-filtered automatically
        grants.setdefault(g.membership_id, []).append(g.module_key)
    return [schemas.MemberOut(membership_id=m.id, user_id=u.id, email=u.email, full_name=u.full_name, role=m.role, status=m.status, job_title=m.job_title,
                              modules=sorted(grants.get(m.id, [])), joined_at=m.joined_at, last_login_at=u.last_login_at) for m, u in rows]


@router.get("", response_model=list[schemas.MemberOut])
def directory(p: Principal = Depends(require_permission("hq:users")), db: Session = Depends(get_db)):
    return _members(db, p.tenant.id)


@router.post("/invite", response_model=schemas.InviteOut, status_code=status.HTTP_201_CREATED)
def invite(body: schemas.InviteIn, p: Principal = Depends(require_permission("hq:users")), _w: Principal = Depends(require_writable), db: Session = Depends(get_db)):
    bad = [k for k in body.modules if not registry.exists(k)]
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "unknown_modules", "modules": bad})
    with platform_scope():
        existing = db.execute(select(Membership).join(User).where(User.email == body.email, Membership.tenant_id == p.tenant.id, Membership.status == "active")).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "already_a_member"})
    raw, h = new_opaque_token()
    inv = Invitation(tenant_id=p.tenant.id, email=body.email, role=body.role, module_keys=",".join(sorted(set(body.modules))), token_hash=h,
                     invited_by=p.user.id, expires_at=utcnow() + timedelta(hours=72))
    db.add(inv)
    db.flush()
    audit.record(db, action="invitation.sent", actor_user_id=p.user.id, tenant_id=p.tenant.id, target_type="invitation", target_id=str(inv.id), detail={"email": body.email, "role": body.role, "modules": body.modules})
    db.commit()
    # TODO(M4): send via packages/notify once SMTP is wired. Until then, non-production returns the link.
    url = f"{settings.APP_PUBLIC_URL}/accept-invite?token={raw}" if not settings.is_production else None
    return schemas.InviteOut(invitation_id=inv.id, email=inv.email, expires_at=inv.expires_at, accept_url=url)


@router.patch("/{membership_id}/grants", response_model=schemas.MemberOut)
def set_grants(membership_id: uuid.UUID, body: schemas.GrantsPatch, p: Principal = Depends(require_permission("hq:access")), _w: Principal = Depends(require_writable), db: Session = Depends(get_db)):
    bad = [k for k in body.modules if not registry.exists(k)]
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "unknown_modules", "modules": bad})
    with platform_scope():
        m = db.get(Membership, membership_id)
    if m is None or m.tenant_id != p.tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    current = {g.module_key: g for g in db.execute(select(ModuleGrant).where(ModuleGrant.membership_id == m.id)).scalars()}
    want = set(body.modules)
    for key in set(current) - want:
        db.delete(current[key])
    for key in want - set(current):
        db.add(ModuleGrant(membership_id=m.id, tenant_id=p.tenant.id, module_key=key, granted_by=p.user.id, granted_at=utcnow()))
    audit.record(db, action="access.changed", actor_user_id=p.user.id, tenant_id=p.tenant.id, target_type="membership", target_id=str(m.id), detail={"modules": sorted(want)})
    db.commit()
    return next(x for x in _members(db, p.tenant.id) if x.membership_id == m.id)


@router.patch("/{membership_id}", response_model=schemas.MemberOut)
def patch_member(membership_id: uuid.UUID, body: schemas.MemberPatch, p: Principal = Depends(require_permission("hq:users")), _w: Principal = Depends(require_writable), db: Session = Depends(get_db)):
    with platform_scope():
        m = db.get(Membership, membership_id)
        if m is None or m.tenant_id != p.tenant.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        if m.role == "owner" and (body.role and body.role != "owner" or body.status == "disabled"):
            owners = db.execute(select(Membership).where(Membership.tenant_id == p.tenant.id, Membership.role == "owner", Membership.status == "active")).scalars().all()
            if len(owners) <= 1:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "last_owner"})
        if body.role == "owner" and p.role != "owner":
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "only_owners_promote_owners"})
        changes = body.model_dump(exclude_none=True)
        for k, v in changes.items():
            setattr(m, k, v)
        if body.status == "disabled":
            u = db.get(User, m.user_id)
            # Ending live sessions for this practice only would need per-tenant token scoping; for M2 we end all.
            u.tokens_valid_from = utcnow()
        audit.record(db, action="member.updated", actor_user_id=p.user.id, tenant_id=p.tenant.id, target_type="membership", target_id=str(m.id), detail=changes)
        db.commit()
    return next(x for x in _members(db, p.tenant.id) if x.membership_id == m.id)
