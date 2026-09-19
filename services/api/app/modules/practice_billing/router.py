"""EnTIQ Billing — module 19. The practice's own revenue ledger, under /practice-billing (the platform's subscription billing keeps /billing)."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.models.crm import Client
from app.modules.practice_billing import schemas as S
from app.modules.practice_billing import service as svc
from app.modules.practice_billing.models import FeeSchedule, Invoice
from app.services.crm_service import client_name_map, member_names

router = APIRouter(prefix="/practice-billing", tags=["practice-billing"])
view = require_module("billing")
edit = require_module("billing", write=True)


def _inv(db: Session, invoice_id: uuid.UUID) -> Invoice:
    i = db.get(Invoice, invoice_id)
    if i is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "invoice_not_found"})
    return i


def _err(e: svc.BillingError) -> HTTPException:
    return HTTPException({"client_not_found": 404, "voided": 409, "already_paid": 409, "has_payments": 409, "overpayment": 400}.get(e.error, 400), detail={"error": e.error, "message": e.message})


@router.get("/overview", response_model=S.OverviewOut)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.overview(db)


@router.get("/invoices", response_model=list[S.InvoiceOut])
def list_invoices(status_: str | None = Query(None, alias="status"), client_id: uuid.UUID | None = None, unpaid: bool = False, p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Invoice).order_by(Invoice.issued_on.desc().nullslast(), Invoice.created_at.desc())
    if client_id:
        stmt = stmt.where(Invoice.client_id == client_id)
    rows = db.execute(stmt).scalars().all()
    if unpaid:
        rows = [i for i in rows if i.voided_at is None and i.paid_cents < i.total_cents]
    names = member_names(db, {i.created_by_membership_id for i in rows})
    cn = client_name_map(db, {i.client_id for i in rows})
    out = [svc.invoice_out(db, i, names, cn) for i in rows]
    return [o for o in out if o.status == status_] if status_ else out


@router.post("/invoices", response_model=S.InvoiceDetail, status_code=status.HTTP_201_CREATED)
def create_invoice(body: S.InvoiceIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("billing:invoice")), db: Session = Depends(get_db)):
    try:
        inv = svc.create_invoice(db, p.tenant, body, p.membership.id, p.user.full_name)
    except svc.BillingError as e:
        raise _err(e)
    db.commit()
    db.refresh(inv)
    return svc.invoice_detail(db, inv)


@router.get("/invoices/{invoice_id}", response_model=S.InvoiceDetail)
def get_invoice(invoice_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.invoice_detail(db, _inv(db, invoice_id))


@router.post("/invoices/{invoice_id}/send", response_model=S.InvoiceDetail)
def send_invoice(invoice_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("billing:invoice")), db: Session = Depends(get_db)):
    inv = _inv(db, invoice_id)
    try:
        svc.send_invoice(db, p.tenant, inv, p.membership.id, p.user.full_name)
    except svc.BillingError as e:
        raise _err(e)
    db.commit()
    return svc.invoice_detail(db, inv)


@router.post("/invoices/{invoice_id}/remind", response_model=S.InvoiceDetail)
def remind(invoice_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("billing:collect")), db: Session = Depends(get_db)):
    inv = _inv(db, invoice_id)
    try:
        svc.send_invoice(db, p.tenant, inv, p.membership.id, p.user.full_name, reminder=True)
    except svc.BillingError as e:
        raise _err(e)
    db.commit()
    return svc.invoice_detail(db, inv)


@router.post("/invoices/{invoice_id}/payments", response_model=S.InvoiceDetail, status_code=status.HTTP_201_CREATED)
def record_payment(invoice_id: uuid.UUID, body: S.PaymentIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("billing:collect")), db: Session = Depends(get_db)):
    inv = _inv(db, invoice_id)
    try:
        svc.record_payment(db, p.tenant, inv, body, p.membership.id, p.user.full_name)
    except svc.BillingError as e:
        raise _err(e)
    db.commit()
    return svc.invoice_detail(db, inv)


@router.post("/invoices/{invoice_id}/void", response_model=S.InvoiceDetail)
def void_invoice(invoice_id: uuid.UUID, body: S.VoidIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("billing:refund")), db: Session = Depends(get_db)):
    inv = _inv(db, invoice_id)
    try:
        svc.void_invoice(db, inv, body.reason, p.membership.id, p.user.full_name)
    except svc.BillingError as e:
        raise _err(e)
    db.commit()
    return svc.invoice_detail(db, inv)


# ------------------------------------------------------------------ fee schedules
@router.get("/schedules", response_model=list[S.ScheduleOut])
def schedules(client_id: uuid.UUID | None = None, p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(FeeSchedule).order_by(FeeSchedule.next_issue_on.is_(None), FeeSchedule.next_issue_on)
    if client_id:
        stmt = stmt.where(FeeSchedule.client_id == client_id)
    rows = db.execute(stmt).scalars().all()
    cn = client_name_map(db, {s.client_id for s in rows})
    return [svc.schedule_out(s, cn) for s in rows]


@router.post("/schedules", response_model=S.ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(body: S.ScheduleIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("billing:invoice")), db: Session = Depends(get_db)):
    try:
        s = svc.create_schedule(db, p.tenant, body, p.membership.id, p.user.full_name)
    except svc.BillingError as e:
        raise _err(e)
    db.commit()
    return svc.schedule_out(s, client_name_map(db, {s.client_id}))


@router.post("/schedules/{schedule_id}/toggle", response_model=S.ScheduleOut)
def toggle_schedule(schedule_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("billing:invoice")), db: Session = Depends(get_db)):
    s = db.get(FeeSchedule, schedule_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "schedule_not_found"})
    s.is_active = not s.is_active
    db.commit()
    return svc.schedule_out(s, client_name_map(db, {s.client_id}))


@router.post("/schedules/generate", response_model=S.GenerateOut)
def generate(as_of: date | None = None, send: bool = False, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("billing:invoice")), db: Session = Depends(get_db)):
    rows = svc.generate_due(db, p.tenant, p.membership.id, p.user.full_name, as_of=as_of, send=send)
    db.commit()
    names = member_names(db, {i.created_by_membership_id for i in rows})
    cn = client_name_map(db, {i.client_id for i in rows})
    return S.GenerateOut(created=len(rows), invoices=[svc.invoice_out(db, i, names, cn) for i in rows])


@router.get("/clients/{client_id}/statement", response_model=S.ClientStatement)
def statement(client_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "client_not_found"})
    return svc.statement(db, c)
