"""
EnTIQ Billing (module 19) — the practice invoicing ITS clients.

Not to be confused with the platform's own subscription billing (app/services/billing_service.py),
which charges the practice for EnTIQ. This module is the practice's revenue ledger: fee schedules
from the engagement, invoices, payments and the statement the client sees in the portal.
Ported from GrowKyc (invoices, payments, plans) and EntiqStart (billing schedules).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

INVOICE_STATUSES = ("draft", "sent", "part_paid", "paid", "overdue", "void")
FREQUENCIES = ("monthly", "quarterly", "annual")
METHODS = ("bank_transfer", "direct_debit", "card", "cash", "other")


class FeeSchedule(Base, UuidPk, Timestamps):
    """Agreed recurring fees for a client, usually created from the Start proposal at activation."""
    __tablename__ = "billing_fee_schedules"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    frequency: Mapped[str] = mapped_column(String(12), default="monthly", nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    gst: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    day_of_month: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    terms_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    method: Mapped[str] = mapped_column(String(16), default="bank_transfer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_issue_on: Mapped[date | None] = mapped_column(Date, index=True)
    last_invoice_period: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)   # manual · start
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))


class Invoice(Base, UuidPk, Timestamps):
    __tablename__ = "billing_invoices"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id", ondelete="SET NULL"))
    number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(12), default="draft", nullable=False, index=True)
    issued_on: Mapped[date | None] = mapped_column(Date, index=True)
    due_on: Mapped[date | None] = mapped_column(Date, index=True)
    period_label: Mapped[str | None] = mapped_column(String(40))
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gst_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paid_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    fee_schedule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("billing_fee_schedules.id", ondelete="SET NULL"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("practice_jobs.id", ondelete="SET NULL"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="SET NULL"))   # the PDF shared with the client
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    voided_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    void_reason: Mapped[str | None] = mapped_column(String(300))
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reminded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    external_ref: Mapped[str | None] = mapped_column(String(120))     # Xero invoice number once synced
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))

    lines: Mapped[list["InvoiceLine"]] = relationship(back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.order")
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", cascade="all, delete-orphan", order_by="Payment.received_on")

    __table_args__ = (Index("ix_billing_invoices_tenant_status", "tenant_id", "status"),)


class InvoiceLine(Base, UuidPk):
    __tablename__ = "billing_invoice_lines"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("billing_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[float] = mapped_column(default=1.0, nullable=False)
    unit_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    gst: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    module_key: Mapped[str | None] = mapped_column(String(32))       # what generated it: practice · workpapers · advisory …
    ref_id: Mapped[str | None] = mapped_column(String(64))

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class Payment(Base, UuidPk):
    __tablename__ = "billing_payments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("billing_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(16), default="bank_transfer", nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))
    received_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    recorded_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="payments")
