from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import schemas_platform as S
from app.core import entitlements
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, require_operator, require_role
from app.modules import registry
from app.services import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


def _ev(e) -> S.BillingEventOut:
    return S.BillingEventOut(id=e.id, module_key=e.module_key, kind=e.kind, amount_cents=e.amount_cents, gst_cents=e.gst_cents, total_cents=e.total_cents, currency=e.currency, status=e.status, detail=e.detail or {}, created_at=e.created_at)


@router.get("/summary", response_model=S.BillingSummary)
def summary(p: Principal = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    t = p.tenant
    base = settings.BASE_PLAN_PRICE_CENTS
    lines: list[S.BillingLine] = []
    estimate = 0
    for s in entitlements.subscriptions_for(db, t.id):
        if s.status in ("cancelled", "retained") or s.module_key in registry.PLATFORM_SERVICES or s.module_key == "hq":
            continue
        m = registry.get_module(s.module_key)
        price = billing_service.indicative_price_cents(s.module_key)
        if s.module_key == "crm":
            name, unit = "Base plan — Practice HQ + CRM", "per month"
        else:
            name, unit = m["name"], m["pricing"]["unit"]
        monthly = (price or 0) * (s.seats or 1) if m["pricing"]["model"] == "per_seat" and price else price
        estimate += monthly or 0
        lines.append(S.BillingLine(module_key=s.module_key, name=name, status=s.status, pricing_model=m["pricing"]["model"], unit=unit, indicative_monthly_cents=monthly, seats=s.seats))
    next_charge = t.trial_ends_at if t.status == "trialing" else t.current_period_end
    return S.BillingSummary(
        tenant_status=t.status, base_plan_cents=base, base_plan_inc_gst_cents=base + billing_service.gst_for(base), gst_rate_bps=settings.GST_RATE_BPS,
        trial_ends_at=t.trial_ends_at, current_period_end=t.current_period_end, next_charge_at=next_charge,
        next_charge_estimate_cents=estimate + billing_service.gst_for(estimate), card_on_file=t.card_on_file, card_last4=t.card_last4, billing_mode=settings.BILLING_MODE,
        lines=lines, recent=[_ev(e) for e in billing_service.events_for(db, t.id, 10)],
    )


@router.get("/events", response_model=list[S.BillingEventOut])
def events(limit: int = Query(50, ge=1, le=200), p: Principal = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    return [_ev(e) for e in billing_service.events_for(db, p.tenant.id, limit)]


@router.get("/verify")
def verify(_p: Principal = Depends(require_operator), db: Session = Depends(get_db)):
    return billing_service.verify_chain(db)
