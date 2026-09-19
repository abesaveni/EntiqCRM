from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import schemas
from app.core import audit, entitlements
from app.core.database import get_db
from app.core.deps import Principal, get_principal, require_permission
from app.modules import registry
from app.services import billing_service, notify_service

router = APIRouter(tags=["subscriptions"])


def _sub_out(s) -> schemas.SubscriptionOut:
    return schemas.SubscriptionOut(**{c: getattr(s, c) for c in schemas.SubscriptionOut.model_fields})


@router.get("/modules", response_model=list[schemas.ModuleCatalogueItem])
def catalogue(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """The catalogue every practice sees: all non-internal modules, with this tenant's entitlement state."""
    subs = {s.module_key: s for s in entitlements.subscriptions_for(db, p.tenant.id)}
    ent = entitlements.entitlement_map(db, p.tenant)
    return [
        schemas.ModuleCatalogueItem(manifest=m, entitled=ent.get(m["key"], False), subscription=_sub_out(subs[m["key"]]) if m["key"] in subs else None,
                                    purchasable=registry.purchasable(m["key"]), base=registry.is_base(m["key"]))
        for m in registry.catalogue()
    ]


@router.get("/subscriptions", response_model=list[schemas.SubscriptionOut])
def list_subscriptions(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return [_sub_out(s) for s in entitlements.subscriptions_for(db, p.tenant.id)]


@router.post("/subscriptions", response_model=schemas.SubscribeOut, status_code=status.HTTP_201_CREATED)
def subscribe(body: schemas.SubscribeIn, p: Principal = Depends(require_permission("hq:subscriptions")), db: Session = Depends(get_db)):
    try:
        added = entitlements.subscribe(db, p.tenant, body.module_key, body.seats)
    except entitlements.ReadOnly:
        raise HTTPException(status.HTTP_423_LOCKED, detail={"error": "tenant_read_only", "status": p.tenant.status})
    except entitlements.NotEntitled as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": e.reason, "module": e.module_key})
    if added:
        audit.record(db, action="subscription.added", actor_user_id=p.user.id, tenant_id=p.tenant.id, target_type="module", target_id=body.module_key,
                     detail={"added": added, "seats": body.seats})
        for key in added:
            price = billing_service.indicative_price_cents(key)
            billing_service.record(db, tenant_id=p.tenant.id, kind="subscription.started", module_key=key, amount_cents=(price or 0) * (body.seats or 1) if key == body.module_key and price else (price or 0),
                                   detail={"seats": body.seats if key == body.module_key else None, "required_by": None if key == body.module_key else body.module_key, "indicative": True})
        m = registry.get_module(body.module_key)
        notify_service.notify_roles(db, tenant_id=p.tenant.id, roles=("owner", "admin"), exclude=p.membership.id, kind="subscription.added",
                                    title=f"{m['shortName']} was added by {p.user.full_name}", body=m["outcome"], link=f"/hq/modules", module_key="hq")
    db.commit()
    return schemas.SubscribeOut(added=added, subscriptions=[_sub_out(s) for s in entitlements.subscriptions_for(db, p.tenant.id)],
                                entitlements=entitlements.entitlement_map(db, p.tenant))


@router.delete("/subscriptions/{module_key}", response_model=schemas.SubscribeOut)
def unsubscribe(module_key: str, p: Principal = Depends(require_permission("hq:subscriptions")), db: Session = Depends(get_db)):
    try:
        changed = entitlements.unsubscribe(db, p.tenant, module_key)
    except entitlements.NotEntitled as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": e.reason, "module": e.module_key})
    if changed:
        audit.record(db, action="subscription.cancelled", actor_user_id=p.user.id, tenant_id=p.tenant.id, target_type="module", target_id=module_key)
        billing_service.record(db, tenant_id=p.tenant.id, kind="subscription.cancelled", module_key=module_key, detail={"by": p.user.email})
    db.commit()
    return schemas.SubscribeOut(added=[], subscriptions=[_sub_out(s) for s in entitlements.subscriptions_for(db, p.tenant.id)],
                                entitlements=entitlements.entitlement_map(db, p.tenant))
