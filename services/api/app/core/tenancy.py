"""
Tenant context and the scoped-model predicate.

The current tenant lives in a ContextVar set by the auth dependency AFTER the JWT
is verified. It is derived from the token's `tid` claim and never from a header,
query parameter or body — the principal decides the tenant, not the request.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_current_tenant: ContextVar[uuid.UUID | None] = ContextVar("entiq_tenant", default=None)
_bypass: ContextVar[bool] = ContextVar("entiq_tenant_bypass", default=False)


class TenantContextMissing(RuntimeError):
    """A tenant-scoped query ran with no tenant in context. We fail closed."""


class TenantIsolationError(RuntimeError):
    """A write would create or move a row into another tenant."""


def current_tenant_id() -> uuid.UUID | None:
    return _current_tenant.get()


def bypass_active() -> bool:
    return _bypass.get()


def set_tenant(tenant_id: uuid.UUID | None) -> None:
    _current_tenant.set(tenant_id)


@contextmanager
def tenant_scope(tenant_id: uuid.UUID) -> Iterator[None]:
    """Run a block as a tenant (services, jobs, tests)."""
    token = _current_tenant.set(tenant_id)
    try:
        yield
    finally:
        _current_tenant.reset(token)


@contextmanager
def platform_scope() -> Iterator[None]:
    """
    Run a block with the tenant filter OFF. Reserved for the platform plane
    (operator console, lifecycle jobs, auth bootstrap). Every use is a deliberate,
    reviewable exception — grep for `platform_scope(` to audit them.
    """
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)


# Tables that carry `tenant_id` but are intentionally global:
#  - memberships:    login must list a person's practices before any tenant is chosen
#  - refresh_tokens: bound to a user session, validated before tenant context exists
#  - audit_events:   append-only chain read by the platform plane; the tenant router
#                    filters explicitly. Rows for platform actions have tenant_id NULL.
#  - outbound_messages: the email delivery job runs with no tenant; platform mail has tenant_id NULL
TENANT_EXEMPT_TABLES: frozenset[str] = frozenset({"memberships", "refresh_tokens", "audit_events", "outbound_messages"})


def is_tenant_scoped(cls: Any) -> bool:
    table = getattr(cls, "__tablename__", None)
    if not table or table in TENANT_EXEMPT_TABLES:
        return False
    cols = getattr(cls, "__table__", None)
    return cols is not None and "tenant_id" in cols.c
