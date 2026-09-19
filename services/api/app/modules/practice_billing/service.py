from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import entitlements, events, mailer
from app.core.config import settings
from app.core.security import utcnow
from app.core.tenancy import platform_scope
from app.models.crm import Client, Contact
from app.models.tenant import Tenant
from app.modules.practice_billing import schemas as S
from app.modules.practice_billing.models import FeeSchedule, Invoice, InvoiceLine, Payment
from app.notify import templates
from app.services import notify_service
from app.services.crm_service import client_name_map, member_names

GST_DIVISOR = 10000


class BillingError(Exception):
    def __init__(self, error: str, message: str | None = None):
        super().__init__(message or error)
        self.error, self.message = error, message or error


def _next_number(db: Session, tenant_id: uuid.UUID) -> str:
    n = db.execute(select(func.count()).select_from(Invoice)).scalar_one()
    return f"INV-{date.today():%Y}-{1000 + n + 1}"


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _totals(inv: Invoice) -> None:
    sub = sum(l.amount_cents for l in inv.lines)
    gst = sum(round(l.amount_cents * settings.GST_RATE_BPS / GST_DIVISOR) for l in inv.lines if l.gst)
    inv.subtotal_cents, inv.gst_cents, inv.total_cents = sub, gst, sub + gst


def _status(inv: Invoice, today: date | None = None) -> str:
    today = today or date.today()
    if inv.voided_at:
        return "void"
    if inv.paid_cents >= inv.total_cents and inv.total_cents > 0:
        return "paid"
    if inv.sent_at is None:
        return "draft"
    if inv.due_on and inv.due_on < today:
        return "overdue"
    return "part_paid" if inv.paid_cents > 0 else "sent"


# ------------------------------------------------------------------ serialisers
def invoice_out(db: Session, inv: Invoice, names: dict | None = None, clients: dict | None = None) -> S.InvoiceOut:
    names = names if names is not None else member_names(db, {inv.created_by_membership_id})
    clients = clients if clients is not None else client_name_map(db, {inv.client_id})
    ct = db.get(Contact, inv.contact_id) if inv.contact_id else None
    today = date.today()
    balance = max(0, inv.total_cents - inv.paid_cents)
    days = (today - inv.due_on).days if inv.due_on and inv.due_on < today and balance > 0 else 0
    return S.InvoiceOut(id=inv.id, client_id=inv.client_id, client_name=clients.get(inv.client_id), contact_name=ct.full_name if ct else None, contact_email=ct.email if ct else None, number=inv.number,
                        status=_status(inv, today), issued_on=inv.issued_on, due_on=inv.due_on, period_label=inv.period_label, subtotal_cents=inv.subtotal_cents, gst_cents=inv.gst_cents,
                        total_cents=inv.total_cents, paid_cents=inv.paid_cents, balance_cents=balance, overdue=days > 0, days_overdue=days, notes=inv.notes, fee_schedule_id=inv.fee_schedule_id,
                        job_id=inv.job_id, document_id=inv.document_id, external_ref=inv.external_ref, reminders_sent=inv.reminders_sent, sent_at=inv.sent_at, paid_at=inv.paid_at,
                        created_by_name=names.get(inv.created_by_membership_id) if inv.created_by_membership_id else None, created_at=inv.created_at)


def invoice_detail(db: Session, inv: Invoice) -> S.InvoiceDetail:
    base = invoice_out(db, inv)
    pnames = member_names(db, {p.recorded_by_membership_id for p in inv.payments})
    return S.InvoiceDetail(**base.model_dump(),
                           lines=[S.LineOut(id=l.id, description=l.description, quantity=l.quantity, unit_cents=l.unit_cents, gst=l.gst, amount_cents=l.amount_cents, module_key=l.module_key) for l in inv.lines],
                           payments=[S.PaymentOut(id=p.id, amount_cents=p.amount_cents, method=p.method, reference=p.reference, received_on=p.received_on, recorded_by_name=pnames.get(p.recorded_by_membership_id)) for p in inv.payments])


def schedule_out(s: FeeSchedule, clients: dict) -> S.ScheduleOut:
    total = s.amount_cents + (round(s.amount_cents * settings.GST_RATE_BPS / GST_DIVISOR) if s.gst else 0)
    per_year = {"monthly": 12, "quarterly": 4, "annual": 1}[s.frequency]
    return S.ScheduleOut(id=s.id, client_id=s.client_id, client_name=clients.get(s.client_id), name=s.name, frequency=s.frequency, amount_cents=s.amount_cents, gst=s.gst, total_cents=total,
                         day_of_month=s.day_of_month, terms_days=s.terms_days, method=s.method, is_active=s.is_active, next_issue_on=s.next_issue_on, last_invoice_period=s.last_invoice_period,
                         source=s.source, annualised_cents=total * per_year)


# ------------------------------------------------------------------ invoices
def create_invoice(db: Session, tenant: Tenant, body: S.InvoiceIn, actor_mid: uuid.UUID, actor_label: str, *, schedule: FeeSchedule | None = None) -> Invoice:
    c = db.get(Client, body.client_id)
    if c is None:
        raise BillingError("client_not_found")
    ct = db.get(Contact, body.contact_id) if body.contact_id else db.execute(select(Contact).where(Contact.client_id == c.id, Contact.archived_at.is_(None)).order_by(Contact.is_primary.desc(), Contact.created_at)).scalars().first()
    issued = body.issued_on or date.today()
    inv = Invoice(tenant_id=tenant.id, client_id=c.id, contact_id=ct.id if ct else None, number=_next_number(db, tenant.id), period_label=body.period_label, issued_on=issued,
                  due_on=issued + timedelta(days=body.terms_days), notes=body.notes, job_id=body.job_id, fee_schedule_id=schedule.id if schedule else None, created_by_membership_id=actor_mid)
    db.add(inv)
    db.flush()
    for i, l in enumerate(body.lines, 1):
        db.add(InvoiceLine(tenant_id=tenant.id, invoice_id=inv.id, description=l.description, quantity=l.quantity, unit_cents=l.unit_cents, gst=l.gst,
                           amount_cents=round(l.quantity * l.unit_cents), order=i, module_key=l.module_key, ref_id=l.ref_id))
    db.flush()
    db.refresh(inv)
    _totals(inv)
    inv.status = _status(inv)
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="billing", kind="invoice.created", summary=f"Invoice {inv.number} drafted — {_money(inv.total_cents)} inc GST",
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="invoice", ref_id=inv.id)
    if body.send_now:
        send_invoice(db, tenant, inv, actor_mid, actor_label)
    return inv


def send_invoice(db: Session, tenant: Tenant, inv: Invoice, actor_mid: uuid.UUID | None, actor_label: str, *, reminder: bool = False) -> Invoice:
    if inv.voided_at:
        raise BillingError("voided")
    if inv.paid_cents >= inv.total_cents and inv.total_cents > 0:
        raise BillingError("already_paid")
    ct = db.get(Contact, inv.contact_id) if inv.contact_id else None
    c = db.get(Client, inv.client_id)
    if ct is None or not ct.email:
        raise BillingError("no_contact_email", "The client needs a contact with an email address")
    balance = max(0, inv.total_cents - inv.paid_cents)
    subject, text, html = templates.invoice_email(name=ct.first_name, practice=tenant.name, number=inv.number, client=c.name, total=_money(balance),
                                                  due=inv.due_on.strftime("%d %b %Y") if inv.due_on else "on receipt",
                                                  lines=[(l.description, _money(l.amount_cents)) for l in inv.lines], reminder=reminder,
                                                  days_overdue=(date.today() - inv.due_on).days if reminder and inv.due_on else 0,
                                                  url=f"{settings.APP_PUBLIC_URL.rstrip('/')}/portal")
    mailer.queue_email(db, tenant_id=tenant.id, to=ct.email, subject=subject, text=text, html=html, template="invoice_reminder" if reminder else "invoice_sent", ref_type="invoice", ref_id=inv.id)
    now = utcnow()
    if reminder:
        inv.reminders_sent += 1
        inv.last_reminded_at = now
    else:
        inv.sent_at = inv.sent_at or now
    inv.status = _status(inv)
    events.emit(db, tenant_id=tenant.id, client_id=inv.client_id, module_key="billing", kind="invoice.reminded" if reminder else "invoice.sent",
                summary=f"Invoice {inv.number} {'reminder sent' if reminder else 'sent'} to {ct.full_name} — {_money(balance)}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="invoice", ref_id=inv.id)
    db.flush()
    return inv


def record_payment(db: Session, tenant: Tenant, inv: Invoice, body: S.PaymentIn, actor_mid: uuid.UUID, actor_label: str) -> Payment:
    if inv.voided_at:
        raise BillingError("voided")
    balance = inv.total_cents - inv.paid_cents
    if body.amount_cents > balance:
        raise BillingError("overpayment", f"That is more than the {_money(balance)} outstanding")
    p = Payment(tenant_id=tenant.id, invoice_id=inv.id, amount_cents=body.amount_cents, method=body.method, reference=body.reference, received_on=body.received_on or date.today(),
                recorded_by_membership_id=actor_mid, created_at=utcnow())
    db.add(p)
    inv.paid_cents += body.amount_cents
    if inv.paid_cents >= inv.total_cents:
        inv.paid_at = utcnow()
    inv.status = _status(inv)
    db.flush()
    events.emit(db, tenant_id=tenant.id, client_id=inv.client_id, module_key="billing", kind="payment.received",
                summary=f"Payment {_money(body.amount_cents)} received against {inv.number}" + (" — paid in full" if inv.status == "paid" else f", {_money(inv.total_cents - inv.paid_cents)} outstanding"),
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="invoice", ref_id=inv.id)
    return p


def void_invoice(db: Session, inv: Invoice, reason: str, actor_mid: uuid.UUID, actor_label: str) -> Invoice:
    if inv.paid_cents > 0:
        raise BillingError("has_payments", "Refund or reallocate the payments before voiding")
    inv.voided_at, inv.void_reason, inv.status = utcnow(), reason, "void"
    events.emit(db, tenant_id=inv.tenant_id, client_id=inv.client_id, module_key="billing", kind="invoice.voided", summary=f"Invoice {inv.number} voided — {reason}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="invoice", ref_id=inv.id)
    return inv


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


# ------------------------------------------------------------------ fee schedules
def create_schedule(db: Session, tenant: Tenant, body: S.ScheduleIn, actor_mid: uuid.UUID | None, actor_label: str, *, source: str = "manual") -> FeeSchedule:
    c = db.get(Client, body.client_id)
    if c is None:
        raise BillingError("client_not_found")
    start = body.start_on or date.today()
    nxt = start.replace(day=min(body.day_of_month, calendar.monthrange(start.year, start.month)[1]))
    if nxt < start:
        nxt = _add_months(nxt, 1)
    s = FeeSchedule(tenant_id=tenant.id, client_id=c.id, name=body.name, frequency=body.frequency, amount_cents=body.amount_cents, gst=body.gst, day_of_month=body.day_of_month,
                    terms_days=body.terms_days, method=body.method, next_issue_on=nxt, notes=body.notes, source=source, created_by_membership_id=actor_mid)
    db.add(s)
    db.flush()
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="billing", kind="fee_schedule.created", summary=f"Fee schedule: {s.name} — {_money(s.amount_cents)} {s.frequency}",
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="fee_schedule", ref_id=s.id)
    return s


def generate_due(db: Session, tenant: Tenant, actor_mid: uuid.UUID | None, actor_label: str, *, as_of: date | None = None, send: bool = False) -> list[Invoice]:
    today = as_of or date.today()
    out: list[Invoice] = []
    for s in db.execute(select(FeeSchedule).where(FeeSchedule.is_active.is_(True), FeeSchedule.next_issue_on.is_not(None))).scalars().all():
        guard = 0
        while s.next_issue_on and s.next_issue_on <= today and guard < 24:
            guard += 1
            period = s.next_issue_on.strftime("%b %Y") if s.frequency == "monthly" else s.next_issue_on.strftime("%b %Y") if s.frequency == "quarterly" else s.next_issue_on.strftime("%Y")
            if s.last_invoice_period != period:
                inv = create_invoice(db, tenant, S.InvoiceIn(client_id=s.client_id, lines=[S.LineIn(description=f"{s.name} — {period}", quantity=1, unit_cents=s.amount_cents, gst=s.gst, module_key="billing")],
                                                             period_label=period, issued_on=s.next_issue_on, terms_days=s.terms_days, send_now=send), actor_mid or uuid.uuid4(), actor_label, schedule=s)
                out.append(inv)
                s.last_invoice_period = period
            months = {"monthly": 1, "quarterly": 3, "annual": 12}[s.frequency]
            s.next_issue_on = _add_months(s.next_issue_on, months)
    db.flush()
    return out


def on_onboarding_activated(db: Session, ev) -> None:
    """Start → Billing: turn the accepted proposal into fee schedules when the client is activated."""
    t = db.get(Tenant, ev.tenant_id)
    try:
        entitlements.check(db, t, "billing")
    except entitlements.NotEntitled:
        return
    if not ev.client_id:
        return
    for svc in (ev.detail or {}).get("services", []):
        basis = str(svc.get("basis", "annual"))
        if basis in ("monthly", "quarterly", "annual"):
            try:
                create_schedule(db, t, S.ScheduleIn(client_id=ev.client_id, name=str(svc.get("name", "Services")), frequency=basis, amount_cents=int(svc.get("amount_cents") or 0) or 1,
                                                    gst=bool(svc.get("gst", True))), None, "EnTIQ Start", source="start")
            except BillingError:
                continue


def register() -> None:
    events.subscribe("onboarding.activated", on_onboarding_activated)


# ------------------------------------------------------------------ statements and overview
def statement(db: Session, client: Client) -> S.ClientStatement:
    invs = db.execute(select(Invoice).where(Invoice.client_id == client.id, Invoice.voided_at.is_(None)).order_by(Invoice.issued_on.desc().nullslast())).scalars().all()
    today = date.today()
    rows: list[S.StatementRow] = []
    outstanding = overdue = 0
    for inv in invs:
        bal = max(0, inv.total_cents - inv.paid_cents)
        days = (today - inv.due_on).days if inv.due_on and inv.due_on < today and bal > 0 else 0
        outstanding += bal
        overdue += bal if days > 0 else 0
        rows.append(S.StatementRow(invoice_id=inv.id, number=inv.number, issued_on=inv.issued_on, due_on=inv.due_on, total_cents=inv.total_cents, paid_cents=inv.paid_cents, balance_cents=bal, status=_status(inv, today), days_overdue=days))
    scheds = db.execute(select(FeeSchedule).where(FeeSchedule.client_id == client.id).order_by(FeeSchedule.name)).scalars().all()
    return S.ClientStatement(client_id=client.id, client_name=client.name, outstanding_cents=outstanding, overdue_cents=overdue, current_cents=outstanding - overdue,
                             invoices=rows, schedules=[schedule_out(s, {client.id: client.name}) for s in scheds])


def overview(db: Session) -> S.OverviewOut:
    invs = db.execute(select(Invoice).where(Invoice.voided_at.is_(None))).scalars().all()
    today = date.today()
    since = today - timedelta(days=30)
    aged: dict[uuid.UUID, list[int]] = {}
    oldest: dict[uuid.UUID, int] = {}
    outstanding = overdue = 0
    for inv in invs:
        bal = max(0, inv.total_cents - inv.paid_cents)
        if bal <= 0 or inv.sent_at is None:
            continue
        days = (today - inv.due_on).days if inv.due_on else 0
        outstanding += bal
        bucket = 0 if days <= 0 else 1 if days <= 30 else 2 if days <= 60 else 3
        if days > 0:
            overdue += bal
        row = aged.setdefault(inv.client_id, [0, 0, 0, 0])
        row[bucket] += bal
        oldest[inv.client_id] = max(oldest.get(inv.client_id, 0), max(0, days))
    clients = client_name_map(db, set(aged))
    paid = db.execute(select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(Payment.received_on >= since)).scalar_one()
    invoiced = sum(i.total_cents for i in invs if i.issued_on and i.issued_on >= since)
    pay_days = [(p.received_on - i.issued_on).days for i in invs if i.issued_on for p in i.payments]
    scheds = db.execute(select(FeeSchedule).where(FeeSchedule.is_active.is_(True))).scalars().all()
    annualised = sum(schedule_out(s, {}).annualised_cents for s in scheds)
    return S.OverviewOut(outstanding_cents=outstanding, overdue_cents=overdue, draft=sum(1 for i in invs if _status(i, today) == "draft"), sent=sum(1 for i in invs if _status(i, today) in ("sent", "part_paid")),
                         overdue_count=sum(1 for i in invs if _status(i, today) == "overdue"), paid_30d_cents=int(paid), invoiced_30d_cents=invoiced, recurring_annualised_cents=annualised,
                         avg_days_to_pay=round(sum(pay_days) / len(pay_days), 1) if pay_days else None,
                         aged=sorted([S.AgedRow(client_id=cid, client_name=clients.get(cid, "—"), current_cents=v[0], d30_cents=v[1], d60_cents=v[2], d90_cents=v[3], total_cents=sum(v), oldest_days=oldest.get(cid, 0)) for cid, v in aged.items()],
                                     key=lambda r: -r.total_cents)[:20])


def chase_overdue(db: Session, now: datetime) -> int:
    """Lifecycle: one reminder per overdue invoice per week, up to three."""
    from app.core.tenancy import tenant_scope
    n = 0
    today = now.date()
    with platform_scope():
        rows = db.execute(select(Invoice).where(Invoice.voided_at.is_(None), Invoice.sent_at.is_not(None), Invoice.due_on.is_not(None), Invoice.due_on < today, Invoice.reminders_sent < 3)).scalars().all()
        rows = [i for i in rows if i.paid_cents < i.total_cents and (i.last_reminded_at is None or (now - i.last_reminded_at).days >= 7)]
    for inv in rows:
        with tenant_scope(inv.tenant_id):
            db.info["tenant_id"] = inv.tenant_id
            t = db.get(Tenant, inv.tenant_id)
            try:
                send_invoice(db, t, inv, None, "EnTIQ Billing", reminder=True)
                n += 1
            except BillingError:
                continue
        db.info.pop("tenant_id", None)
    return n
