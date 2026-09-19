"""
The subscription lifecycle job. Run it every hour (cron / scheduler / `python -m app.jobs.lifecycle`).

  trialing ──(day 10, day 14)──▶ reminder emails, sent once each
  trialing ──(trial_ends_at passed)──▶ active            BILLING_MODE=simulate: charge recorded, not taken
                                                         BILLING_MODE=stripe:   charge attempted (pending Stripe keys)
  past_due ──(grace over)──▶ suspended (read-only)
  suspended ──(30 days)──▶ cancelled (export window)
  cancelled ──(export window over)──▶ retained           access ends; records are NEVER deleted

Every transition is audited, mirrored onto the base-bundle subscription rows, recorded in
the billing ledger where money is involved, and communicated to the practice owners.
Idempotent: safe to run as often as you like.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit, events, mailer
from app.core.config import settings
from app.core.security import utcnow
from app.core.tenancy import platform_scope
from app.models.platform import LifecycleNotice
from app.models.subscription import TenantSubscription
from app.models.tenant import Tenant
from app.modules import registry
from app.notify import templates
from app.services import billing_service, notify_service

log = logging.getLogger("entiq.lifecycle")


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _notice_sent(db: Session, tenant_id, kind: str) -> bool:
    return db.execute(select(LifecycleNotice.id).where(LifecycleNotice.tenant_id == tenant_id, LifecycleNotice.kind == kind)).first() is not None


def _mark_notice(db: Session, tenant_id, kind: str) -> None:
    db.add(LifecycleNotice(tenant_id=tenant_id, kind=kind, sent_at=utcnow()))
    db.flush()


def _email_owners(db: Session, t: Tenant, template: str, build) -> int:
    n = 0
    for m, u in notify_service.owners(db, t.id):
        subject, text, html = build(u.full_name.split()[0])
        mailer.queue_email(db, tenant_id=t.id, to=u.email, subject=subject, text=text, html=html, template=template, ref_type="tenant", ref_id=t.id)
        n += 1
    return n


def _set_status(db: Session, t: Tenant, status: str, reason: str, now: datetime) -> None:
    old = t.status
    t.status, t.status_changed_at, t.status_reason = status, now, reason
    # The base bundle's status IS the tenant's status.
    for s in db.execute(select(TenantSubscription).where(TenantSubscription.tenant_id == t.id, TenantSubscription.module_key.in_([*registry.BASE_BUNDLE, *registry.PLATFORM_SERVICES]))).scalars():
        s.status = status
    audit.record(db, action="tenant.status_changed", actor_user_id=None, tenant_id=t.id, target_type="tenant", target_id=str(t.id), detail={"from": old, "to": status, "reason": reason, "by": "lifecycle_job"})
    notify_service.notify_roles(db, tenant_id=t.id, roles=("owner", "admin"), kind=f"tenant.{status}", title=f"Practice is now {status.replace('_', ' ')}", body=reason, link="/hq/modules", module_key="hq")


def run(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    base = settings.BASE_PLAN_PRICE_CENTS
    inc = _money(base + billing_service.gst_for(base))
    app_url = settings.APP_PUBLIC_URL
    stats = {"checked": 0, "reminders": 0, "activated": 0, "past_due": 0, "suspended": 0, "cancelled": 0, "retained": 0, "stripe_pending": 0, "emails": 0}

    with platform_scope():
        tenants = db.execute(select(Tenant).where(Tenant.status.in_(["trialing", "past_due", "suspended", "cancelled"]))).scalars().all()
        for t in tenants:
            stats["checked"] += 1
            if t.status == "trialing" and t.trial_ends_at:
                days_left = (t.trial_ends_at - now).total_seconds() / 86_400
                for kind, threshold in (("trial_day10", 5), ("trial_day14", 1)):
                    if 0 < days_left <= threshold and not _notice_sent(db, t.id, kind):
                        stats["emails"] += _email_owners(db, t, kind, lambda first, d=max(1, round(days_left)): templates.trial_reminder(
                            name=first, practice=t.name, days_left=d, charge_date=t.trial_ends_at.strftime("%d %b %Y"), amount_inc_gst=inc, app_url=app_url, card_last4=t.card_last4))
                        notify_service.notify_roles(db, tenant_id=t.id, roles=("owner",), kind=kind, title=f"{max(1, round(days_left))} day{'s' if round(days_left) != 1 else ''} left in your trial", body=f"{inc} is charged on {t.trial_ends_at.strftime('%d %b')} unless you cancel.", link="/hq/modules")
                        _mark_notice(db, t.id, kind)
                        stats["reminders"] += 1
                if t.trial_ends_at <= now:
                    if settings.BILLING_MODE == "simulate" or not settings.stripe_enabled:
                        period_end = now + timedelta(days=30)
                        t.current_period_end = period_end
                        _set_status(db, t, "active", "trial ended — base plan started (charge simulated: no payment provider configured)", now)
                        billing_service.record(db, tenant_id=t.id, kind="charge.simulated", module_key="crm", amount_cents=base, status="simulated",
                                               detail={"period_end": period_end.isoformat(), "card_last4": t.card_last4, "note": "BILLING_MODE=simulate — no money moved"})
                        if not _notice_sent(db, t.id, "trial_ended"):
                            stats["emails"] += _email_owners(db, t, "trial_ended", lambda first: templates.trial_ended_active(name=first, practice=t.name, amount_inc_gst=inc, period_end=period_end.strftime("%d %b %Y"), simulated=True, app_url=app_url))
                            _mark_notice(db, t.id, "trial_ended")
                        stats["activated"] += 1
                    else:
                        # Stripe keys present: the charge path lands with the Stripe integration. Do not fake an outcome.
                        stats["stripe_pending"] += 1
                        log.warning("tenant %s trial ended; BILLING_MODE=stripe charge not yet implemented — left trialing", t.slug)

            elif t.status == "past_due" and t.status_changed_at and t.status_changed_at + timedelta(days=settings.PAST_DUE_GRACE_DAYS) <= now:
                _set_status(db, t, "suspended", f"payment not received within {settings.PAST_DUE_GRACE_DAYS} days — read-only", now)
                if not _notice_sent(db, t.id, "suspended"):
                    stats["emails"] += _email_owners(db, t, "suspended", lambda first: templates.suspended(name=first, practice=t.name, app_url=app_url))
                    _mark_notice(db, t.id, "suspended")
                stats["suspended"] += 1

            elif t.status == "suspended" and t.status_changed_at and t.status_changed_at + timedelta(days=settings.SUSPENDED_TO_CANCELLED_DAYS) <= now:
                _set_status(db, t, "cancelled", f"suspended for {settings.SUSPENDED_TO_CANCELLED_DAYS} days — cancelled, {settings.EXPORT_WINDOW_DAYS}-day export window", now)
                for s in db.execute(select(TenantSubscription).where(TenantSubscription.tenant_id == t.id, TenantSubscription.status != "cancelled")).scalars():
                    s.status, s.cancelled_at = "cancelled", now
                    billing_service.record(db, tenant_id=t.id, kind="subscription.cancelled", module_key=s.module_key, detail={"reason": "tenant cancelled"})
                if not _notice_sent(db, t.id, "cancelled"):
                    stats["emails"] += _email_owners(db, t, "cancelled", lambda first: templates.cancelled(name=first, practice=t.name, export_days=settings.EXPORT_WINDOW_DAYS, app_url=app_url))
                    _mark_notice(db, t.id, "cancelled")
                stats["cancelled"] += 1

            elif t.status == "cancelled" and t.status_changed_at and t.status_changed_at + timedelta(days=settings.EXPORT_WINDOW_DAYS) <= now:
                _set_status(db, t, "retained", "export window closed — records retained under compliance obligations, access ended", now)
                stats["retained"] += 1

        db.flush()
        delivered = mailer.deliver_pending(db)
    stats["agreements_expired"] = expire_agreements(db, now)
    stats["recurring_jobs_created"] = generate_recurring_jobs(db, now)
    from app.modules.requests import service as requests_service
    stats["request_reminders"] = requests_service.remind_overdue(db, now)
    db.commit()
    stats["delivery"] = delivered
    return stats


def expire_agreements(db: Session, now: datetime) -> int:
    """Sign: agreements still awaiting signature past their expiry become `expired` (links already refuse). Records are kept."""
    from app.modules.sign.models import Agreement
    from app.modules.sign.service import record_event
    n = 0
    with platform_scope():
        rows = db.execute(select(Agreement).where(Agreement.status.in_(["sent", "partially_signed"]), Agreement.expires_at.is_not(None), Agreement.expires_at < now)).scalars().all()
        for a in rows:
            a.status = "expired"
            for s in a.signers:
                s.token_hash = None
            record_event(db, a, "expired", detail={"expires_at": a.expires_at.isoformat()})
            events.emit(db, tenant_id=a.tenant_id, client_id=a.client_id, module_key="sign", kind="agreement.expired", summary=f"Expired unsigned: {a.title}", actor_label="EnTIQ Sign", ref_type="agreement", ref_id=a.id)
            n += 1
        db.commit()
    return n


if __name__ == "__main__":
    from app.core.database import SessionLocal

    with SessionLocal() as session:
        result = run(session)
        session.commit()
    json.dump(result, sys.stdout, indent=2)
    print()


def generate_recurring_jobs(db: Session, now: datetime) -> int:
    """Practice: materialise recurring jobs whose due date is within their advance window, per tenant."""
    from app.core.tenancy import tenant_scope
    from app.models.tenant import Tenant
    from app.modules.practice import service as practice_service
    n = 0
    with platform_scope():
        tenants = db.execute(select(Tenant.id).join(TenantSubscription, TenantSubscription.tenant_id == Tenant.id).where(TenantSubscription.module_key == "practice", TenantSubscription.status.in_(["trialing", "active", "past_due"]))).scalars().all()
    for tid in tenants:
        with tenant_scope(tid):
            db.info["tenant_id"] = tid
            n += practice_service.generate_recurring(db, tid, now.date())
        db.info.pop("tenant_id", None)
    db.commit()
    return n
