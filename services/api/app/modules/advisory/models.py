"""
EnTIQ Advisory (module 10) — turn the numbers into decisions: a periodic snapshot of the client's
position, alerts and recommendations that become owned actions, and the meeting that ties them
together. Ported from ClientPortal (alerts → recommendations → actions, KPI snapshots, meetings) and
GrowAccounting (meetings + agenda), reading its figures from the Workpapers ledger rather than a
second integration.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

ACTION_STATUSES = ("open", "in_progress", "done", "cancelled")
MEETING_STATUSES = ("scheduled", "prepared", "held", "published", "cancelled")
ALERT_SEVERITIES = ("info", "watch", "action")


class Snapshot(Base, UuidPk, Timestamps):
    """The client's position at a point in time, with the KPIs the meeting is run from."""
    __tablename__ = "advisory_snapshots"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    as_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_label: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(20), default="workpapers", nullable=False)   # workpapers · ledger · manual
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    workpaper_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("workpaper_packs.id", ondelete="SET NULL"))
    # headline figures, in cents
    revenue_cents: Mapped[int | None] = mapped_column(Integer)
    gross_profit_cents: Mapped[int | None] = mapped_column(Integer)
    expenses_cents: Mapped[int | None] = mapped_column(Integer)
    net_profit_cents: Mapped[int | None] = mapped_column(Integer)
    cash_cents: Mapped[int | None] = mapped_column(Integer)
    receivables_cents: Mapped[int | None] = mapped_column(Integer)
    payables_cents: Mapped[int | None] = mapped_column(Integer)
    inventory_cents: Mapped[int | None] = mapped_column(Integer)
    debt_cents: Mapped[int | None] = mapped_column(Integer)
    equity_cents: Mapped[int | None] = mapped_column(Integer)
    tax_provision_cents: Mapped[int | None] = mapped_column(Integer)
    # derived ratios
    kpis: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    health_score: Mapped[int | None] = mapped_column(Integer)      # 0–100
    health_band: Mapped[str | None] = mapped_column(String(20))    # good · watch · needs_action
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))

    __table_args__ = (Index("ix_advisory_snapshots_client_asat", "client_id", "as_at"),)


class Alert(Base, UuidPk, Timestamps):
    """Something the numbers say. Raised by the rules from a snapshot, or by an adviser."""
    __tablename__ = "advisory_alerts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("advisory_snapshots.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10), default="watch", nullable=False, index=True)
    metric: Mapped[str | None] = mapped_column(String(40))
    value: Mapped[float | None] = mapped_column(Float)
    benchmark: Mapped[float | None] = mapped_column(Float)
    recommendation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="open", nullable=False, index=True)   # open · actioned · dismissed
    auto: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    dismissed_reason: Mapped[str | None] = mapped_column(String(300))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Action(Base, UuidPk, Timestamps):
    """An owned commitment coming out of advice. Visible to the client in the portal unless marked internal."""
    __tablename__ = "advisory_actions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("advisory_meetings.id", ondelete="SET NULL"), index=True)
    alert_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("advisory_alerts.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    owner_side: Mapped[str] = mapped_column(String(10), default="practice", nullable=False)   # practice · client
    owner_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    owner_label: Mapped[str | None] = mapped_column(String(200))
    due_on: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(12), default="open", nullable=False, index=True)
    visible_to_client: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tasks.id", ondelete="SET NULL"))   # mirrored into CRM tasks when owned by the practice


class Meeting(Base, UuidPk, Timestamps):
    __tablename__ = "advisory_meetings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("advisory_snapshots.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="quarterly", nullable=False)   # quarterly · monthly · annual · adhoc
    scheduled_for: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(12), default="scheduled", nullable=False, index=True)
    agenda: Mapped[list] = mapped_column(JSON, default=list, nullable=False)     # [{title, note, source, decision}]
    summary: Mapped[str | None] = mapped_column(Text)
    prepared_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    held_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="SET NULL"))   # the pack PDF shared with the client

    actions: Mapped[list[Action]] = relationship(primaryjoin="Meeting.id == foreign(Action.meeting_id)", viewonly=True)
