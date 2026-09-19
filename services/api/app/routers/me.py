from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.core import audit
from app.core.database import get_db
from app.core.deps import Principal, get_principal, require_permission, require_writable
from app.services import session_service as svc

router = APIRouter(tags=["session"])


@router.get("/me", response_model=schemas.SessionOut)
def me(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return svc.build_session(db, p.user, p.tenant, p.membership)


@router.get("/tenant", response_model=schemas.TenantOut)
def get_tenant(p: Principal = Depends(get_principal)):
    return schemas.TenantOut(**{c: getattr(p.tenant, c) for c in schemas.TenantOut.model_fields})


@router.patch("/tenant", response_model=schemas.TenantOut)
def patch_tenant(body: schemas.TenantPatch, p: Principal = Depends(require_permission("hq:settings")), _w: Principal = Depends(require_writable), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(p.tenant, k, v.strip() if isinstance(v, str) else v)
    audit.record(db, action="tenant.updated", actor_user_id=p.user.id, tenant_id=p.tenant.id, target_type="tenant", target_id=str(p.tenant.id), detail=changes)
    db.commit()
    db.refresh(p.tenant)
    return schemas.TenantOut(**{c: getattr(p.tenant, c) for c in schemas.TenantOut.model_fields})
