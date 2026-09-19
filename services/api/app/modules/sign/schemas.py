from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class SignerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    contact_id: uuid.UUID | None = None


class AgreementIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    document_id: uuid.UUID
    client_id: uuid.UUID | None = None
    kind: Literal["engagement_letter", "declaration", "resolution", "agreement"] = "agreement"
    message: str | None = Field(default=None, max_length=4000)
    signers: list[SignerIn] = Field(min_length=1, max_length=20)
    require_identity: bool = False
    expires_in_days: int = Field(default=30, ge=1, le=365)
    send_now: bool = True


class SignerOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    contact_id: uuid.UUID | None
    order: int
    status: str
    viewed_at: datetime | None
    signed_at: datetime | None
    declined_at: datetime | None
    decline_reason: str | None
    signature_kind: str | None
    signature_sha256: str | None
    identity_verified: bool


class SignEventOut(BaseModel):
    id: uuid.UUID
    kind: str
    at: datetime
    signer_name: str | None
    ip: str | None
    detail: dict[str, Any]
    hash: str


class AgreementOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID | None
    client_name: str | None
    document_id: uuid.UUID
    document_filename: str | None
    document_sha256: str | None
    title: str
    kind: str
    message: str | None
    status: str
    require_identity: bool
    created_by_name: str | None
    sent_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None
    sealed_sha256: str | None
    chain_head: str | None
    signers: list[SignerOut]
    created_at: datetime


class AgreementDetail(AgreementOut):
    events: list[SignEventOut]
    certificate: dict[str, Any] | None


class VoidIn(BaseModel):
    reason: str = Field(min_length=2, max_length=300)


class OverviewOut(BaseModel):
    awaiting: int
    completed_30d: int
    declined: int
    expiring_7d: int


# ------------------------------------------------------------------ public signing
class PublicSignerView(BaseModel):
    agreement_id: uuid.UUID
    title: str
    kind: str
    message: str | None
    practice_name: str
    document_filename: str
    document_content_type: str
    document_sha256: str
    signer_name: str
    signer_email: str
    signer_status: str
    agreement_status: str
    require_identity: bool
    identity_ok: bool
    expires_at: datetime | None
    other_signers: list[dict[str, str]]


class PublicSignIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    signature_kind: Literal["typed", "drawn"]
    signature_data: str = Field(min_length=1, max_length=400_000)   # typed name or a data:image/png;base64 URL
    consent: bool


class PublicDeclineIn(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
