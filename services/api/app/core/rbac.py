"""
Role → permission mapping for the platform spine. Module-specific permission strings
(e.g. "verify:approve") arrive with each module's manifest; the spine grants them by
role until modules define finer templates.
"""
from __future__ import annotations

from app.modules import registry

# Practice HQ permissions live here because HQ is the spine's own surface.
HQ_PERMS = ("hq:view", "hq:subscriptions", "hq:users", "hq:access", "hq:integrations", "hq:settings", "hq:audit")

ROLE_BASE: dict[str, frozenset[str]] = {
    "owner": frozenset(HQ_PERMS),
    "admin": frozenset(p for p in HQ_PERMS if p != "hq:subscriptions"),  # admins run the practice; owners hold the card
    "staff": frozenset({"hq:view"}),
}


def permissions_for(role: str, granted_modules: set[str]) -> set[str]:
    """Everything a member may do: HQ perms by role + every permission of every module they hold."""
    perms = set(ROLE_BASE.get(role, frozenset()))
    modules = set(granted_modules) | (set(registry.BASE_BUNDLE) - {"hq"})  # CRM is base for every member
    if role in ("owner", "admin"):
        # Owners/admins hold every module the tenant has; staff hold what they are ticked for.
        modules |= {m["key"] for m in registry.all_modules()} | set(registry.PLATFORM_SERVICES)
    # Practice HQ and Control Centre permissions are ROLE-tiered (ROLE_BASE / operator flag) —
    # they must never arrive through module expansion, or every member could buy modules.
    modules -= {"hq", "control"}
    for key in modules:
        try:
            perms.update(registry.get_module(key)["permissions"])
        except KeyError:
            continue
    return perms


def has_permission(role: str, granted_modules: set[str], permission: str) -> bool:
    return permission in permissions_for(role, granted_modules)
