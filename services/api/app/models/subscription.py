"""
tenant_subscriptions — entitlement is DATA, not deployment.

Every module ships in every build; a row here decides whether a tenant can reach it.
The base bundle (Practice HQ + CRM) is provisioned as rows like any other module so
there is no special-case code path. A trial is the same row with status=trialing.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import Timestamps, UuidPk, UTCDateTime


class TenantSubscription(Base, UuidPk, Timestamps):
    __tablename__ = "tenant_subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    module_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    seats: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    trial_ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    current_period_end: Mapped[datetime | None] = mapped_column(UTCDateTime())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Set when the row was provisioned as a hard dependency of another module.
    required_by: Mapped[str | None] = mapped_column(String(32))

    stripe_subscription_item_id: Mapped[str | None] = mapped_column(String(64))
    stripe_price_id: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (UniqueConstraint("tenant_id", "module_key", name="uq_subscription_tenant_module"),)
