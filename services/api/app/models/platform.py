"""
Cross-cutting platform tables (M4): in-app notifications, the outbound email outbox,
documents, the billing ledger and lifecycle notice tracking.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk


class Notification(Base, UuidPk):
    """In-app notification for one member. The bell in the shell reads these."""
    __tablename__ = "notifications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(String(1000))
    link: Mapped[str | None] = mapped_column(String(300))
    module_key: Mapped[str] = mapped_column(String(32), default="hq", nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    __table_args__ = (Index("ix_notifications_member_unread", "tenant_id", "membership_id", "read_at"),)


class OutboundMessage(Base, UuidPk):
    """
    Email outbox. Rows are queued inside the request transaction and delivered by
    mailer.deliver_pending() — so a mail server outage never fails a user action, and
    nothing is sent for a transaction that rolled back. EXEMPT from the tenant filter:
    the delivery job runs with no tenant.
    """
    __tablename__ = "outbound_messages"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    channel: Mapped[str] = mapped_column(String(10), default="email", nullable=False)
    to_address: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str | None] = mapped_column(Text)
    template: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False, index=True)  # queued | sent | failed | skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    ref_type: Mapped[str | None] = mapped_column(String(40))
    ref_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class Document(Base, UuidPk, Timestamps):
    """A stored file. Bytes live in the storage backend under storage_key; this row is the permission-aware index."""
    __tablename__ = "documents"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    module_key: Mapped[str] = mapped_column(String(32), default="crm", nullable=False)
    kind: Mapped[str] = mapped_column(String(40), default="general", nullable=False)   # general · identity · agreement · financial · correspondence …
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    uploaded_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    scan_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # clean · infected · unavailable · pending
    # Compliance: a held document cannot be deleted by anyone until the hold is lifted by an owner/admin.
    retention_hold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retention_until: Mapped[date | None] = mapped_column(Date)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (Index("ix_documents_tenant_client", "tenant_id", "client_id", "deleted_at"),)


class BillingEvent(Base):
    """Append-only, hash-chained billing ledger. Money is never edited — corrections are new rows."""
    __tablename__ = "billing_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    module_key: Mapped[str | None] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)   # trial.started · subscription.started · subscription.cancelled · charge.simulated · charge.succeeded · charge.failed · refund
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)     # ex GST
    gst_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="AUD", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="recorded", nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    stripe_ref: Mapped[str | None] = mapped_column(String(80))
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class LifecycleNotice(Base, UuidPk):
    """Which lifecycle communications a tenant has already received — reminders are sent exactly once."""
    __tablename__ = "lifecycle_notices"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)   # trial_day10 · trial_day14 · trial_ended · payment_failed · suspended · cancelled
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    __table_args__ = (UniqueConstraint("tenant_id", "kind", name="uq_lifecycle_notice"),)
