"""
FastAPI dependencies — the request-time enforcement chain, in the order the architecture
diagram draws it: authenticate → tenant context → require_module → require_permission.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import entitlements, rbac
from app.core.database import bind_tenant, get_db
from app.core.security import TokenError, decode_access_token, utcnow
from app.core.tenancy import platform_scope, set_tenant
from app.models.identity import Membership, ModuleGrant, RevokedToken, User
from app.models.tenant import Tenant
from app.modules import registry

bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    user: User
    tenant: Tenant
    membership: Membership
    jti: str
    granted_modules: set[str] = field(default_factory=set)

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def is_operator(self) -> bool:
        return self.user.is_operator

    def can(self, permission: str) -> bool:
        return rbac.has_permission(self.role, self.granted_modules, permission)


def _unauth(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if creds is None:
        raise _unauth()
    try:
        claims = decode_access_token(creds.credentials)
    except TokenError as e:
        raise _unauth(f"Token {e}") from e

    user_id, tenant_id, jti = uuid.UUID(claims["sub"]), uuid.UUID(claims["tid"]), claims["jti"]

    with platform_scope():
        if db.get(RevokedToken, jti) is not None:
            raise _unauth("Token revoked")
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise _unauth("Account unavailable")
        if user.tokens_valid_from and claims["iat"] < int(user.tokens_valid_from.timestamp()):
            raise _unauth("Session ended")
        membership = db.execute(
            select(Membership).where(Membership.user_id == user_id, Membership.tenant_id == tenant_id, Membership.status == "active")
        ).scalar_one_or_none()
        if membership is None:
            raise _unauth("No active membership for this practice")
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise _unauth("Practice not found")
        grants = {g.module_key for g in db.execute(select(ModuleGrant).where(ModuleGrant.membership_id == membership.id)).scalars()}

    # From here on, every tenant-scoped query in this request is filtered to this tenant.
    # Bound to the Session (shared by every dependency and the endpoint) — see database._effective_tenant.
    bind_tenant(db, tenant.id)
    set_tenant(tenant.id)
    request.state.principal = Principal(user=user, tenant=tenant, membership=membership, jti=jti, granted_modules=grants)
    return request.state.principal


def require_role(*roles: str):
    def _dep(p: Principal = Depends(get_principal)) -> Principal:
        if p.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Requires role: {', '.join(roles)}")
        return p
    return _dep


def require_permission(permission: str):
    def _dep(p: Principal = Depends(get_principal)) -> Principal:
        if not p.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "permission_denied", "permission": permission})
        return p
    return _dep


def require_module(module_key: str, *, write: bool = False):
    """
    The entitlement gate. 403 carries an upsell payload the shell renders as "Add <Module>".
    Staff must also hold a module grant; owners/admins hold every module the tenant has.
    `write=True` additionally refuses suspended (read-only) tenants.
    """
    def _dep(p: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> Principal:
        try:
            entitlements.check(db, p.tenant, module_key)
        except entitlements.NotEntitled as e:
            m = registry.get_module(module_key) if registry.exists(module_key) else None
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "module_not_subscribed" if e.reason == "not_subscribed" else e.reason,
                    "module": module_key,
                    "upsell": {"name": m["name"], "shortName": m["shortName"], "outcome": m["outcome"], "pricing": m["pricing"], "addPath": f"/hq/modules/{module_key}"} if m else None,
                },
            ) from e
        if p.role == "staff" and not registry.is_base(module_key) and module_key not in p.granted_modules:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "module_not_granted", "module": module_key})
        if write and entitlements.tenant_is_read_only(p.tenant):
            raise HTTPException(status.HTTP_423_LOCKED, detail={"error": "tenant_read_only", "status": p.tenant.status})
        return p
    return _dep


def require_writable(p: Principal = Depends(get_principal)) -> Principal:
    """Blocks writes for suspended tenants — records intact, access read-only."""
    if entitlements.tenant_is_read_only(p.tenant):
        raise HTTPException(status.HTTP_423_LOCKED, detail={"error": "tenant_read_only", "status": p.tenant.status})
    return p


def require_operator(p: Principal = Depends(get_principal)) -> Principal:
    if not p.is_operator:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="EnTIQ operators only")
    return p
