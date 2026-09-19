"""
EnTIQ Workpapers (module 08) — prepare, review and sign off accounting and tax workpapers
with linked evidence. Ported from GrowAccounting's pack/module/item/issue engine, simplified to
three levels (pack → section → item) and re-keyed to the CRM client, the Practice job and the
shared Documents store.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

PACK_STATUSES = ("draft", "in_progress", "in_review", "signed_off", "lodged", "archived")
ITEM_STATUSES = ("not_started", "prepared", "queried", "reviewed", "signed_off", "n_a")
EVIDENCE_STATES = ("missing", "attached", "verified")
ISSUE_SEVERITIES = ("low", "medium", "high")


class Workpaper(Base, UuidPk, Timestamps):
    """One pack for one client, one period, one job type."""
    __tablename__ = "workpaper_packs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("practice_jobs.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    pack_type: Mapped[str] = mapped_column(String(40), default="financial_statements", nullable=False, index=True)  # financial_statements · tax_return · bas · smsf · audit
    period_label: Mapped[str | None] = mapped_column(String(40))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    preparer_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    reviewer_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    prepared_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    signed_off_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    signed_off_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    lodged_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    lodgement_ref: Mapped[str | None] = mapped_column(String(120))
    materiality_cents: Mapped[int | None] = mapped_column(Integer)      # below this, variances are not queried
    # Ledger provenance: which connection/snapshot the figures came from and when
    ledger_source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)   # manual · xero · myob · csv
    ledger_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    ledger_ref: Mapped[str | None] = mapped_column(String(200))
    seal_sha256: Mapped[str | None] = mapped_column(String(64))         # set at sign-off over items + evidence hashes
    notes: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["WorkpaperItem"]] = relationship(back_populates="pack", cascade="all, delete-orphan", order_by="WorkpaperItem.order")
    issues: Mapped[list["WorkpaperIssue"]] = relationship(back_populates="pack", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_workpaper_packs_tenant_status", "tenant_id", "status"),)


class WorkpaperItem(Base, UuidPk, Timestamps):
    """A line of the pack: a balance, a schedule, a reconciliation or a checklist step."""
    __tablename__ = "workpaper_items"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    pack_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workpaper_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    section: Mapped[str] = mapped_column(String(60), nullable=False)       # Assets · Liabilities · Equity · Income · Expenses · Tax · Disclosures · Checklist
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(600))
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    account_code: Mapped[str | None] = mapped_column(String(40))
    value_cents: Mapped[int | None] = mapped_column(Integer)
    prior_cents: Mapped[int | None] = mapped_column(Integer)
    variance_cents: Mapped[int | None] = mapped_column(Integer)
    variance_pct: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="not_started", nullable=False, index=True)
    evidence_state: Mapped[str] = mapped_column(String(10), default="missing", nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="SET NULL"))
    workings: Mapped[str | None] = mapped_column(Text)                    # preparer's note / calculation
    query: Mapped[str | None] = mapped_column(String(600))                # reviewer's question
    prepared_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    prepared_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    reviewed_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    pack: Mapped[Workpaper] = relationship(back_populates="items")

    __table_args__ = (Index("ix_workpaper_items_pack_key", "pack_id", "key", unique=True),)


class WorkpaperIssue(Base, UuidPk, Timestamps):
    """A query or exception raised on the pack. Blocking issues stop sign-off."""
    __tablename__ = "workpaper_issues"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    pack_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workpaper_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("workpaper_items.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)          # variance · missing_evidence · unreconciled · query · compliance
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="open", nullable=False, index=True)   # open · resolved · waived
    raised_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    resolved_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    resolution: Mapped[str | None] = mapped_column(String(600))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    auto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)   # raised by the rules, not a person

    pack: Mapped[Workpaper] = relationship(back_populates="issues")


class LedgerConnection(Base, UuidPk, Timestamps):
    """
    A practice's accounting-ledger connection (Xero, MYOB). Tokens are never returned by the API.
    With no provider credentials configured the connection runs in simulation and every figure it
    produces is marked `simulated`, exactly like the Verify providers.
    """
    __tablename__ = "ledger_connections"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20), default="xero", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)  # pending · connected · error · disconnected
    simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    external_tenant_id: Mapped[str | None] = mapped_column(String(120))     # Xero organisation id
    external_name: Mapped[str | None] = mapped_column(String(200))
    access_token_enc: Mapped[str | None] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    scopes: Mapped[str | None] = mapped_column(String(500))
    last_sync_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(String(500))
    connected_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
