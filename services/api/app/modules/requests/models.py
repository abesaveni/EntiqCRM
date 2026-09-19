"""
EnTIQ Requests (module 06) — adaptive, secure information requests. Ported from RequestIQ
(intake → classification → adaptive checklist → exceptions-only review) and GrowAccounting's
document_requests, re-keyed to the CRM client and the shared Documents store.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

PACK_STATUSES = ("draft", "sent", "in_progress", "submitted", "reviewing", "complete", "cancelled")
ITEM_STATUSES = ("pending", "uploaded", "accepted", "rejected", "not_applicable")
PURPOSES = ("tax_return", "bas", "financials", "lending", "onboarding", "audit", "custom")


class RequestPack(Base, UuidPk, Timestamps):
    __tablename__ = "request_packs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), default="custom", nullable=False)
    period_label: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)
    due_on: Mapped[date | None] = mapped_column(Date, index=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)     # adaptive questions: [{key,label,answer,adds:[item keys]}]
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    reminder_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reminded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    items: Mapped[list["RequestItem"]] = relationship(back_populates="pack", cascade="all, delete-orphan", order_by="RequestItem.order")

    __table_args__ = (Index("ix_request_packs_tenant_status", "tenant_id", "status"),)


class RequestItem(Base, UuidPk, Timestamps):
    __tablename__ = "request_items"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    pack_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("request_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(600))
    category: Mapped[str] = mapped_column(String(20), default="other", nullable=False)   # identity · financial · tax · bank · payroll · legal · property · other
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="SET NULL"))
    client_note: Mapped[str | None] = mapped_column(String(600))
    rejection_reason: Mapped[str | None] = mapped_column(String(600))
    classification: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)   # {detected, confidence, matches_item, flags:[…]}
    uploaded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    reviewed_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    pack: Mapped[RequestPack] = relationship(back_populates="items")

    __table_args__ = (Index("ix_request_items_pack_key", "pack_id", "key", unique=True),)
