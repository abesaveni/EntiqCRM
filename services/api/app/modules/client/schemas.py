from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


# ------------------------------------------------------------------ staff side
class PortalContactOut(BaseModel):
    contact_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    name: str
    email: str | None
    role: str | None
    has_portal_access: bool
    invited_at: datetime | None
    last_login_at: datetime | None
    active_sessions: int


class ThreadMessage(BaseModel):
    id: uuid.UUID
    from_client: bool
    author: str
    body: str
    created_at: datetime
    read: bool


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class StaffOverview(BaseModel):
    contacts_with_access: int
    clients_with_access: int
    logins_30d: int
    unread_messages: int
    shared_documents: int


# ------------------------------------------------------------------ portal auth
class RequestLinkIn(BaseModel):
    email: EmailStr


class ExchangeIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class PortalTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    practice_name: str
    client_name: str


# ------------------------------------------------------------------ portal (client) side
class PortalMe(BaseModel):
    contact_id: uuid.UUID
    name: str
    email: str | None
    client_id: uuid.UUID
    client_name: str
    client_type: str
    practice_name: str
    practice_email: str | None
    practice_phone: str | None
    features: dict[str, bool]        # documents · requests · agreements · jobs · messages — what the practice has switched on
    counts: dict[str, int]           # open_requests · awaiting_signature · unread_messages · shared_documents


class PortalDocument(BaseModel):
    id: uuid.UUID
    filename: str
    kind: str
    size_bytes: int
    content_type: str
    uploaded_by: str          # "You" · "Practice"
    created_at: datetime


class PortalRequest(BaseModel):
    id: uuid.UUID
    title: str
    purpose: str
    status: str
    due_on: date | None
    overdue: bool
    items_total: int
    items_done: int
    outstanding: int


class PortalAgreement(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    status: str
    my_status: str
    sent_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None


class PortalJob(BaseModel):
    id: uuid.UUID
    title: str
    job_type: str
    period_label: str | None
    status: str
    due_on: date | None
    completed_at: datetime | None


class PortalActivity(BaseModel):
    kind: str
    summary: str
    module_key: str
    occurred_at: datetime


class PortalHome(BaseModel):
    me: PortalMe
    requests: list[PortalRequest]
    agreements: list[PortalAgreement]
    jobs: list[PortalJob]
    recent: list[PortalActivity]
    messages: list[ThreadMessage]


class PortalUploadOut(BaseModel):
    document: PortalDocument
    message: str


EXTRA: dict[str, Any] = {}
