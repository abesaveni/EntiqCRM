from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """
    Timezone-aware UTC datetimes on every backend. Postgres stores tz; SQLite does not and
    hands back NAIVE values, which then blow up against aware `utcnow()` comparisons and
    change `isoformat()` output (breaking the audit hash chain). This re-attaches UTC on read.
    DDL is identical to DateTime(timezone=True), so migrations are unaffected.
    """
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Subscription and tenant lifecycle. Access: trialing/active/past_due. Read-only: suspended.
# None: cancelled/retained. Records are NEVER deleted on a status change.
LIFECYCLE = ("trialing", "active", "past_due", "suspended", "cancelled", "retained")
ACCESS_STATES = frozenset({"trialing", "active", "past_due"})
READONLY_STATES = frozenset({"suspended"})


class UuidPk:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)
