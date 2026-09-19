from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal["not_started", "in_progress", "waiting_client", "review", "complete", "cancelled"]
Frequency = Literal["monthly", "quarterly", "biannual", "annual"]


class ChecklistItem(BaseModel):
    key: str
    label: str
    done: bool = False


class JobIn(BaseModel):
    client_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    job_type: str = Field(default="Other", max_length=40)
    period_label: str | None = Field(default=None, max_length=40)
    period_start: date | None = None
    period_end: date | None = None
    due_on: date | None = None
    lodgement_due: date | None = None
    priority: Literal["Low", "Normal", "High"] = "Normal"
    assignee_membership_id: uuid.UUID | None = None
    reviewer_membership_id: uuid.UUID | None = None
    budget_minutes: int | None = Field(default=None, ge=0)
    fee_cents: int | None = Field(default=None, ge=0)
    checklist: list[ChecklistItem] | None = None
    notes: str | None = None


class JobPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    job_type: str | None = None
    period_label: str | None = None
    due_on: date | None = None
    lodgement_due: date | None = None
    priority: Literal["Low", "Normal", "High"] | None = None
    assignee_membership_id: uuid.UUID | None = None
    reviewer_membership_id: uuid.UUID | None = None
    budget_minutes: int | None = None
    fee_cents: int | None = None
    checklist: list[ChecklistItem] | None = None
    notes: str | None = None


class StatusIn(BaseModel):
    status: JobStatus
    note: str | None = Field(default=None, max_length=500)


class JobOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    title: str
    job_type: str
    period_label: str | None
    period_start: date | None
    period_end: date | None
    due_on: date | None
    lodgement_due: date | None
    status: str
    priority: str
    assignee_membership_id: uuid.UUID | None
    assignee_name: str | None
    reviewer_name: str | None
    budget_minutes: int | None
    actual_minutes: int
    fee_cents: int | None
    recurring_job_id: uuid.UUID | None
    source: str
    checklist: list[ChecklistItem]
    notes: str | None
    overdue: bool
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class RecurringIn(BaseModel):
    client_id: uuid.UUID
    name_template: str = Field(default="{type} {period}", max_length=200)
    job_type: str = Field(default="BAS", max_length=40)
    frequency: Frequency = "quarterly"
    month_offset: int = Field(default=1, ge=0, le=12)
    day_of_month: int = Field(default=28, ge=1, le=28)
    advance_days: int = Field(default=14, ge=0, le=120)
    assignee_membership_id: uuid.UUID | None = None
    budget_minutes: int | None = Field(default=None, ge=0)
    fee_cents: int | None = Field(default=None, ge=0)
    notes: str | None = None


class RecurringOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    name_template: str
    job_type: str
    frequency: str
    month_offset: int
    day_of_month: int
    advance_days: int
    assignee_name: str | None
    budget_minutes: int | None
    fee_cents: int | None
    is_active: bool
    last_period_label: str | None
    next_due_on: date | None
    notes: str | None
    created_at: datetime


class TimeIn(BaseModel):
    worked_on: date
    minutes: int = Field(gt=0, le=24 * 60)
    billable: bool = True
    note: str | None = Field(default=None, max_length=500)


class TimeOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    membership_id: uuid.UUID
    member_name: str | None
    worked_on: date
    minutes: int
    billable: bool
    note: str | None
    created_at: datetime


class DeadlineOut(BaseModel):
    on: date
    kind: str                # job · statutory
    label: str
    job_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    client_name: str | None = None
    overdue: bool = False
    detail: str | None = None


class TeamMember(BaseModel):
    membership_id: uuid.UUID
    name: str
    role: str
    open_jobs: int
    overdue_jobs: int
    minutes_this_month: int
    budget_minutes_open: int


class OverviewOut(BaseModel):
    open_jobs: int
    overdue: int
    due_7d: int
    unassigned: int
    waiting_client: int
    in_review: int
    completed_30d: int
    by_type: dict[str, int]
    minutes_this_month: int
    recurring_active: int
    upcoming: list[DeadlineOut]
    stats: dict[str, Any] = {}
