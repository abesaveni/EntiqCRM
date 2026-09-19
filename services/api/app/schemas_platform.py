from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    link: str | None
    module_key: str
    read_at: datetime | None
    created_at: datetime


class UnreadOut(BaseModel):
    unread: int


class DocumentOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID | None
    module_key: str
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    description: str | None
    uploaded_by_name: str | None
    scan_status: str
    retention_hold: bool
    visible_to_client: bool = False
    retention_until: date | None
    created_at: datetime


class HoldIn(BaseModel):
    hold: bool
    until: date | None = None
    reason: str | None = Field(default=None, max_length=300)


class BillingEventOut(BaseModel):
    id: int
    module_key: str | None
    kind: str
    amount_cents: int
    gst_cents: int
    total_cents: int
    currency: str
    status: str
    detail: dict[str, Any]
    created_at: datetime


class BillingLine(BaseModel):
    module_key: str
    name: str
    status: str
    pricing_model: str
    unit: str
    indicative_monthly_cents: int | None
    seats: int | None


class BillingSummary(BaseModel):
    tenant_status: str
    base_plan_cents: int
    base_plan_inc_gst_cents: int
    gst_rate_bps: int
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    next_charge_at: datetime | None
    next_charge_estimate_cents: int
    card_on_file: bool
    card_last4: str | None
    free_mode: bool = False        # $0 base plan: nothing is charged in this environment
    billing_mode: str
    lines: list[BillingLine]
    recent: list[BillingEventOut]


class OutboundOut(BaseModel):
    id: uuid.UUID
    to_address: str
    subject: str
    template: str | None
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None
    body_text: str


class TimeTravelIn(BaseModel):
    trial_ends_in_days: float | None = None
    status_changed_days_ago: float | None = None


class ShareIn(BaseModel):
    visible_to_client: bool
