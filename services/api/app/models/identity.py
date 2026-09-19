"""
Identity: a person is ONE user (global email) who may hold MANY memberships, one per practice.

This is the deliberate fix for the estate's worst identity defect — GrowKyc's globally-unique
`users.email` bound each person to exactly one tenant. Here the user is global and the
membership carries the tenant, role and module grants.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Timestamps, UuidPk, UTCDateTime

ROLES = ("owner", "admin", "staff")
MEMBERSHIP_STATUSES = ("active", "invited", "disabled")


class User(Base, UuidPk, Timestamps):
    __tablename__ = "users"  # GLOBAL — not tenant-scoped

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_operator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # EnTIQ staff → Control Centre
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Tokens issued before this instant are refused — password change / admin disable ends live sessions.
    tokens_valid_from: Mapped[datetime | None] = mapped_column(UTCDateTime())

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Membership(Base, UuidPk, Timestamps):
    __tablename__ = "memberships"  # carries tenant_id but is EXEMPT from the read filter (login needs it)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default="staff", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(120))
    joined_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    user: Mapped[User] = relationship(back_populates="memberships")
    grants: Mapped[list["ModuleGrant"]] = relationship(back_populates="membership", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_membership_user_tenant"),)


class ModuleGrant(Base, UuidPk):
    """One tick in the Practice HQ access matrix: this member may open this module."""
    __tablename__ = "module_grants"

    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    module_key: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    granted_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    membership: Mapped[Membership] = relationship(back_populates="grants")

    __table_args__ = (UniqueConstraint("membership_id", "module_key", name="uq_grant_membership_module"),)


class Invitation(Base, UuidPk, Timestamps):
    __tablename__ = "invitations"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default="staff", nullable=False)
    module_keys: Mapped[str] = mapped_column(String(500), default="", nullable=False)  # comma-separated
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class RefreshToken(Base, UuidPk):
    __tablename__ = "refresh_tokens"  # EXEMPT — validated before tenant context exists

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(300))


class RevokedToken(Base):
    """Access-token denylist by jti, purgeable once expires_at passes."""
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(32), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)


Index("ix_invitations_tenant_email", Invitation.tenant_id, Invitation.email)
