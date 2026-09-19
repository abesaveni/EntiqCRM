from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.core import audit
from app.core.database import get_db
from app.core.deps import Principal, require_operator, require_permission
from app.core.tenancy import platform_scope
from app.models.audit import AuditEvent

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[schemas.AuditOut])
def list_events(limit: int = Query(100, ge=1, le=500), p: Principal = Depends(require_permission("hq:audit")), db: Session = Depends(get_db)):
    with platform_scope():  # audit_events is exempt from the auto-filter; we filter explicitly to this tenant
        rows = db.execute(select(AuditEvent).where(AuditEvent.tenant_id == p.tenant.id).order_by(AuditEvent.id.desc()).limit(limit)).scalars().all()
    return [schemas.AuditOut(id=r.id, action=r.action, actor_user_id=r.actor_user_id, target_type=r.target_type, target_id=r.target_id, detail=r.detail, created_at=r.created_at, hash=r.hash) for r in rows]


@router.get("/verify")
def verify(_p: Principal = Depends(require_operator), db: Session = Depends(get_db)):
    return audit.verify_chain(db)
