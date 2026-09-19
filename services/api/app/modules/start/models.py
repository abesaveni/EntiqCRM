"""
EnTIQ Start (module 03) — the 11-stage onboarding orchestrator, ported from EntiqStart.

The prospect is a CRM Client from the first minute (stage Lead → Onboarding → Active), so every
other module sees the same record. Stage order is enforced server-side: stage n cannot complete
until 1..n-1 are complete. Stage 9's gates are read from Verify and Sign in-process.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

STAGES: list[tuple[int, str, str, str, str]] = [
    # number, key, name, who completes it, description
    (1, "invitation", "Invitation", "prospect", "Magic-link invitation opened by the prospect"),
    (2, "entity_details", "Entity details", "prospect", "Legal name, ABN/ACN, structure, tax residency and contact profile"),
    (3, "questionnaire", "Questionnaire", "prospect", "Intake questionnaire and scope discovery"),
    (4, "document_requests", "Documents", "prospect", "Prior financials, deeds and registry extracts uploaded and verified"),
    (5, "related_parties", "Related parties", "prospect", "Directors, trustees and beneficial owners"),
    (6, "service_selection", "Services", "prospect", "Services selected from the practice catalogue"),
    (7, "proposal", "Proposal", "prospect", "Fee proposal issued by the practice and accepted by the prospect"),
    (8, "engagement_prep", "Engagement letter", "practice", "Letter of engagement compiled and sent for signature"),
    (9, "external_checks", "Checks", "practice", "Gateway: identity (KYC), screening (AML), signature and payment mandate"),
    (10, "acceptance", "Acceptance", "practice", "Partner review, margin check and risk sign-off"),
    (11, "activated", "Activated", "practice", "Client activated and handed to the practice"),
]
STAGE_STATUSES = ("pending", "active", "completed", "blocked", "skipped")
ONBOARDING_STATUSES = ("draft", "invited", "in_progress", "awaiting_practice", "activated", "withdrawn")
GATES = ("kyc", "aml", "esign", "mandate")


class ServiceOffering(Base, UuidPk, Timestamps):
    """The practice's service catalogue prospects choose from (stage 6) and proposals are priced from (stage 7)."""
    __tablename__ = "start_services"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)          # tax · bas · ias · financials · bookkeeping · payroll · asic · fbt · advisory · smsf · other
    description: Mapped[str | None] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(String(12), default="annual", nullable=False)   # fixed · monthly · quarterly · annual · hourly
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gst: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    entity_types: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # [] = all
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Onboarding(Base, UuidPk, Timestamps):
    __tablename__ = "onboardings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    primary_contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id", ondelete="SET NULL"))
    owner_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    current_stage: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="email", nullable=False)   # email · qr · manual
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    invited_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    opened_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    withdrawn_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    withdraw_reason: Mapped[str | None] = mapped_column(String(300))
    # stage payloads keyed by stage key; gates keyed by gate name
    data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    gates: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sign_agreement_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    proposal_total_cents: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    stages: Mapped[list["OnboardingStage"]] = relationship(back_populates="onboarding", cascade="all, delete-orphan", order_by="OnboardingStage.number")

    __table_args__ = (Index("ix_onboardings_tenant_status", "tenant_id", "status"),)


class OnboardingStage(Base, UuidPk):
    __tablename__ = "onboarding_stages"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    onboarding_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("onboardings.id", ondelete="CASCADE"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_by: Mapped[str | None] = mapped_column(String(120))
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    onboarding: Mapped[Onboarding] = relationship(back_populates="stages")

    __table_args__ = (Index("ix_onboarding_stages_onb_number", "onboarding_id", "number", unique=True),)
