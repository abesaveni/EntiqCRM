"""
Engine, session and the FAIL-CLOSED tenant filter.

Two SQLAlchemy hooks enforce isolation centrally so no router can forget it:

  * `do_orm_execute` — every SELECT against a tenant-scoped model gets
    `WHERE tenant_id = <current tenant>` injected via with_loader_criteria.
    If there is no tenant in context and the query touches a scoped model, we
    raise instead of returning everything. (Ported from GrowKyc — the only
    implementation in the estate that failed closed.)

  * `before_flush` — a scoped row being inserted gets the current tenant stamped
    on it; a row whose tenant_id differs from the context is refused.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, with_loader_criteria
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.tenancy import (
    TenantContextMissing,
    TenantIsolationError,
    bypass_active,
    current_tenant_id,
    is_tenant_scoped,
)


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        eng = create_engine(url, echo=settings.SQL_ECHO, **kwargs)

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return eng
    return create_engine(url, echo=settings.SQL_ECHO, pool_pre_ping=True, pool_size=10, max_overflow=20, pool_recycle=3600)


engine = _make_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _effective_tenant(session: Session):
    """
    The tenant for this session. Preference: the Session's own binding (set by the auth
    dependency — FastAPI runs each sync dependency in a separate threadpool call with a
    COPY of the context, so a ContextVar set in `get_principal` would not reach the
    endpoint; the Session object is shared across them and so carries the tenant).
    Fallback: the ContextVar, for services, jobs and tests that use `tenant_scope()`.
    """
    return session.info.get("tenant_id") or current_tenant_id()


def _effective_bypass(session: Session) -> bool:
    return bool(session.info.get("bypass_tenant")) or bypass_active()


def bind_tenant(session: Session, tenant_id) -> None:
    session.info["tenant_id"] = tenant_id


# --------------------------------------------------------------------------- read filter
@event.listens_for(Session, "do_orm_execute")
def _tenant_read_filter(state):
    if not state.is_select or _effective_bypass(state.session):
        return
    tenant_id = _effective_tenant(state.session)
    scoped = [m.class_ for m in state.all_mappers if is_tenant_scoped(m.class_)]
    if not scoped:
        return
    if tenant_id is None:
        raise TenantContextMissing(
            f"Tenant-scoped query on {', '.join(c.__tablename__ for c in scoped)} with no tenant in context"
        )
    for cls in scoped:
        # A concrete SQL expression, deliberately NOT a lambda: SQLAlchemy caches lambda
        # criteria by code object and only tracks true closure variables, so a lambda
        # would bake in the first tenant it ever saw. (GrowKyc learned this the hard way.)
        state.statement = state.statement.options(
            with_loader_criteria(cls, cls.tenant_id == tenant_id, include_aliases=True)
        )


# --------------------------------------------------------------------------- write guard
@event.listens_for(Session, "before_flush")
def _tenant_write_guard(session: Session, _ctx, _instances):
    if _effective_bypass(session):
        return
    tenant_id = _effective_tenant(session)
    for obj in list(session.new) + list(session.dirty):
        if not is_tenant_scoped(type(obj)):
            continue
        if getattr(obj, "tenant_id", None) is None:
            if tenant_id is None:
                raise TenantContextMissing(f"Insert into {type(obj).__tablename__} with no tenant in context")
            obj.tenant_id = tenant_id
        elif tenant_id is not None and obj.tenant_id != tenant_id:
            raise TenantIsolationError(
                f"Write to {type(obj).__tablename__} for tenant {obj.tenant_id} from context {tenant_id}"
            )
