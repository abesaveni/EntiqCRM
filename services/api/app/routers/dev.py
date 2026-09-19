"""Non-production helpers. The router is not mounted at all when ENV=production."""
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas, schemas_platform as SP
from app.core import audit, mailer
from app.core.database import get_db
from app.core.deps import Principal, get_principal, require_module, require_role
from app.core.security import utcnow
from app.core.tenancy import platform_scope
from app.jobs import lifecycle
from app.models.platform import OutboundMessage
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


@router.post("/time-travel", response_model=schemas.SessionOut)
def time_travel(body: SP.TimeTravelIn, p: Principal = Depends(require_role("owner")), db: Session = Depends(get_db)):
    """Move the tenant's clock so the lifecycle job can be exercised: end the trial now, age a past_due status, etc."""
    if body.trial_ends_in_days is not None:
        p.tenant.trial_ends_at = utcnow() + timedelta(days=body.trial_ends_in_days)
    if body.status_changed_days_ago is not None:
        p.tenant.status_changed_at = utcnow() - timedelta(days=body.status_changed_days_ago)
    db.commit()
    db.refresh(p.tenant)
    return svc.build_session(db, p.user, p.tenant, p.membership)


@router.post("/run-lifecycle")
def run_lifecycle(p: Principal = Depends(require_role("owner")), db: Session = Depends(get_db)):
    """Run the hourly lifecycle job now (all tenants), then return this tenant's fresh session alongside the stats."""
    stats = lifecycle.run(db)
    db.commit()
    db.refresh(p.tenant)
    return {"stats": stats, "session": svc.build_session(db, p.user, p.tenant, p.membership)}


@router.post("/deliver-outbound")
def deliver_outbound(p: Principal = Depends(require_role("owner")), db: Session = Depends(get_db)):
    counts = mailer.deliver_pending(db)
    db.commit()
    return counts


@router.get("/outbound", response_model=list[SP.OutboundOut])
def outbound(limit: int = Query(20, ge=1, le=100), p: Principal = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    """What this practice's users would have received by email — visible in dev even without SMTP."""
    with platform_scope():
        rows = db.execute(select(OutboundMessage).where(OutboundMessage.tenant_id == p.tenant.id).order_by(OutboundMessage.created_at.desc()).limit(limit)).scalars().all()
    return [SP.OutboundOut(id=m.id, to_address=m.to_address, subject=m.subject, template=m.template, status=m.status, attempts=m.attempts, last_error=m.last_error, created_at=m.created_at, sent_at=m.sent_at, body_text=m.body_text) for m in rows]


def _probe(key: str):
    def handler(p: Principal = Depends(require_module(key))):
        return {"module": key, "tenant": str(p.tenant.id), "ok": True}
    return handler


for _key in ("crm", "hq", "verify", "sign", "workpapers", "academy", "support", "advisory"):
    router.add_api_route(f"/probe/{_key}", _probe(_key), methods=["GET"], name=f"probe_{_key}")


@router.get("/whoami")
def whoami(p: Principal = Depends(get_principal)):
    return {"user": p.user.email, "tenant": p.tenant.slug, "role": p.role, "granted": sorted(p.granted_modules)}
