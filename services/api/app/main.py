"""EnTIQ platform spine — FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import enforce_production_safety, settings
from app.core.limiter import limiter
from app.core.tenancy import TenantContextMissing, TenantIsolationError, set_tenant
from app.modules.sign import router as sign_router
from app.modules.verify import router as verify_router
from app.routers import audit_router, auth, billing, crm, dev, documents, health, me, notifications, subscriptions, users
from app.services import notify_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("entiq")

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    enforce_production_safety()
    notify_service.register()  # event subscribers: task assigned, stage changed, import completed
    from app.modules import registry
    log.info("EnTIQ API starting · env=%s · modules=%d · db=%s", settings.ENV, len(registry.all_modules()), settings.DATABASE_URL.split("://", 1)[0])
    yield
    log.info("EnTIQ API stopped")


app = FastAPI(title=settings.APP_NAME, version="0.2.0", lifespan=lifespan, docs_url=None if settings.is_production else "/docs", redoc_url=None)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def _reset_tenant_context(request: Request, call_next):
    # Each request starts with NO tenant. The auth dependency sets it after verifying the token.
    set_tenant(None)
    try:
        return await call_next(request)
    finally:
        set_tenant(None)


@app.exception_handler(TenantContextMissing)
async def _ctx_missing(_: Request, exc: TenantContextMissing):
    log.error("Fail-closed: %s", exc)
    return JSONResponse(status_code=500, content={"error": "tenant_context_missing"})


@app.exception_handler(TenantIsolationError)
async def _isolation(_: Request, exc: TenantIsolationError):
    log.error("Isolation violation refused: %s", exc)
    return JSONResponse(status_code=403, content={"error": "tenant_isolation_violation"})


app.include_router(health.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(me.router, prefix=API_PREFIX)
app.include_router(subscriptions.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(audit_router.router, prefix=API_PREFIX)
app.include_router(crm.router, prefix=API_PREFIX)
app.include_router(notifications.router, prefix=API_PREFIX)
app.include_router(documents.router, prefix=API_PREFIX)
app.include_router(billing.router, prefix=API_PREFIX)
# Modules
app.include_router(verify_router.router, prefix=API_PREFIX)
app.include_router(sign_router.router, prefix=API_PREFIX)
app.include_router(sign_router.public, prefix=API_PREFIX)
if not settings.is_production:
    app.include_router(dev.router, prefix=API_PREFIX)
