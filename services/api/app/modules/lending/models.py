"""
EnTIQ Lending (module 20) — finance enquiries and applications through approval, conditions,
settlement and handover. Ported from RequestIQ's lending intake (readiness, exceptions-only review,
conditions), re-keyed to the CRM client and using the Requests module for document collection rather
than a second uploader.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

# The pipeline, in order. `declined` and `withdrawn` are terminal off-ramps.
STAGES = ["enquiry", "information", "assessment", "submitted", "approved", "conditions", "settled"]
TERMINAL = ("settled", "declined", "withdrawn")
PURPOSES = ("equipment", "vehicle", "property", "working_capital", "refinance", "expansion", "other")


class Application(Base, UuidPk, Timestamps):
    __tablename__ = "lending_applications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id", ondelete="SET NULL"))
    reference: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(20), default="equipment", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    term_months: Mapped[int | None] = mapped_column(Integer)
    rate_bps: Mapped[int | None] = mapped_column(Integer)           # indicative or approved rate
    repayment_cents: Mapped[int | None] = mapped_column(Integer)
    lender: Mapped[str | None] = mapped_column(String(120))
    stage: Mapped[str] = mapped_column(String(16), default="enquiry", nullable=False, index=True)
    owner_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"), index=True)
    request_pack_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("request_packs.id", ondelete="SET NULL"), index=True)
    # assessment
    serviceability: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)   # {ebitda_cents, existing_repayments_cents, dscr, notes}
    readiness_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    decision_note: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    settled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    settlement_date: Mapped[date | None] = mapped_column(Date)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    close_reason: Mapped[str | None] = mapped_column(String(300))
    expected_settlement: Mapped[date | None] = mapped_column(Date, index=True)

    conditions: Mapped[list["Condition"]] = relationship(back_populates="application", cascade="all, delete-orphan", order_by="Condition.created_at")
    events: Mapped[list["ApplicationEvent"]] = relationship(back_populates="application", cascade="all, delete-orphan", order_by="ApplicationEvent.at")

    __table_args__ = (Index("ix_lending_applications_tenant_stage", "tenant_id", "stage"),)


class Condition(Base, UuidPk, Timestamps):
    """A lender condition precedent or subsequent. Settlement is blocked while a precedent is open."""
    __tablename__ = "lending_conditions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lending_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(12), default="precedent", nullable=False)   # precedent · subsequent
    owner_side: Mapped[str] = mapped_column(String(10), default="client", nullable=False)  # client · practice · lender
    due_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="open", nullable=False, index=True)   # open · satisfied · waived
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="SET NULL"))
    satisfied_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    satisfied_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(String(600))

    application: Mapped[Application] = relationship(back_populates="conditions")


class ApplicationEvent(Base, UuidPk):
    """Stage history — who moved it, when, and why."""
    __tablename__ = "lending_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lending_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    from_stage: Mapped[str | None] = mapped_column(String(16))
    to_stage: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    actor_label: Mapped[str] = mapped_column(String(120), nullable=False)
    at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    application: Mapped[Application] = relationship(back_populates="events")
