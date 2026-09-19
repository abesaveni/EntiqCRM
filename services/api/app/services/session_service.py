"""Builds the /me payload and issues token pairs. Shared by signup, login, refresh, switch-tenant."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.core import entitlements, rbac
from app.core.config import settings
from app.core.security import issue_access_token, new_opaque_token, utcnow
from app.core.tenancy import platform_scope, tenant_scope
from app.models.identity import Membership, ModuleGrant, RefreshToken, User
from app.models.tenant import Tenant


def issue_pair(db: Session, user: User, tenant: Tenant, membership: Membership, user_agent: str | None = None) -> schemas.TokenPair:
    access, _jti, exp = issue_access_token(user_id=user.id, tenant_id=tenant.id, role=membership.role, is_operator=user.is_operator)
    raw, h = new_opaque_token()
    with platform_scope():
        db.add(RefreshToken(user_id=user.id, tenant_id=tenant.id, token_hash=h, created_at=utcnow(),
                            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), user_agent=(user_agent or "")[:300]))
        db.flush()
    return schemas.TokenPair(access_token=access, refresh_token=raw, expires_at=exp)


def build_session(db: Session, user: User, tenant: Tenant, membership: Membership) -> schemas.SessionOut:
    with tenant_scope(tenant.id):
        with platform_scope():
            grants = sorted(g.module_key for g in db.execute(select(ModuleGrant).where(ModuleGrant.membership_id == membership.id)).scalars())
        subs = entitlements.subscriptions_for(db, tenant.id)
        ent = entitlements.entitlement_map(db, tenant)
    base = settings.BASE_PLAN_PRICE_CENTS
    return schemas.SessionOut(
        user=schemas.UserOut(id=user.id, email=user.email, full_name=user.full_name, is_operator=user.is_operator, email_verified=user.email_verified_at is not None),
        tenant=schemas.TenantOut(**{c: getattr(tenant, c) for c in schemas.TenantOut.model_fields}),
        role=membership.role,
        granted_modules=grants,
        permissions=sorted(rbac.permissions_for(membership.role, set(grants))),
        subscriptions=[schemas.SubscriptionOut(**{c: getattr(s, c) for c in schemas.SubscriptionOut.model_fields}) for s in subs],
        entitlements=ent,
        read_only=entitlements.tenant_is_read_only(tenant),
        pricing=schemas.PricingOut(base_plan_cents=base, gst_rate_bps=settings.GST_RATE_BPS,
                                   base_plan_inc_gst_cents=round(base * (10_000 + settings.GST_RATE_BPS) / 10_000), trial_days=settings.TRIAL_DAYS, require_card=settings.REQUIRE_CARD_AT_SIGNUP, free_mode=settings.free_mode),
    )


def pricing_out() -> schemas.PricingOut:
    """The plan as this server is configured — read by the signup page before any session exists."""
    base = settings.BASE_PLAN_PRICE_CENTS
    return schemas.PricingOut(base_plan_cents=base, gst_rate_bps=settings.GST_RATE_BPS,
                              base_plan_inc_gst_cents=round(base * (10_000 + settings.GST_RATE_BPS) / 10_000),
                              trial_days=settings.TRIAL_DAYS, require_card=settings.REQUIRE_CARD_AT_SIGNUP, free_mode=settings.free_mode)


def tenant_choices(db: Session, user: User) -> list[schemas.TenantChoice]:
    with platform_scope():
        rows = db.execute(
            select(Membership, Tenant).join(Tenant, Tenant.id == Membership.tenant_id)
            .where(Membership.user_id == user.id, Membership.status == "active").order_by(Tenant.name)
        ).all()
    return [schemas.TenantChoice(id=t.id, name=t.name, slug=t.slug, role=m.role, status=t.status) for m, t in rows]


def slugify(name: str, db: Session) -> str:
    import re
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "practice"
    slug, n = base, 2
    with platform_scope():
        while db.execute(select(Tenant.id).where(Tenant.slug == slug)).first() is not None:
            slug, n = f"{base}-{n}", n + 1
    return slug


def uuid_or_none(v: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(v) if v else None
    except ValueError:
        return None
