"""The practice — one tenant per subscribing firm. Everything tenant-scoped points here."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import Timestamps, UuidPk, UTCDateTime


class Tenant(Base, UuidPk, Timestamps):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    abn: Mapped[str | None] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(String(64), default="Australia/Sydney", nullable=False)
    country: Mapped[str] = mapped_column(String(2), default="AU", nullable=False)

    # Lifecycle (see models.common.LIFECYCLE). The base plan's status IS the tenant's status.
    status: Mapped[str] = mapped_column(String(20), default="trialing", nullable=False, index=True)
    status_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status_reason: Mapped[str | None] = mapped_column(String(500))
    trial_ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    current_period_end: Mapped[datetime | None] = mapped_column(UTCDateTime())

    # Payment method on file — card at signup, $0 charged in trial. Only a display token is stored.
    card_on_file: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    card_brand: Mapped[str | None] = mapped_column(String(20))
    card_last4: Mapped[str | None] = mapped_column(String(4))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), index=True)

    __table_args__ = (Index("ix_tenants_status_trial", "status", "trial_ends_at"),)

    def __repr__(self) -> str:
        return f"<Tenant {self.slug} {self.status}>"
