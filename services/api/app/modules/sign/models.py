"""
EnTIQ Sign (module 05) — prepare, send, sign, seal, prove.

An Agreement wraps one stored Document and one or more Signers. Every material action
is a SignEvent in a per-agreement hash chain; completion seals the agreement with a hash
over the document and every signature, and produces a certificate anyone can verify
independently. Signed agreements are legal records: they are never deleted.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

AGREEMENT_STATUSES = ("draft", "sent", "partially_signed", "completed", "declined", "voided", "expired")
SIGNER_STATUSES = ("pending", "sent", "viewed", "signed", "declined")


class Agreement(Base, UuidPk, Timestamps):
    __tablename__ = "agreements"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40), default="agreement", nullable=False)   # engagement_letter · declaration · resolution · agreement
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    # Verify interlink: signers must hold a current, non-simulated identity verification.
    require_identity: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    voided_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    void_reason: Mapped[str | None] = mapped_column(String(300))
    sealed_sha256: Mapped[str | None] = mapped_column(String(64))
    certificate: Mapped[dict | None] = mapped_column(JSON)
    chain_head: Mapped[str | None] = mapped_column(String(64))

    signers: Mapped[list["Signer"]] = relationship(back_populates="agreement", cascade="all, delete-orphan", order_by="Signer.order")

    __table_args__ = (Index("ix_agreements_tenant_status", "tenant_id", "status"),)


class Signer(Base, UuidPk, Timestamps):
    __tablename__ = "signers"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agreement_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    viewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    consented_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    signed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    declined_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    decline_reason: Mapped[str | None] = mapped_column(String(500))
    signature_kind: Mapped[str | None] = mapped_column(String(10))            # typed | drawn
    signature_data: Mapped[str | None] = mapped_column(Text)                  # typed name, or data:image/png;base64,…
    signature_sha256: Mapped[str | None] = mapped_column(String(64))
    identity_verification_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # the Verify record relied upon, if any
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))

    agreement: Mapped[Agreement] = relationship(back_populates="signers")


class SignEvent(Base, UuidPk):
    """Evidence trail. Hash-chained per agreement; the chain head is stored on the agreement and in the certificate."""
    __tablename__ = "sign_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agreement_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    signer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("signers.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)   # created · sent · reminded · viewed · consented · signed · declined · completed · voided · identity_checked
    at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    __table_args__ = (Index("ix_sign_events_agreement_at", "agreement_id", "at"),)
