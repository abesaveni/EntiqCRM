from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Purpose = Literal["tax_return", "bas", "financials", "lending", "onboarding", "audit", "custom"]
Category = Literal["identity", "financial", "tax", "bank", "payroll", "legal", "property", "other"]


class ItemIn(BaseModel):
    key: str | None = Field(default=None, max_length=60)
    label: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=600)
    category: Category = "other"
    required: bool = True


class QuestionIn(BaseModel):
    key: str
    label: str
    adds: list[str] = []          # template item keys added when answered yes


class PackIn(BaseModel):
    client_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=300)
    purpose: Purpose = "custom"
    period_label: str | None = Field(default=None, max_length=40)
    message: str | None = Field(default=None, max_length=4000)
    due_in_days: int = Field(default=14, ge=1, le=365)
    use_template: bool = True
    items: list[ItemIn] = []
    send_now: bool = True


class ItemOut(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    description: str | None
    category: str
    required: bool
    order: int
    status: str
    document_id: uuid.UUID | None
    document_filename: str | None
    client_note: str | None
    rejection_reason: str | None
    classification: dict[str, Any]
    uploaded_at: datetime | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None


class QuestionOut(BaseModel):
    key: str
    label: str
    answer: bool | None
    adds: list[str]


class PackOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    contact_id: uuid.UUID | None
    contact_name: str | None
    contact_email: str | None
    title: str
    purpose: str
    period_label: str | None
    message: str | None
    status: str
    due_on: date | None
    overdue: bool
    items_total: int
    items_required: int
    items_done: int          # accepted or not_applicable
    items_uploaded: int      # awaiting review
    items_rejected: int
    exceptions: int          # uploaded items whose classification flags a mismatch
    created_by_name: str | None
    sent_at: datetime | None
    submitted_at: datetime | None
    completed_at: datetime | None
    reminder_count: int
    last_reminded_at: datetime | None
    token_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PackDetail(PackOut):
    items: list[ItemOut]
    questions: list[QuestionOut]
    request_url: str | None = None


class ReviewIn(BaseModel):
    decision: Literal["accept", "reject"]
    reason: str | None = Field(default=None, max_length=600)


class AddItemsIn(BaseModel):
    items: list[ItemIn] = Field(min_length=1, max_length=40)
    notify: bool = True


class OverviewOut(BaseModel):
    awaiting_client: int
    awaiting_review: int
    exceptions: int
    overdue: int
    completed_30d: int
    avg_days_to_submit: float | None


class TemplateOut(BaseModel):
    purpose: str
    label: str
    items: list[dict[str, Any]]
    questions: list[dict[str, Any]]


# ------------------------------------------------------------------ public (client)
class PublicPack(BaseModel):
    practice_name: str
    client_name: str
    contact_name: str | None
    title: str
    purpose: str
    message: str | None
    status: str
    due_on: date | None
    items: list[ItemOut]
    questions: list[QuestionOut]
    expires_at: datetime | None
    can_submit: bool
    outstanding: list[str]


class AnswerIn(BaseModel):
    key: str
    answer: bool


class NotApplicableIn(BaseModel):
    note: str = Field(min_length=2, max_length=600)
