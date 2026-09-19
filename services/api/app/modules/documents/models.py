"""
EnTIQ Documents (module 07) — one permission-aware document system for every module.

The base plan already stores files (app/models/platform.py: Document) with scanning, hashing,
retention holds and portal sharing, because every module needs that. This module adds the layer a
practice pays for: folders, tags, extracted text and search across the whole practice, retention
policies that apply themselves, and a storage picture.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

# Retention triggers: what starts the clock
TRIGGERS = ("created", "period_end", "engagement_end", "lodgement")


class Folder(Base, UuidPk, Timestamps):
    """A folder in a client's file. Practice-wide folders have client_id NULL."""
    __tablename__ = "document_folders"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("document_folders.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    path: Mapped[str] = mapped_column(String(600), nullable=False, index=True)   # "Tax/FY26" — denormalised for display and search
    kind: Mapped[str] = mapped_column(String(20), default="custom", nullable=False)   # custom · standard (from the template)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))

    __table_args__ = (Index("ix_document_folders_tenant_client_path", "tenant_id", "client_id", "path"),)


class RetentionPolicy(Base, UuidPk, Timestamps):
    """How long a kind of document is kept, and what happens at the end of it."""
    __tablename__ = "document_retention_policies"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kinds: Mapped[list] = mapped_column(JSON, default=list, nullable=False)     # document kinds this applies to; [] = all
    years: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), default="created", nullable=False)
    action: Mapped[str] = mapped_column(String(12), default="review", nullable=False)   # review · hold · delete
    reference: Mapped[str | None] = mapped_column(String(200))                 # e.g. "AML/CTF Act s.107 — 7 years"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))


class DocumentIndex(Base, UuidPk):
    """
    The searchable side of a document: extracted text and tags, kept apart from the file row so the
    base plan never carries the weight of it.
    """
    __tablename__ = "document_index"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("document_folders.id", ondelete="SET NULL"), index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)               # extracted text, lower-cased at write time
    text_source: Mapped[str] = mapped_column(String(16), default="none", nullable=False)   # none · plain · pdf · ocr
    pages: Mapped[int | None] = mapped_column(Integer)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("document_retention_policies.id", ondelete="SET NULL"))
    retain_until: Mapped[date | None] = mapped_column(Date, index=True)
    indexed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
