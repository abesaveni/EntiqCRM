"""
Entitlement resolution. One record (tenant_subscriptions) — three enforcement points
(shell nav, API middleware, billing meter). This module is the API one.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import utcnow
from app.models.common import ACCESS_STATES, READONLY_STATES
from app.models.subscription import TenantSubscription
from app.models.tenant import Tenant
from app.modules import registry


class NotEntitled(Exception):
    def __init__(self, module_key: str, reason: str):
        self.module_key = module_key
        self.reason = reason
        super().__init__(f"{module_key}: {reason}")


class ReadOnly(Exception):
    pass


def tenant_has_access(t: Tenant) -> bool:
    return t.status in ACCESS_STATES


def tenant_is_read_only(t: Tenant) -> bool:
    return t.status in READONLY_STATES


def subscriptions_for(db: Session, tenant_id: uuid.UUID) -> list[TenantSubscription]:
    return list(db.execute(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)).scalars())


def entitlement_map(db: Session, tenant: Tenant) -> dict[str, bool]:
    subs = {s.module_key: s for s in subscriptions_for(db, tenant.id)}
    out: dict[str, bool] = {}
    for m in registry.all_modules():
        out[m["key"]] = _entitled(tenant, subs.get(m["key"]), m["key"])
    return out


def _entitled(tenant: Tenant, sub: TenantSubscription | None, key: str) -> bool:
    if tenant.status not in ACCESS_STATES and tenant.status not in READONLY_STATES:
        return False
    if registry.is_base(key):
        return True
    return sub is not None and (sub.status in ACCESS_STATES or sub.status in READONLY_STATES)


def check(db: Session, tenant: Tenant, module_key: str) -> None:
    """Raise NotEntitled if the tenant may not reach `module_key`."""
    if not registry.exists(module_key):
        raise NotEntitled(module_key, "unknown_module")
    if tenant.status not in ACCESS_STATES and tenant.status not in READONLY_STATES:
        raise NotEntitled(module_key, f"tenant_{tenant.status}")
    if registry.is_base(module_key):
        return
    sub = db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id, TenantSubscription.module_key == module_key)
    ).scalar_one_or_none()
    if sub is None:
        raise NotEntitled(module_key, "not_subscribed")
    if sub.status not in ACCESS_STATES and sub.status not in READONLY_STATES:
        raise NotEntitled(module_key, f"subscription_{sub.status}")


def provision_base_bundle(db: Session, tenant: Tenant) -> list[TenantSubscription]:
    now = utcnow()
    rows = []
    for key in (*registry.BASE_BUNDLE, *registry.PLATFORM_SERVICES):
        rows.append(TenantSubscription(tenant_id=tenant.id, module_key=key, status="trialing", started_at=now, trial_ends_at=tenant.trial_ends_at))
    db.add_all(rows)
    db.flush()
    return rows


def subscribe(db: Session, tenant: Tenant, module_key: str, seats: int | None = None) -> list[str]:
    """Add a module plus its hard-dependency closure. Returns the keys actually added."""
    if not registry.exists(module_key):
        raise NotEntitled(module_key, "unknown_module")
    if not registry.purchasable(module_key):
        raise NotEntitled(module_key, "not_purchasable")
    if tenant_is_read_only(tenant) or not tenant_has_access(tenant):
        raise ReadOnly()
    existing = {s.module_key for s in subscriptions_for(db, tenant.id)}
    now = utcnow()
    added: list[str] = []
    for dep in registry.required_closure(module_key):
        if registry.is_base(dep) or dep in existing:
            continue
        db.add(TenantSubscription(tenant_id=tenant.id, module_key=dep, status="active", started_at=now, required_by=module_key))
        added.append(dep)
    if module_key not in existing:
        db.add(TenantSubscription(tenant_id=tenant.id, module_key=module_key, status="active", started_at=now, seats=seats,
                                  current_period_end=now + timedelta(days=30)))
        added.append(module_key)
    db.flush()
    return added


def unsubscribe(db: Session, tenant: Tenant, module_key: str) -> bool:
    """Cancel a module. Data is retained; the row is marked cancelled, not deleted. Base bundle cannot be removed here."""
    if registry.is_base(module_key):
        raise NotEntitled(module_key, "base_bundle_is_tenant_level")
    sub = db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id, TenantSubscription.module_key == module_key)
    ).scalar_one_or_none()
    if sub is None or sub.status == "cancelled":
        return False
    sub.status = "cancelled"
    sub.cancelled_at = utcnow()
    # A module that was only there because another required it goes with it.
    for dep in subscriptions_for(db, tenant.id):
        if dep.required_by == module_key and dep.status != "cancelled":
            dep.status = "cancelled"
            dep.cancelled_at = utcnow()
    db.flush()
    return True


def trial_end_for_new_tenant():
    return utcnow() + timedelta(days=settings.TRIAL_DAYS)
