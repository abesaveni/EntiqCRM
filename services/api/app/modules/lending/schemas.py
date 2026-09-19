from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Purpose = Literal["equipment", "vehicle", "property", "working_capital", "refinance", "expansion", "other"]
Stage = Literal["enquiry", "information", "assessment", "submitted", "approved", "conditions", "settled", "declined", "withdrawn"]


class ApplicationIn(BaseModel):
    client_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    purpose: Purpose = "equipment"
    description: str | None = Field(default=None, max_length=4000)
    amount_cents: int = Field(gt=0)
    term_months: int | None = Field(default=None, ge=1, le=600)
    rate_bps: int | None = Field(default=None, ge=0, le=10000)
    lender: str | None = Field(default=None, max_length=120)
    owner_membership_id: uuid.UUID | None = None
    expected_settlement: date | None = None
    send_request: bool = True         # open a Requests pack for the lending checklist


class ApplicationPatch(BaseModel):
    purpose: Purpose | None = None
    description: str | None = None
    amount_cents: int | None = Field(default=None, gt=0)
    term_months: int | None = None
    rate_bps: int | None = None
    repayment_cents: int | None = None
    lender: str | None = None
    owner_membership_id: uuid.UUID | None = None
    expected_settlement: date | None = None


class ServiceabilityIn(BaseModel):
    ebitda_cents: int | None = None
    existing_repayments_cents: int | None = None
    proposed_repayment_cents: int | None = None
    notes: str | None = Field(default=None, max_length=2000)
    use_snapshot: bool = True          # pull EBITDA from the latest Advisory snapshot when present


class StageIn(BaseModel):
    stage: Stage
    note: str | None = Field(default=None, max_length=2000)


class ConditionIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    detail: str | None = None
    kind: Literal["precedent", "subsequent"] = "precedent"
    owner_side: Literal["client", "practice", "lender"] = "client"
    due_on: date | None = None


class ConditionSatisfyIn(BaseModel):
    note: str | None = Field(default=None, max_length=600)
    document_id: uuid.UUID | None = None
    waive: bool = False


class ConditionOut(BaseModel):
    id: uuid.UUID
    title: str
    detail: str | None
    kind: str
    owner_side: str
    due_on: date | None
    overdue: bool
    status: str
    document_id: uuid.UUID | None
    note: str | None
    satisfied_at: datetime | None
    satisfied_by_name: str | None


class EventOut(BaseModel):
    id: uuid.UUID
    kind: str
    from_stage: str | None
    to_stage: str | None
    note: str | None
    actor_label: str
    at: datetime


class ApplicationOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    contact_name: str | None
    reference: str
    purpose: str
    description: str | None
    amount_cents: int
    term_months: int | None
    rate_bps: int | None
    repayment_cents: int | None
    lender: str | None
    stage: str
    stage_index: int
    owner_name: str | None
    request_pack_id: uuid.UUID | None
    readiness_pct: int
    serviceability: dict[str, Any]
    dscr: float | None
    decision_note: str | None
    submitted_at: datetime | None
    approved_at: datetime | None
    settled_at: datetime | None
    settlement_date: date | None
    expected_settlement: date | None
    closed_at: datetime | None
    close_reason: str | None
    conditions_open: int
    conditions_blocking: int
    created_at: datetime
    updated_at: datetime


class ApplicationDetail(ApplicationOut):
    conditions: list[ConditionOut]
    events: list[EventOut]
    documents_outstanding: list[str]
    request_status: str | None


class OverviewOut(BaseModel):
    active: int
    pipeline_value_cents: int
    settled_90d: int
    settled_value_90d_cents: int
    awaiting_client: int
    conditions_open: int
    by_stage: dict[str, int]
    conversion_pct: int | None
