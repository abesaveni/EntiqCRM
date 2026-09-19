from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    client_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None


class FolderOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    name: str
    path: str
    kind: str
    depth: int
    document_count: int


class FileIn(BaseModel):
    folder_id: uuid.UUID | None = None
    tags: list[str] = Field(default=[], max_length=20)
    kind: str | None = Field(default=None, max_length=40)
    reindex: bool = True


class DocumentRow(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID | None
    client_name: str | None
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
    visible_to_client: bool
    created_at: datetime
    folder_id: uuid.UUID | None
    folder_path: str | None
    tags: list[str]
    text_source: str
    pages: int | None
    retain_until: date | None
    snippet: str | None = None


class SearchIn(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    client_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    kind: str | None = None
    module_key: str | None = None
    visible_to_client: bool | None = None
    retention_hold: bool | None = None
    limit: int = Field(default=100, ge=1, le=500)


class PolicyIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    kinds: list[str] = []
    years: int = Field(default=7, ge=1, le=50)
    trigger: Literal["created", "period_end", "engagement_end", "lodgement"] = "created"
    action: Literal["review", "hold", "delete"] = "review"
    reference: str | None = Field(default=None, max_length=200)


class PolicyOut(PolicyIn):
    id: uuid.UUID
    is_active: bool
    documents: int


class RetentionRow(BaseModel):
    document_id: uuid.UUID
    filename: str
    client_id: uuid.UUID | None
    client_name: str | None
    kind: str
    policy_name: str | None
    action: str
    retain_until: date
    due: bool
    retention_hold: bool
    created_at: datetime


class OverviewOut(BaseModel):
    documents: int
    bytes_total: int
    unfiled: int
    searchable: int
    needs_ocr: int
    on_hold: int
    shared_with_clients: int
    retention_due: int
    by_module: dict[str, int]
    by_kind: dict[str, int]
    policies: int
