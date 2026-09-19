from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class LineIn(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    quantity: float = Field(default=1.0, gt=0, le=10000)
    unit_cents: int = Field(ge=0)
    gst: bool = True
    module_key: str | None = None
    ref_id: str | None = None


class InvoiceIn(BaseModel):
    client_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    lines: list[LineIn] = Field(min_length=1, max_length=60)
    period_label: str | None = Field(default=None, max_length=40)
    issued_on: date | None = None
    terms_days: int = Field(default=14, ge=0, le=180)
    notes: str | None = Field(default=None, max_length=4000)
    job_id: uuid.UUID | None = None
    send_now: bool = False


class LineOut(BaseModel):
    id: uuid.UUID
    description: str
    quantity: float
    unit_cents: int
    gst: bool
    amount_cents: int
    module_key: str | None


class PaymentIn(BaseModel):
    amount_cents: int = Field(gt=0)
    method: Literal["bank_transfer", "direct_debit", "card", "cash", "other"] = "bank_transfer"
    reference: str | None = Field(default=None, max_length=120)
    received_on: date | None = None


class PaymentOut(BaseModel):
    id: uuid.UUID
    amount_cents: int
    method: str
    reference: str | None
    received_on: date
    recorded_by_name: str | None


class InvoiceOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    contact_name: str | None
    contact_email: str | None
    number: str
    status: str
    issued_on: date | None
    due_on: date | None
    period_label: str | None
    subtotal_cents: int
    gst_cents: int
    total_cents: int
    paid_cents: int
    balance_cents: int
    overdue: bool
    days_overdue: int
    notes: str | None
    fee_schedule_id: uuid.UUID | None
    job_id: uuid.UUID | None
    document_id: uuid.UUID | None
    external_ref: str | None
    reminders_sent: int
    sent_at: datetime | None
    paid_at: datetime | None
    created_by_name: str | None
    created_at: datetime


class InvoiceDetail(InvoiceOut):
    lines: list[LineOut]
    payments: list[PaymentOut]


class VoidIn(BaseModel):
    reason: str = Field(min_length=2, max_length=300)


class ScheduleIn(BaseModel):
    client_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    frequency: Literal["monthly", "quarterly", "annual"] = "monthly"
    amount_cents: int = Field(gt=0)
    gst: bool = True
    day_of_month: int = Field(default=1, ge=1, le=28)
    terms_days: int = Field(default=14, ge=0, le=180)
    method: Literal["bank_transfer", "direct_debit", "card", "cash", "other"] = "bank_transfer"
    start_on: date | None = None
    notes: str | None = None


class ScheduleOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    name: str
    frequency: str
    amount_cents: int
    gst: bool
    total_cents: int
    day_of_month: int
    terms_days: int
    method: str
    is_active: bool
    next_issue_on: date | None
    last_invoice_period: str | None
    source: str
    annualised_cents: int


class StatementRow(BaseModel):
    invoice_id: uuid.UUID
    number: str
    issued_on: date | None
    due_on: date | None
    total_cents: int
    paid_cents: int
    balance_cents: int
    status: str
    days_overdue: int


class ClientStatement(BaseModel):
    client_id: uuid.UUID
    client_name: str
    outstanding_cents: int
    overdue_cents: int
    current_cents: int
    invoices: list[StatementRow]
    schedules: list[ScheduleOut]


class AgedRow(BaseModel):
    client_id: uuid.UUID
    client_name: str
    current_cents: int
    d30_cents: int
    d60_cents: int
    d90_cents: int
    total_cents: int
    oldest_days: int


class OverviewOut(BaseModel):
    outstanding_cents: int
    overdue_cents: int
    draft: int
    sent: int
    overdue_count: int
    paid_30d_cents: int
    invoiced_30d_cents: int
    recurring_annualised_cents: int
    avg_days_to_pay: float | None
    aged: list[AgedRow]


class GenerateOut(BaseModel):
    created: int
    invoices: list[InvoiceOut]
