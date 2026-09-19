"""
EnTIQ Support — the "one supporting system" (ported from SupportHub/EntiqSupportingSystem).
Tenants raise tickets from Practice HQ; EnTIQ operators work them from the Control Centre with SLA
tracking. Tickets are tenant-scoped rows (a practice sees only its own); operators read across
tenants through platform_scope.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

TICKET_STATUSES = ("open", "pending", "resolved", "closed")       # pending = waiting on the customer
PRIORITIES = ("low", "medium", "high", "urgent")
CATEGORIES = ("question", "problem", "billing", "feature", "onboarding", "security")
# SLA policy (minutes): first response · resolution — mirrors SupportHub's SLAPolicy per priority
SLA = {"urgent": (30, 4 * 60), "high": (2 * 60, 24 * 60), "medium": (8 * 60, 3 * 24 * 60), "low": (24 * 60, 7 * 24 * 60)}


class SupportTicket(Base, UuidPk, Timestamps):
    __tablename__ = "support_tickets"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(20), default="question", nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="medium", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(10), default="open", nullable=False, index=True)
    module_key: Mapped[str | None] = mapped_column(String(32))
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    assigned_operator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    first_response_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    resolution_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    first_response_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    sla_breached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    satisfaction: Mapped[int | None] = mapped_column(Integer)      # 1–5, optional on close

    comments: Mapped[list["SupportComment"]] = relationship(back_populates="ticket", cascade="all, delete-orphan", order_by="SupportComment.created_at")

    __table_args__ = (Index("ix_support_tickets_status_priority", "status", "priority"),)


class SupportComment(Base, UuidPk):
    __tablename__ = "support_comments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_operator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)     # operator-only note
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    ticket: Mapped[SupportTicket] = relationship(back_populates="comments")
