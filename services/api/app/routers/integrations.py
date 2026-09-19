"""
The Integration Hub (Practice HQ). Reports what is actually configured, from the settings the API is
running with — never from a hard-coded list — plus the per-tenant connections a practice has made.
Credentials are never returned; only whether they exist and what depends on them.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, get_principal
from app.core.security import utcnow
from app.modules import registry

router = APIRouter(tags=["integrations"])

Status = Literal["connected", "simulated", "attention", "not_connected"]


class IntegrationOut(BaseModel):
    key: str
    name: str
    category: str
    status: Status
    detail: str
    used_by: list[str]
    scope: Literal["platform", "practice"]      # platform = configured by EnTIQ; practice = the firm connects it
    configurable_here: bool
    missing: list[str] = []
    connections: int = 0
    last_activity: str | None = None


def _entitled_keys(db: Session, p: Principal) -> set[str]:
    from app.core import entitlements
    return {k for k, v in entitlements.entitlement_map(db, p.tenant).items() if v}


@router.get("/integrations", response_model=list[IntegrationOut])
def integrations(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    from app.modules.verify import providers as verify_providers
    from app.modules.workpapers import ledger as ledger_mod
    from app.modules.workpapers.models import LedgerConnection
    from app.services import payments

    held = _entitled_keys(db, p)
    out: list[IntegrationOut] = []

    def add(key: str, name: str, category: str, status: Status, detail: str, used_by: list[str], scope: str, missing: list[str] | None = None, connections: int = 0, last: Any = None):
        out.append(IntegrationOut(key=key, name=name, category=category, status=status, detail=detail, used_by=[k for k in used_by if k in held or k == "hq"],
                                  scope=scope, configurable_here=scope == "practice", missing=missing or [], connections=connections,
                                  last_activity=last.isoformat() if hasattr(last, "isoformat") else last))

    # --- identity and screening (Verify)
    ident = verify_providers.identity_provider()
    add("didit", "Didit", "Identity verification",
        "connected" if ident.name != "simulation" else "simulated",
        f"{ident.name} · individual and KYB workflows" if ident.name != "simulation" else "No API key configured — identity checks run in simulation and every result is flagged.",
        ["verify", "start", "sign"], "platform",
        [] if ident.name != "simulation" else ["DIDIT_API_KEY", "DIDIT_WORKFLOW_INDIVIDUAL"])
    scr = verify_providers.screening_provider()
    add("opensanctions", "OpenSanctions", "PEP & sanctions",
        "connected" if scr.name != "simulation" else "simulated",
        f"{scr.name} · dataset {settings.OPENSANCTIONS_DATASET} · threshold {settings.OPENSANCTIONS_THRESHOLD}" if scr.name != "simulation" else "No API key configured — screening runs in simulation.",
        ["verify", "start"], "platform", [] if scr.name != "simulation" else ["OPENSANCTIONS_API_KEY"])

    # --- accounting ledger (Workpapers / Advisory), connected per client by the practice
    conns = db.execute(select(LedgerConnection)).scalars().all()
    live_ledger = ledger_mod.live_available()
    add("xero", "Xero", "Accounting ledger",
        "connected" if live_ledger and any(not c.simulated and c.status == "connected" for c in conns) else "simulated" if conns else "not_connected",
        (f"{len(conns)} client ledger(s) connected" if conns else "Connect a client's ledger from Workpapers to sync the trial balance.") + ("" if live_ledger else " Xero credentials are not configured, so syncs use the simulation driver."),
        ["workpapers", "advisory", "practice"], "practice", [] if live_ledger else ["XERO_CLIENT_ID", "XERO_CLIENT_SECRET"],
        len(conns), max((c.last_sync_at for c in conns if c.last_sync_at), default=None))

    # --- payments (EnTIQ's own subscription billing)
    add("stripe", "Stripe", "Subscription payments",
        "connected" if payments.live() else "simulated",
        f"Live · charges the card captured at signup on day {settings.TRIAL_DAYS + 1}" if payments.live()
        else f"BILLING_MODE={settings.BILLING_MODE}" + (" · a key is present but the mode is simulate" if settings.stripe_enabled else " · no secret key") + " — trial conversions are recorded, not charged.",
        ["hq", "billing"], "platform", [] if payments.live() else ([] if settings.stripe_enabled else ["STRIPE_SECRET_KEY"]) + ([] if settings.BILLING_MODE == "stripe" else ["BILLING_MODE=stripe"]))

    # --- email
    add("smtp", "Email (SMTP)", "Communications",
        "connected" if (settings.SMTP_HOST and settings.EMAIL_DELIVERY_ENABLED) else "attention" if settings.SMTP_HOST else "not_connected",
        f"{settings.SMTP_FROM}" + ("" if settings.EMAIL_DELIVERY_ENABLED else " · delivery is off in this environment, so mail is queued to the outbox and not sent"),
        ["crm", "sign", "start", "requests", "client", "billing", "hq"], "platform",
        [] if settings.SMTP_HOST else ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"])

    # --- storage and anti-virus
    add("storage", "File storage", "Infrastructure",
        "connected" if settings.STORAGE_BACKEND == "s3" else "simulated",
        f"{settings.STORAGE_BACKEND} · {settings.AWS_S3_BUCKET or settings.STORAGE_DIR}" + ("" if settings.STORAGE_BACKEND == "s3" else " — local disk; S3 is expected in production"),
        ["documents", "sign", "verify", "requests", "workpapers", "client"], "platform",
        [] if settings.STORAGE_BACKEND == "s3" else ["STORAGE_BACKEND=s3", "AWS_S3_BUCKET"])
    add("clamav", "Anti-virus (ClamAV)", "Infrastructure",
        "connected" if settings.CLAMAV_HOST else "attention",
        f"{settings.CLAMAV_HOST}:{settings.CLAMAV_PORT}" if settings.CLAMAV_HOST else "Not reachable — uploads are accepted and marked unscanned in development; production refuses them.",
        ["documents", "sign", "requests", "client"], "platform", [] if settings.CLAMAV_HOST else ["CLAMAV_HOST"])

    # --- AI (used for drafting and classification where a module asks for it)
    add("openai", "OpenAI", "AI assistance",
        "connected" if settings.OPENAI_API_KEY else "not_connected",
        "Configured" if settings.OPENAI_API_KEY else "Optional. Requests classification and Advisory commentary fall back to deterministic rules without it.",
        ["requests", "advisory", "workpapers"], "platform", [] if settings.OPENAI_API_KEY else ["OPENAI_API_KEY"])

    return out


class IntegrationSummary(BaseModel):
    connected: int
    simulated: int
    attention: int
    not_connected: int
    production_ready: bool
    blocking: list[str]


@router.get("/integrations/summary", response_model=IntegrationSummary)
def summary(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = integrations(p, db)
    counts = {s: sum(1 for r in rows if r.status == s) for s in ("connected", "simulated", "attention", "not_connected")}
    blocking = sorted({m for r in rows if r.key in ("stripe", "smtp", "storage", "clamav", "didit", "opensanctions") for m in r.missing})
    return IntegrationSummary(connected=counts["connected"], simulated=counts["simulated"], attention=counts["attention"], not_connected=counts["not_connected"],
                              production_ready=not blocking, blocking=blocking)
