"""
CRM core — the client record every module contributes to. Blueprint MODULE 16 data ownership:
party, organisation, relationship, lead, opportunity, stage, activity, referral, source,
consent, segment, owner.

`Client` is the aggregate root (one client = one legal party: company, trust, individual,
partnership or SMSF). Contacts are the people attached to it. Relationships form the party
graph (director_of, trustee_of, …). TimelineEvent is the shared activity feed: the CRM writes
to it, and so does every other module through core.events.emit(). Nothing here is ever hard
deleted — clients archive, tasks cancel.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

CLIENT_TYPES = ("Company", "Trust", "Individual", "Partnership", "SMSF", "Other")
STAGES = ("Lead", "Proposal", "Onboarding", "Active", "Review", "Dormant", "Lost")
RISK_LEVELS = ("Low", "Medium", "High")
TASK_STATUSES = ("open", "done", "cancelled")
TASK_PRIORITIES = ("Low", "Normal", "High")
RELATIONSHIP_KINDS = (
    "director_of", "secretary_of", "shareholder_of", "trustee_of", "beneficiary_of", "appointor_of",
    "partner_of", "member_of", "owner_of", "bookkeeper_for", "adviser_to", "referrer_of", "related_entity", "spouse_of",
)


class Client(Base, UuidPk, Timestamps):
    __tablename__ = "clients"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    name_normalised: Mapped[str] = mapped_column(String(300), nullable=False, index=True)  # for search + duplicate detection
    legal_name: Mapped[str | None] = mapped_column(String(300))
    client_type: Mapped[str] = mapped_column(String(20), default="Company", nullable=False)
    abn: Mapped[str | None] = mapped_column(String(11), index=True)   # digits only
    acn: Mapped[str | None] = mapped_column(String(9))                # digits only
    stage: Mapped[str] = mapped_column(String(20), default="Lead", nullable=False, index=True)
    owner_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"), index=True)
    # Written by Verify; the CRM only displays it.
    risk_rating: Mapped[str | None] = mapped_column(String(10))
    risk_assessed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    since: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(255))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    suburb: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(10))
    postcode: Mapped[str | None] = mapped_column(String(10))
    country: Mapped[str] = mapped_column(String(2), default="AU", nullable=False)

    source: Mapped[str | None] = mapped_column(String(40))        # inbound | referral | import:xero | import:myob | import:csv | start
    external_ref: Mapped[str | None] = mapped_column(String(120))  # e.g. Xero ContactID / MYOB Card ID
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    custom: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    contacts: Mapped[list["Contact"]] = relationship(back_populates="client", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_clients_tenant_stage", "tenant_id", "stage"),
        Index("ix_clients_tenant_name", "tenant_id", "name_normalised"),
        Index("ix_clients_tenant_abn", "tenant_id", "abn"),
        Index("ix_clients_tenant_ext", "tenant_id", "external_ref"),
    )


class Contact(Base, UuidPk, Timestamps):
    __tablename__ = "contacts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    role: Mapped[str | None] = mapped_column(String(80))           # Director · Trustee · Owner · Bookkeeper · …
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    # Set when this person is invited to the client portal (module 14).
    portal_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    portal_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)   # Client portal (module 14) invitation accepted/active
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    client: Mapped[Client] = relationship(back_populates="contacts")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name or ''}".strip()


class Relationship(Base, UuidPk, Timestamps):
    """Party graph edge. from → to, e.g. contact(Margaret) trustee_of client(Ashfield Trust)."""
    __tablename__ = "relationships"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    from_type: Mapped[str] = mapped_column(String(10), nullable=False)   # client | contact
    from_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    to_type: Mapped[str] = mapped_column(String(10), nullable=False)
    to_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    percentage: Mapped[int | None] = mapped_column(Integer)              # ownership %, where relevant
    notes: Mapped[str | None] = mapped_column(String(300))
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class TimelineEvent(Base, UuidPk):
    """The shared activity feed. Every module writes here through core.events.emit()."""
    __tablename__ = "timeline_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    module_key: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)       # client.created · stage.changed · task.completed · agreement.signed …
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    actor_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(120), nullable=False, default="System")
    ref_type: Mapped[str | None] = mapped_column(String(40))
    ref_id: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)

    __table_args__ = (Index("ix_timeline_tenant_client_time", "tenant_id", "client_id", "occurred_at"),)


class Task(Base, UuidPk, Timestamps):
    __tablename__ = "tasks"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    priority: Mapped[str] = mapped_column(String(10), default="Normal", nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="open", nullable=False, index=True)
    assignee_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"), index=True)
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    module_key: Mapped[str] = mapped_column(String(32), default="crm", nullable=False)  # which module raised it
    ref_type: Mapped[str | None] = mapped_column(String(40))
    ref_id: Mapped[str | None] = mapped_column(String(64))


class Note(Base, UuidPk, Timestamps):
    __tablename__ = "notes"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Segment(Base, UuidPk, Timestamps):
    """A saved client filter. Members are computed on read so the list is never stale."""
    __tablename__ = "segments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    filters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)   # {stage, client_type, tag, owner, risk, q}
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))


class ImportJob(Base, UuidPk, Timestamps):
    """A client-list import (Xero / MYOB / generic CSV): parsed once, previewed, then committed."""
    __tablename__ = "import_jobs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)          # xero | myob | csv
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="preview", nullable=False)  # preview | committed | failed
    columns: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    mapping: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # {field: column}
    rows: Mapped[list] = mapped_column(JSON, default=list, nullable=False)     # parsed rows (capped)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    committed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
