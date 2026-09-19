"""
EnTIQ Verify (module 04) — identity, screening, risk, ongoing monitoring.

The parties of a client are the CRM's contacts and relationship graph; Verify does not
keep its own copy. A Verification or Screening points at the client and, when it is about
a person, at the contact. The latest RiskAssessment writes Client.risk_rating so every
module sees it without importing Verify.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

VERIFICATION_STATUSES = ("pending", "in_progress", "verified", "failed", "expired", "cancelled")
SCREENING_STATUSES = ("clear", "potential_match", "confirmed_match", "false_positive", "error")


class Verification(Base, UuidPk, Timestamps):
    __tablename__ = "verifications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id", ondelete="SET NULL"), index=True)
    subject_type: Mapped[str] = mapped_column(String(12), nullable=False)          # individual | entity
    subject_name: Mapped[str] = mapped_column(String(300), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)             # didit | simulation
    provider_ref: Mapped[str | None] = mapped_column(String(120), index=True)
    verification_url: Mapped[str | None] = mapped_column(String(600))            # where the person completes the check
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)      # normalised: document_type, name_match, dob, liveness, address …
    failure_reason: Mapped[str | None] = mapped_column(String(300))
    started_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())          # verified identity is relied on for 12 months

    __table_args__ = (Index("ix_verifications_tenant_client", "tenant_id", "client_id"),)


class Screening(Base, UuidPk, Timestamps):
    __tablename__ = "screenings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id", ondelete="SET NULL"), index=True)
    subject_type: Mapped[str] = mapped_column(String(12), nullable=False)
    subject_name: Mapped[str] = mapped_column(String(300), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)             # opensanctions | simulation
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="clear", nullable=False, index=True)
    match_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches: Mapped[list] = mapped_column(JSON, default=list, nullable=False)     # [{id, name, score, datasets, topics}]
    threshold: Mapped[int] = mapped_column(Integer, default=70, nullable=False)    # percent
    error: Mapped[str | None] = mapped_column(String(300))
    screened_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    # Human adjudication of a potential match — a hit is never auto-confirmed.
    review_decision: Mapped[str | None] = mapped_column(String(20))              # true_match | false_positive
    reviewed_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    review_notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_screenings_tenant_client", "tenant_id", "client_id"),)


class RiskAssessment(Base, UuidPk):
    __tablename__ = "risk_assessments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    rating: Mapped[str] = mapped_column(String(10), nullable=False)                # Low | Medium | High
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(20), default="rules_v1", nullable=False)
    factors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)     # [{factor, points, note}]
    assessed_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    assessed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    next_review_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_risk_tenant_client_current", "tenant_id", "client_id", "superseded_at"),)
