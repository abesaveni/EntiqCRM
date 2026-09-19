from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StartVerificationIn(BaseModel):
    subject_type: Literal["individual", "entity"] = "individual"
    contact_id: uuid.UUID | None = None


class VerificationOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    contact_id: uuid.UUID | None
    subject_type: str
    subject_name: str
    provider: str
    simulated: bool
    status: str
    verification_url: str | None
    result: dict[str, Any]
    failure_reason: str | None
    started_by_name: str | None
    completed_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


class ScreenIn(BaseModel):
    contact_id: uuid.UUID | None = None
    dob: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class ScreeningOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None = None
    contact_id: uuid.UUID | None
    subject_type: str
    subject_name: str
    provider: str
    simulated: bool
    status: str
    match_count: int
    matches: list[dict[str, Any]]
    threshold: int
    error: str | None
    screened_at: datetime
    review_decision: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    review_notes: str | None


class ReviewIn(BaseModel):
    decision: Literal["true_match", "false_positive"]
    notes: str | None = Field(default=None, max_length=2000)


class RiskOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    rating: str
    score: int
    method: str
    factors: list[dict[str, Any]]
    assessed_by_name: str | None
    assessed_at: datetime
    next_review_at: datetime
    notes: str | None


class AssessIn(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class PartyStatus(BaseModel):
    contact_id: uuid.UUID
    name: str
    role: str | None
    identity_status: str          # verified | in_progress | failed | none
    identity_simulated: bool
    screening_status: str         # clear | potential_match | confirmed_match | false_positive | none
    screening_simulated: bool


class ClientVerifyOut(BaseModel):
    client_id: uuid.UUID
    client_name: str
    client_type: str
    risk: RiskOut | None
    entity_screening: ScreeningOut | None
    entity_verification: VerificationOut | None
    parties: list[PartyStatus]
    verifications: list[VerificationOut]
    screenings: list[ScreeningOut]
    providers: dict[str, Any]


class OverviewOut(BaseModel):
    verifications_pending: int
    verifications_verified: int
    screenings_to_review: int
    reviews_due_30d: int
    clients_unassessed: int
    providers: dict[str, Any]


class ReviewDueOut(BaseModel):
    client_id: uuid.UUID
    client_name: str
    rating: str
    next_review_at: datetime
    overdue: bool
