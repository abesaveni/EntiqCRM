from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings, verify_production_safety
from app.core.database import get_db
from app.modules import registry

from app import schemas
from app.services import session_service

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"ok": True, "app": settings.APP_NAME, "env": settings.ENV}


@router.get("/health/deep")
def health_deep(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {
        "ok": True,
        "env": settings.ENV,
        "database": settings.DATABASE_URL.split("://", 1)[0],
        "modules_registered": len(registry.all_modules()),
        "stripe": settings.stripe_enabled,
        "smtp": settings.smtp_enabled,
        "email_delivery": settings.email_delivery_active,
        "safety_problems": verify_production_safety() if not settings.is_production else [],
    }


@router.get("/pricing", response_model=schemas.PricingOut)
def pricing():
    """Public: what the base plan costs here, whether a card is required, and whether this is a free environment."""
    return session_service.pricing_out()
