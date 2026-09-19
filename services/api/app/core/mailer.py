"""
Email outbox + SMTP delivery.

queue_email() writes an OutboundMessage inside the caller's transaction. deliver_pending()
sends what is queued — from the lifecycle job, the dev endpoint, or a scheduler. With no
SMTP configured (dev, tests) messages are marked `skipped` so the flow is still visible.
"""
from __future__ import annotations

import logging
import smtplib
import uuid
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import utcnow
from app.core.tenancy import platform_scope
from app.models.platform import OutboundMessage

log = logging.getLogger("entiq.mailer")
MAX_ATTEMPTS = 3


def queue_email(
    db: Session, *, tenant_id: uuid.UUID | None, to: str, subject: str, text: str, html: str | None = None,
    template: str | None = None, ref_type: str | None = None, ref_id: str | None = None,
) -> OutboundMessage:
    msg = OutboundMessage(tenant_id=tenant_id, to_address=to.lower().strip()[:255], subject=subject[:300], body_text=text, body_html=html,
                          template=template, status="queued", attempts=0, ref_type=ref_type, ref_id=str(ref_id) if ref_id else None, created_at=utcnow())
    db.add(msg)
    db.flush()
    return msg


def _send_smtp(msg: OutboundMessage) -> None:
    em = EmailMessage()
    em["From"] = settings.SMTP_FROM
    em["To"] = msg.to_address
    em["Subject"] = msg.subject
    em.set_content(msg.body_text)
    if msg.body_html:
        em.add_alternative(msg.body_html, subtype="html")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as s:
        if settings.SMTP_USE_TLS:
            s.starttls()
        if settings.SMTP_USERNAME:
            s.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        s.send_message(em)


def deliver_pending(db: Session, limit: int = 100) -> dict[str, int]:
    """Deliver queued messages. Returns counts. Safe to call repeatedly."""
    counts = {"sent": 0, "failed": 0, "skipped": 0, "retry": 0}
    with platform_scope():
        rows = db.execute(select(OutboundMessage).where(OutboundMessage.status == "queued").order_by(OutboundMessage.created_at).limit(limit)).scalars().all()
        for m in rows:
            m.attempts += 1
            if not settings.email_delivery_active:
                m.status, m.last_error = "skipped", "smtp_not_configured" if not settings.smtp_enabled else "delivery_disabled_outside_production"
                counts["skipped"] += 1
                log.info("email skipped (no SMTP) → %s · %s", m.to_address, m.subject)
                continue
            try:
                _send_smtp(m)
                m.status, m.sent_at, m.last_error = "sent", utcnow(), None
                counts["sent"] += 1
            except Exception as e:  # noqa: BLE001 — any transport failure is retryable up to MAX_ATTEMPTS
                m.last_error = f"{type(e).__name__}: {e}"[:500]
                if m.attempts >= MAX_ATTEMPTS:
                    m.status = "failed"
                    counts["failed"] += 1
                else:
                    counts["retry"] += 1
        db.flush()
    return counts
