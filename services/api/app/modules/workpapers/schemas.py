from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PackType = Literal["financial_statements", "tax_return", "bas", "smsf", "audit"]
ItemStatus = Literal["not_started", "prepared", "queried", "reviewed", "signed_off", "n_a"]


class PackIn(BaseModel):
    client_id: uuid.UUID
    job_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=300)
    pack_type: PackType = "financial_statements"
    period_label: str | None = Field(default=None, max_length=40)
    period_start: date | None = None
    period_end: date | None = None
    preparer_membership_id: uuid.UUID | None = None
    reviewer_membership_id: uuid.UUID | None = None
    materiality_cents: int | None = Field(default=None, ge=0)
    use_template: bool = True


class ItemIn(BaseModel):
    section: str = Field(max_length=60)
    label: str = Field(min_length=1, max_length=300)
    key: str | None = Field(default=None, max_length=80)
    description: str | None = None
    account_code: str | None = Field(default=None, max_length=40)
    value_cents: int | None = None
    prior_cents: int | None = None


class ItemPatch(BaseModel):
    label: str | None = None
    value_cents: int | None = None
    prior_cents: int | None = None
    account_code: str | None = None
    workings: str | None = Field(default=None, max_length=8000)
    document_id: uuid.UUID | None = None
    status: ItemStatus | None = None


class ItemOut(BaseModel):
    id: uuid.UUID
    section: str
    key: str
    label: str
    description: str | None
    order: int
    account_code: str | None
    value_cents: int | None
    prior_cents: int | None
    variance_cents: int | None
    variance_pct: float | None
    status: str
    evidence_state: str
    document_id: uuid.UUID | None
    document_filename: str | None
    workings: str | None
    query: str | None
    prepared_by_name: str | None
    prepared_at: datetime | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    material: bool


class IssueIn(BaseModel):
    item_id: uuid.UUID | None = None
    kind: Literal["variance", "missing_evidence", "unreconciled", "query", "compliance"] = "query"
    title: str = Field(min_length=2, max_length=300)
    detail: str | None = None
    severity: Literal["low", "medium", "high"] = "medium"
    blocking: bool = False


class IssueResolveIn(BaseModel):
    resolution: str = Field(min_length=2, max_length=600)
    waive: bool = False


class IssueOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID | None
    item_label: str | None
    kind: str
    title: str
    detail: str | None
    severity: str
    blocking: bool
    status: str
    auto: bool
    raised_by_name: str | None
    resolved_by_name: str | None
    resolution: str | None
    resolved_at: datetime | None
    created_at: datetime


class PackOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    job_id: uuid.UUID | None
    title: str
    pack_type: str
    period_label: str | None
    period_start: date | None
    period_end: date | None
    status: str
    preparer_name: str | None
    reviewer_name: str | None
    prepared_at: datetime | None
    reviewed_at: datetime | None
    signed_off_at: datetime | None
    signed_off_by_name: str | None
    lodged_at: datetime | None
    lodgement_ref: str | None
    materiality_cents: int | None
    ledger_source: str
    ledger_synced_at: datetime | None
    ledger_simulated: bool
    seal_sha256: str | None
    items_total: int
    items_done: int
    evidence_attached: int
    open_issues: int
    blocking_issues: int
    net_assets_cents: int | None
    created_at: datetime
    updated_at: datetime


class PackDetail(PackOut):
    items: list[ItemOut]
    issues: list[IssueOut]
    sections: list[str]
    totals: dict[str, int]
    notes: str | None


class SignOffIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class LodgeIn(BaseModel):
    reference: str = Field(min_length=2, max_length=120)
    lodged_on: date | None = None


class OverviewOut(BaseModel):
    in_progress: int
    in_review: int
    signed_off_30d: int
    lodged_30d: int
    open_issues: int
    blocking_issues: int
    by_type: dict[str, int]
    ledger_connections: int
    ledger_live: bool


class LedgerConnectionOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID | None
    client_name: str | None
    provider: str
    status: str
    simulated: bool
    external_name: str | None
    external_tenant_id: str | None
    scopes: str | None
    last_sync_at: datetime | None
    last_error: str | None
    connected_by_name: str | None
    created_at: datetime


class ConnectIn(BaseModel):
    client_id: uuid.UUID
    provider: Literal["xero", "myob"] = "xero"


class SyncOut(BaseModel):
    pack: PackDetail
    synced: int
    simulated: bool
    source: str
    message: str
