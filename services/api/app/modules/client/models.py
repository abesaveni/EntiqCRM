"""
EnTIQ Client portal (module 14) — one phone-first surface for every service a client uses.
Ported from ClientPortal / GrowAccounting portal / entiq-app. The portal user IS a CRM Contact
(has_portal_access); login is a passwordless magic link, the session a short-lived portal JWT.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk


class PortalLoginToken(Base, UuidPk):
    """One-time magic-link token for a contact. Exempt from tenant scoping: it is looked up before any tenant is known."""
    __tablename__ = "portal_login_tokens"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(10), default="login", nullable=False)   # login · invite
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class PortalMessage(Base, UuidPk, Timestamps):
    """Client ↔ practice thread on the client record. contact_id set = from the client; membership_id set = from staff."""
    __tablename__ = "portal_messages"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id", ondelete="SET NULL"))
    membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    read_by_practice_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    read_by_client_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (Index("ix_portal_messages_client_created", "client_id", "created_at"),)


class PortalSession(Base, UuidPk):
    """Issued portal sessions, so a practice can revoke access instantly (revoking the contact invalidates its sessions)."""
    __tablename__ = "portal_sessions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
