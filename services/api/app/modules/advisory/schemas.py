from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SnapshotIn(BaseModel):
    client_id: uuid.UUID
    as_at: date | None = None
    period_label: str | None = Field(default=None, max_length=40)
    workpaper_id: uuid.UUID | None = None
    # manual entry (all optional; anything omitted is taken from the workpaper when one is given)
    revenue_cents: int | None = None
    gross_profit_cents: int | None = None
    expenses_cents: int | None = None
    net_profit_cents: int | None = None
    cash_cents: int | None = None
    receivables_cents: int | None = None
    payables_cents: int | None = None
    inventory_cents: int | None = None
    debt_cents: int | None = None
    equity_cents: int | None = None
    tax_provision_cents: int | None = None
    notes: str | None = None


class SnapshotOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    as_at: date
    period_label: str | None
    source: str
    simulated: bool
    workpaper_id: uuid.UUID | None
    revenue_cents: int | None
    gross_profit_cents: int | None
    expenses_cents: int | None
    net_profit_cents: int | None
    cash_cents: int | None
    receivables_cents: int | None
    payables_cents: int | None
    inventory_cents: int | None
    debt_cents: int | None
    equity_cents: int | None
    tax_provision_cents: int | None
    kpis: dict[str, Any]
    health_score: int | None
    health_band: str | None
    notes: str | None
    created_by_name: str | None
    created_at: datetime


class AlertOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    snapshot_id: uuid.UUID | None
    code: str
    title: str
    detail: str | None
    severity: str
    metric: str | None
    value: float | None
    benchmark: float | None
    recommendation: str | None
    status: str
    auto: bool
    created_at: datetime


class AlertIn(BaseModel):
    client_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    detail: str | None = None
    severity: Literal["info", "watch", "action"] = "watch"
    recommendation: str | None = None


class DismissIn(BaseModel):
    reason: str = Field(min_length=2, max_length=300)


class ActionIn(BaseModel):
    client_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    detail: str | None = None
    owner_side: Literal["practice", "client"] = "practice"
    owner_membership_id: uuid.UUID | None = None
    owner_label: str | None = Field(default=None, max_length=200)
    due_on: date | None = None
    visible_to_client: bool = True
    alert_id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None


class ActionOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    meeting_id: uuid.UUID | None
    alert_id: uuid.UUID | None
    title: str
    detail: str | None
    owner_side: str
    owner_name: str | None
    due_on: date | None
    overdue: bool
    status: str
    visible_to_client: bool
    completed_at: datetime | None
    task_id: uuid.UUID | None
    created_at: datetime


class ActionPatch(BaseModel):
    status: Literal["open", "in_progress", "done", "cancelled"] | None = None
    due_on: date | None = None
    owner_membership_id: uuid.UUID | None = None
    owner_label: str | None = None
    visible_to_client: bool | None = None


class AgendaItem(BaseModel):
    title: str
    note: str | None = None
    source: str = "manual"       # manual · alert · action · kpi
    source_ref: str | None = None
    decision: str | None = None


class MeetingIn(BaseModel):
    client_id: uuid.UUID
    title: str | None = Field(default=None, max_length=300)
    kind: Literal["quarterly", "monthly", "annual", "adhoc"] = "quarterly"
    scheduled_for: date | None = None
    snapshot_id: uuid.UUID | None = None


class MeetingPatch(BaseModel):
    title: str | None = None
    scheduled_for: date | None = None
    agenda: list[AgendaItem] | None = None
    summary: str | None = None


class MeetingOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    snapshot_id: uuid.UUID | None
    title: str
    kind: str
    scheduled_for: date | None
    status: str
    agenda: list[AgendaItem]
    summary: str | None
    prepared_by_name: str | None
    held_at: datetime | None
    published_at: datetime | None
    document_id: uuid.UUID | None
    action_count: int
    created_at: datetime


class MeetingDetail(MeetingOut):
    snapshot: SnapshotOut | None
    alerts: list[AlertOut]
    actions: list[ActionOut]


class HoldIn(BaseModel):
    summary: str = Field(min_length=2, max_length=8000)
    decisions: dict[str, str] = {}          # agenda title → decision
    actions: list[ActionIn] = []


class ClientAdvisoryOut(BaseModel):
    client_id: uuid.UUID
    client_name: str
    latest: SnapshotOut | None
    history: list[SnapshotOut]
    alerts: list[AlertOut]
    actions: list[ActionOut]
    meetings: list[MeetingOut]


class OverviewOut(BaseModel):
    clients_with_snapshots: int
    open_alerts: int
    action_alerts: int
    open_actions: int
    overdue_actions: int
    meetings_scheduled: int
    meetings_held_90d: int
    avg_health_score: int | None
    attention: list[dict[str, Any]]
