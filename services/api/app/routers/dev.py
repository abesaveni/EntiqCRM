"""Non-production helpers. The router is not mounted at all when ENV=production."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.core import audit
from app.core.database import get_db
from app.core.deps import Principal, get_principal, require_module, require_role
from app.core.security import utcnow
from app.services import session_service as svc

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/lifecycle", response_model=schemas.SessionOut)
def set_lifecycle(body: schemas.LifecycleIn, p: Principal = Depends(require_role("owner")), db: Session = Depends(get_db)):
    """Mirror of the frontend demo control: move the tenant through the subscription lifecycle."""
    p.tenant.status, p.tenant.status_changed_at, p.tenant.status_reason = body.status, utcnow(), body.reason or "dev.lifecycle"
    audit.record(db, action="tenant.status_changed", actor_user_id=p.user.id, tenant_id=p.tenant.id, target_type="tenant", target_id=str(p.tenant.id), detail={"status": body.status, "reason": body.reason})
    db.commit()
    db.refresh(p.tenant)
    return svc.build_session(db, p.user, p.tenant, p.membership)


# A gated probe per module so the gate itself is testable before any module is ported.
def _probe(key: str):
    def handler(p: Principal = Depends(require_module(key))):
        return {"module": key, "tenant": str(p.tenant.id), "ok": True}
    return handler


for _key in ("crm", "hq", "verify", "sign", "workpapers", "academy", "support", "advisory"):
    router.add_api_route(f"/probe/{_key}", _probe(_key), methods=["GET"], name=f"probe_{_key}")


@router.get("/whoami")
def whoami(p: Principal = Depends(get_principal)):
    return {"user": p.user.email, "tenant": p.tenant.slug, "role": p.role, "granted": sorted(p.granted_modules)}
