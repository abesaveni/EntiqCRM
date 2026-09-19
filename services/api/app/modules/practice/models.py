"""
EnTIQ Practice (module 09) — jobs, recurring work, time and deadlines.
Ported from GrowAccounting jobs / recurring_jobs / tasks, re-keyed to the CRM client and tenant.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

JOB_TYPES = ["BAS", "IAS", "Tax Return", "Financial Statements", "Bookkeeping", "Payroll", "ASIC", "FBT", "Advisory", "Onboarding", "Other"]
JOB_STATUSES = ["not_started", "in_progress", "waiting_client", "review", "complete", "cancelled"]
OPEN_STATUSES = ["not_started", "in_progress", "waiting_client", "review"]
FREQUENCIES = ["monthly", "quarterly", "biannual", "annual"]


class Job(Base, UuidPk, Timestamps):
    __tablename__ = "practice_jobs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    job_type: Mapped[str] = mapped_column(String(40), default="Other", nullable=False, index=True)
    period_label: Mapped[str | None] = mapped_column(String(40))            # "Q1 FY27" · "Jul 2026" · "FY26"
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    due_on: Mapped[date | None] = mapped_column(Date, index=True)             # internal target
    lodgement_due: Mapped[date | None] = mapped_column(Date, index=True)      # statutory (ATO/ASIC) date
    status: Mapped[str] = mapped_column(String(20), default="not_started", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(10), default="Normal", nullable=False)
    assignee_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"), index=True)
    reviewer_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    budget_minutes: Mapped[int | None] = mapped_column(Integer)
    fee_cents: Mapped[int | None] = mapped_column(Integer)
    recurring_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("practice_recurring_jobs.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)   # manual · recurring · onboarding
    checklist: Mapped[list] = mapped_column(JSON, default=list, nullable=False)          # [{key,label,done}]
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (Index("ix_practice_jobs_tenant_status_due", "tenant_id", "status", "due_on"),
                      Index("ix_practice_jobs_recurring_period", "recurring_job_id", "period_label"))


class RecurringJob(Base, UuidPk, Timestamps):
    __tablename__ = "practice_recurring_jobs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    name_template: Mapped[str] = mapped_column(String(200), nullable=False)   # "BAS {period}"
    job_type: Mapped[str] = mapped_column(String(40), default="BAS", nullable=False)
    frequency: Mapped[str] = mapped_column(String(12), default="quarterly", nullable=False)
    month_offset: Mapped[int] = mapped_column(Integer, default=1, nullable=False)     # months after period end the job is due
    day_of_month: Mapped[int] = mapped_column(Integer, default=28, nullable=False)
    advance_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)    # create the job this many days before due
    assignee_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    budget_minutes: Mapped[int | None] = mapped_column(Integer)
    fee_cents: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_period_label: Mapped[str | None] = mapped_column(String(40))
    next_due_on: Mapped[date | None] = mapped_column(Date, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))


class TimeEntry(Base, UuidPk, Timestamps):
    __tablename__ = "practice_time_entries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("practice_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False, index=True)
    worked_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
