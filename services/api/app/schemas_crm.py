from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

ClientType = Literal["Company", "Trust", "Individual", "Partnership", "SMSF", "Other"]
Stage = Literal["Lead", "Proposal", "Onboarding", "Active", "Review", "Dormant", "Lost"]
Priority = Literal["Low", "Normal", "High"]
TaskStatus = Literal["open", "done", "cancelled"]


def _digits(v: str | None) -> str | None:
    if v is None:
        return None
    d = "".join(ch for ch in v if ch.isdigit())
    return d or None


# ------------------------------------------------------------------ clients
class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    legal_name: str | None = Field(default=None, max_length=300)
    client_type: ClientType = "Company"
    abn: str | None = Field(default=None, max_length=20)
    acn: str | None = Field(default=None, max_length=20)
    stage: Stage = "Lead"
    owner_membership_id: uuid.UUID | None = None
    since: date | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    website: str | None = Field(default=None, max_length=255)
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    suburb: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=10)
    postcode: str | None = Field(default=None, max_length=10)
    country: str = Field(default="AU", min_length=2, max_length=2)
    source: str | None = Field(default=None, max_length=40)
    tags: list[str] = []
    custom: dict[str, Any] = {}

    @field_validator("abn", "acn")
    @classmethod
    def _norm(cls, v: str | None) -> str | None:
        return _digits(v)

    @field_validator("abn")
    @classmethod
    def _abn_len(cls, v: str | None) -> str | None:
        if v is not None and len(v) != 11:
            raise ValueError("ABN must be 11 digits")
        return v

    @field_validator("acn")
    @classmethod
    def _acn_len(cls, v: str | None) -> str | None:
        if v is not None and len(v) != 9:
            raise ValueError("ACN must be 9 digits")
        return v


class ClientPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    legal_name: str | None = None
    client_type: ClientType | None = None
    abn: str | None = None
    acn: str | None = None
    owner_membership_id: uuid.UUID | None = None
    since: date | None = None
    email: EmailStr | None = None
    phone: str | None = None
    website: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    suburb: str | None = None
    state: str | None = None
    postcode: str | None = None
    country: str | None = None
    source: str | None = None
    tags: list[str] | None = None
    custom: dict[str, Any] | None = None

    @field_validator("abn", "acn")
    @classmethod
    def _norm(cls, v: str | None) -> str | None:
        return _digits(v)


class StageIn(BaseModel):
    stage: Stage
    reason: str | None = Field(default=None, max_length=300)


class ContactOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    first_name: str
    last_name: str | None
    full_name: str
    email: str | None
    phone: str | None
    role: str | None
    is_primary: bool
    notes: str | None
    has_portal_access: bool
    created_at: datetime


class ClientOut(BaseModel):
    id: uuid.UUID
    name: str
    legal_name: str | None
    client_type: str
    abn: str | None
    abn_formatted: str | None
    acn: str | None
    stage: str
    owner_membership_id: uuid.UUID | None
    owner_name: str | None
    risk_rating: str | None
    risk_assessed_at: datetime | None
    since: date | None
    email: str | None
    phone: str | None
    website: str | None
    address_line1: str | None
    address_line2: str | None
    suburb: str | None
    state: str | None
    postcode: str | None
    country: str
    source: str | None
    external_ref: str | None
    tags: list[str]
    custom: dict[str, Any]
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # aggregates
    contact_count: int = 0
    open_task_count: int = 0
    primary_contact: ContactOut | None = None


class ClientPage(BaseModel):
    items: list[ClientOut]
    total: int
    page: int
    size: int


# ------------------------------------------------------------------ contacts / relationships
class ContactIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    role: str | None = Field(default=None, max_length=80)
    is_primary: bool = False
    notes: str | None = None


class ContactPatch(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    role: str | None = None
    is_primary: bool | None = None
    notes: str | None = None


class RelationshipIn(BaseModel):
    from_type: Literal["client", "contact"]
    from_id: uuid.UUID
    to_type: Literal["client", "contact"]
    to_id: uuid.UUID
    kind: str = Field(min_length=2, max_length=30)
    percentage: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=300)


class RelationshipOut(BaseModel):
    id: uuid.UUID
    from_type: str
    from_id: uuid.UUID
    from_label: str
    to_type: str
    to_id: uuid.UUID
    to_label: str
    kind: str
    percentage: int | None
    notes: str | None
    ended_at: datetime | None


# ------------------------------------------------------------------ timeline / tasks / notes
class TimelineOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID | None
    client_name: str | None = None
    module_key: str
    kind: str
    summary: str
    detail: dict[str, Any]
    actor_label: str
    ref_type: str | None
    ref_id: str | None
    occurred_at: datetime


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    client_id: uuid.UUID | None = None
    due_at: datetime | None = None
    priority: Priority = "Normal"
    assignee_membership_id: uuid.UUID | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    due_at: datetime | None = None
    priority: Priority | None = None
    assignee_membership_id: uuid.UUID | None = None
    status: TaskStatus | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID | None
    client_name: str | None
    title: str
    description: str | None
    due_at: datetime | None
    priority: str
    status: str
    assignee_membership_id: uuid.UUID | None
    assignee_name: str | None
    module_key: str
    done_at: datetime | None
    created_at: datetime
    overdue: bool


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    pinned: bool = False


class NoteOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    body: str
    author_name: str | None
    pinned: bool
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ pipeline / home / segments / search
class PipelineColumn(BaseModel):
    stage: str
    count: int
    clients: list[ClientOut]


class HomeOut(BaseModel):
    overdue_tasks: int
    due_this_week: int
    elevated_risk: int
    in_pipeline: int
    total_clients: int
    tasks: list[TaskOut]
    risks: list[ClientOut]
    recent: list[TimelineOut]


class SegmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    filters: dict[str, Any] = {}


class SegmentOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    filters: dict[str, Any]
    member_count: int
    created_at: datetime


class SearchHit(BaseModel):
    type: Literal["client", "contact"]
    id: uuid.UUID
    client_id: uuid.UUID
    label: str
    sublabel: str | None


class StaffOut(BaseModel):
    membership_id: uuid.UUID
    name: str
    email: str
    role: str


class DuplicateGroup(BaseModel):
    reason: Literal["abn", "name"]
    key: str
    clients: list[ClientOut]


# ------------------------------------------------------------------ import
class ImportPreview(BaseModel):
    job_id: uuid.UUID
    source: str
    filename: str
    columns: list[str]
    proposed_mapping: dict[str, str | None]
    row_count: int
    sample: list[dict[str, Any]]
    warnings: list[str]


class ImportCommitIn(BaseModel):
    mapping: dict[str, str | None] = {}
    default_stage: Stage = "Active"
    update_existing: bool = True


class ImportResult(BaseModel):
    job_id: uuid.UUID
    status: str
    row_count: int
    created_count: int
    updated_count: int
    skipped_count: int
    errors: list[str]
