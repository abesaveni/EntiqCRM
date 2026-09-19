from __future__ import annotations

import copy
import re
import statistics
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import events, mailer
from app.core.config import settings
from app.core.database import bind_tenant
from app.core.security import hash_token, new_opaque_token, utcnow
from app.core.tenancy import platform_scope, set_tenant
from app.models.crm import Client, Contact
from app.models.platform import Document
from app.models.tenant import Tenant
from app.modules.requests import schemas as S
from app.modules.requests.models import RequestItem, RequestPack
from app.notify import templates
from app.services import billing_service, notify_service
from app.services.crm_service import client_name_map, member_names


class RequestError(Exception):
    def __init__(self, error: str, message: str | None = None):
        super().__init__(message or error)
        self.error, self.message = error, message or error


# ------------------------------------------------------------------ templates (the "adaptive checklist")
# key, label, category, required, entity types ([] = all)
_T = {
    "tax_return": {
        "label": "Tax return",
        "items": [
            ("bank_statements", "Bank statements for the year", "bank", True, []),
            ("income_summary", "Income statements / PAYG summaries", "payroll", True, ["Individual"]),
            ("prior_financials", "Prior year financial statements", "financial", True, ["Company", "Trust", "Partnership", "SMSF"]),
            ("ato_ica", "ATO integrated client account statement", "tax", False, ["Company", "Trust", "Partnership"]),
            ("asset_purchases", "Invoices for asset purchases over $1,000", "financial", False, []),
            ("loan_statements", "Loan and hire-purchase statements", "bank", False, []),
            ("dividend_statements", "Dividend and managed fund statements", "financial", False, []),
            ("private_health", "Private health insurance statement", "other", False, ["Individual"]),
            ("work_deductions", "Work-related expense receipts", "other", False, ["Individual"]),
            ("trust_distribution", "Trust distribution minute", "legal", True, ["Trust"]),
            ("rental_statements", "Rental property agent statements", "property", True, []),   # added by question
            ("rental_expenses", "Rental property expenses (rates, insurance, repairs)", "property", False, []),
            ("crypto_records", "Cryptocurrency transaction history", "financial", True, []),
            ("motor_vehicle_log", "Motor vehicle logbook", "other", True, []),
        ],
        "questions": [
            {"key": "rental", "label": "Did you own a rental property during the year?", "adds": ["rental_statements", "rental_expenses"]},
            {"key": "crypto", "label": "Did you buy, sell or hold cryptocurrency?", "adds": ["crypto_records"]},
            {"key": "vehicle", "label": "Do you claim a motor vehicle for work?", "adds": ["motor_vehicle_log"]},
        ],
        "conditional": {"rental_statements", "rental_expenses", "crypto_records", "motor_vehicle_log"},
    },
    "bas": {
        "label": "Activity statement",
        "items": [("bank_statements", "Bank statements for the quarter", "bank", True, []), ("sales_summary", "Sales / invoicing summary", "financial", True, []), ("purchase_invoices", "Purchase invoices over $1,000", "financial", False, []), ("payroll_summary", "Payroll summary (wages & PAYGW)", "payroll", True, [])],
        "questions": [], "conditional": set(),
    },
    "financials": {
        "label": "Financial statements",
        "items": [("bank_statements", "Year-end bank statements", "bank", True, []), ("debtors_creditors", "Debtors and creditors listings", "financial", True, []), ("stock_count", "Stock on hand at year end", "financial", False, []), ("loan_statements", "Loan statements", "bank", False, []), ("asset_purchases", "Asset purchase and disposal invoices", "financial", False, [])],
        "questions": [], "conditional": set(),
    },
    "lending": {
        "label": "Finance application",
        "items": [("id_document", "Photo ID (driver licence or passport)", "identity", True, []), ("bank_statements", "6 months bank statements", "bank", True, []), ("prior_financials", "Last 2 years financial statements", "financial", True, ["Company", "Trust", "Partnership"]), ("prior_tax_return", "Last 2 years tax returns", "tax", True, []), ("ato_ica", "ATO integrated client account", "tax", True, ["Company", "Trust", "Partnership"]), ("payslips", "Recent payslips", "payroll", True, ["Individual"]), ("asset_liability", "Statement of assets and liabilities", "financial", True, []), ("contract_of_sale", "Contract of sale / quote for the asset", "legal", True, [])],
        "questions": [], "conditional": set(),
    },
    "onboarding": {
        "label": "New client onboarding",
        "items": [("prior_financials", "Last financial statements", "financial", True, []), ("prior_tax_return", "Last tax return", "tax", True, []), ("asic_extract", "ASIC company extract", "legal", True, ["Company"]), ("trust_deed", "Trust deed", "legal", True, ["Trust", "SMSF"])],
        "questions": [], "conditional": set(),
    },
    "audit": {
        "label": "Audit evidence",
        "items": [("bank_confirmations", "Bank confirmations", "bank", True, []), ("board_minutes", "Board minutes for the year", "legal", True, []), ("fixed_asset_register", "Fixed asset register", "financial", True, []), ("related_party", "Related party transactions schedule", "financial", False, [])],
        "questions": [], "conditional": set(),
    },
    "custom": {"label": "Custom request", "items": [], "questions": [], "conditional": set()},
}


def templates_out() -> list[S.TemplateOut]:
    return [S.TemplateOut(purpose=k, label=v["label"], items=[{"key": i[0], "label": i[1], "category": i[2], "required": i[3], "entity_types": i[4], "conditional": i[0] in v["conditional"]} for i in v["items"]], questions=v["questions"]) for k, v in _T.items()]


def template_items(purpose: str, entity_type: str) -> tuple[list[dict], list[dict]]:
    t = _T.get(purpose, _T["custom"])
    items = [{"key": k, "label": l, "category": c, "required": r} for k, l, c, r, et in t["items"] if (not et or entity_type in et) and k not in t["conditional"]]
    return items, [dict(q, answer=None) for q in t["questions"]]


# ------------------------------------------------------------------ classification (deterministic heuristics, as RequestIQ shipped)
_PATTERNS: list[tuple[str, str]] = [
    (r"bank|statement|bsb|transaction", "bank"), (r"payg|payslip|payroll|wage|stp|income statement", "payroll"), (r"ato|notice of assessment|activity statement|bas|ias|tax return|itr", "tax"),
    (r"licen[cs]e|passport|medicare|photo id|identity", "identity"), (r"deed|minute|resolution|agreement|contract|asic|extract", "legal"), (r"rental|rates|strata|property|lease", "property"),
    (r"financial|balance sheet|profit|p&l|trial balance|ledger|invoice|receipt|dividend|fund", "financial"),
]


def classify(filename: str, content_type: str | None, item: RequestItem) -> dict[str, Any]:
    name = (filename or "").lower()
    detected, conf = "other", 0.2
    for pat, cat in _PATTERNS:
        if re.search(pat, name):
            detected, conf = cat, 0.7
            break
    flags: list[str] = []
    if content_type and content_type not in ("application/pdf", "image/jpeg", "image/png", "image/heic", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "text/csv", "application/vnd.ms-excel", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
        flags.append("unusual_file_type")
    matches = detected == item.category or detected == "other" or item.category == "other"
    if not matches:
        flags.append(f"looks_like_{detected}")
    if re.search(r"\b(19|20)\d{2}\b", name) and item.pack.period_label and not any(y in name for y in re.findall(r"\d{2,4}", item.pack.period_label or "")):
        flags.append("period_mismatch")
    return {"detected": detected, "confidence": conf, "matches_item": matches, "flags": flags, "method": "heuristic-v1"}


# ------------------------------------------------------------------ serialisers
def item_out(i: RequestItem, docs: dict, names: dict) -> S.ItemOut:
    return S.ItemOut(id=i.id, key=i.key, label=i.label, description=i.description, category=i.category, required=i.required, order=i.order, status=i.status, document_id=i.document_id,
                     document_filename=docs.get(i.document_id) if i.document_id else None, client_note=i.client_note, rejection_reason=i.rejection_reason, classification=i.classification or {},
                     uploaded_at=i.uploaded_at, reviewed_by_name=names.get(i.reviewed_by_membership_id) if i.reviewed_by_membership_id else None, reviewed_at=i.reviewed_at)


def _counts(p: RequestPack) -> dict[str, int]:
    it = p.items
    return {"items_total": len(it), "items_required": sum(1 for i in it if i.required), "items_done": sum(1 for i in it if i.status in ("accepted", "not_applicable")), "items_uploaded": sum(1 for i in it if i.status == "uploaded"),
            "items_rejected": sum(1 for i in it if i.status == "rejected"), "exceptions": sum(1 for i in it if i.status == "uploaded" and (i.classification or {}).get("flags"))}


def pack_out(db: Session, p: RequestPack, names: dict | None = None, clients: dict | None = None) -> S.PackOut:
    names = names if names is not None else member_names(db, {p.created_by_membership_id})
    clients = clients if clients is not None else client_name_map(db, {p.client_id})
    ct = db.get(Contact, p.contact_id) if p.contact_id else None
    return S.PackOut(id=p.id, client_id=p.client_id, client_name=clients.get(p.client_id), contact_id=p.contact_id, contact_name=ct.full_name if ct else None, contact_email=ct.email if ct else None, title=p.title, purpose=p.purpose,
                     period_label=p.period_label, message=p.message, status=p.status, due_on=p.due_on, overdue=bool(p.due_on and p.due_on < date.today() and p.status in ("sent", "in_progress")), **_counts(p),
                     created_by_name=names.get(p.created_by_membership_id) if p.created_by_membership_id else None, sent_at=p.sent_at, submitted_at=p.submitted_at, completed_at=p.completed_at, reminder_count=p.reminder_count,
                     last_reminded_at=p.last_reminded_at, token_expires_at=p.token_expires_at, created_at=p.created_at, updated_at=p.updated_at)


def _docs(db: Session, p: RequestPack) -> dict:
    ids = [i.document_id for i in p.items if i.document_id]
    return {d.id: d.filename for d in db.execute(select(Document).where(Document.id.in_(ids))).scalars()} if ids else {}


def pack_detail(db: Session, p: RequestPack, url: str | None = None) -> S.PackDetail:
    base = pack_out(db, p)
    names = member_names(db, {i.reviewed_by_membership_id for i in p.items})
    docs = _docs(db, p)
    return S.PackDetail(**base.model_dump(), items=[item_out(i, docs, names) for i in p.items], questions=[S.QuestionOut(**q) for q in (p.questions or [])], request_url=url)


# ------------------------------------------------------------------ lifecycle
def create(db: Session, tenant: Tenant, body: S.PackIn, actor_mid: uuid.UUID, actor_label: str) -> tuple[RequestPack, str | None]:
    c = db.get(Client, body.client_id)
    if c is None:
        raise RequestError("client_not_found")
    ct = db.get(Contact, body.contact_id) if body.contact_id else db.execute(select(Contact).where(Contact.client_id == c.id, Contact.archived_at.is_(None)).order_by(Contact.is_primary.desc(), Contact.created_at)).scalars().first()
    items, questions = template_items(body.purpose, c.client_type) if body.use_template else ([], [])
    seen = {i["key"] for i in items}
    for extra in body.items:
        key = (extra.key or re.sub(r"[^a-z0-9]+", "_", extra.label.lower()).strip("_"))[:60]
        n = 2
        while key in seen:
            key = f"{key}_{n}"; n += 1
        seen.add(key)
        items.append({"key": key, "label": extra.label, "description": extra.description, "category": extra.category, "required": extra.required})
    if not items:
        raise RequestError("no_items", "A request needs at least one item")
    title = body.title or f"{_T.get(body.purpose, _T['custom'])['label']}{' · ' + body.period_label if body.period_label else ''} — {c.name}"
    p = RequestPack(tenant_id=tenant.id, client_id=c.id, contact_id=ct.id if ct else None, title=title[:300], purpose=body.purpose, period_label=body.period_label, message=body.message, status="draft",
                    due_on=date.today() + timedelta(days=body.due_in_days), questions=questions, created_by_membership_id=actor_mid)
    db.add(p)
    db.flush()
    for n, it in enumerate(items, 1):
        db.add(RequestItem(tenant_id=tenant.id, pack_id=p.id, key=it["key"], label=it["label"], description=it.get("description"), category=it["category"], required=it["required"], order=n))
    db.flush()
    db.refresh(p)
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="requests", kind="request.created", summary=f"Request drafted: {p.title} ({len(items)} items)", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="request_pack", ref_id=p.id)
    url = send(db, tenant, p, actor_mid, actor_label) if body.send_now else None
    return p, url


def _url(raw: str) -> str:
    return f"{settings.APP_PUBLIC_URL.rstrip('/')}/r/{raw}"


def send(db: Session, tenant: Tenant, p: RequestPack, actor_mid: uuid.UUID | None, actor_label: str, *, reminder: bool = False) -> str:
    if p.status in ("complete", "cancelled"):
        raise RequestError("closed", f"Request is {p.status}")
    ct = db.get(Contact, p.contact_id) if p.contact_id else None
    if ct is None or not ct.email:
        raise RequestError("no_contact_email", "The client needs a contact with an email address")
    raw, h = new_opaque_token()
    p.token_hash, p.token_expires_at = h, utcnow() + timedelta(days=max(30, ((p.due_on - date.today()).days if p.due_on else 30) + 30))
    url = _url(raw)
    outstanding = [i.label for i in p.items if i.status in ("pending", "rejected")]
    subject, text, html = templates.request_sent(name=ct.first_name, practice=tenant.name, title=p.title, message=p.message, url=url, due=p.due_on.strftime("%d %b %Y") if p.due_on else None, items=outstanding, reminder=reminder)
    mailer.queue_email(db, tenant_id=tenant.id, to=ct.email, subject=subject, text=text, html=html, template="request_reminder" if reminder else "request_sent", ref_type="request_pack", ref_id=p.id)
    if reminder:
        p.reminder_count += 1
        p.last_reminded_at = utcnow()
        events.emit(db, tenant_id=tenant.id, client_id=p.client_id, module_key="requests", kind="request.reminded", summary=f"Reminder sent for {p.title} ({len(outstanding)} outstanding)", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="request_pack", ref_id=p.id)
    else:
        p.sent_at = p.sent_at or utcnow()
        if p.status == "draft":
            p.status = "sent"
        events.emit(db, tenant_id=tenant.id, client_id=p.client_id, module_key="requests", kind="request.sent", summary=f"Request sent to {ct.full_name}: {p.title}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="request_pack", ref_id=p.id)
    db.flush()
    return url


def add_items(db: Session, tenant: Tenant, p: RequestPack, body: S.AddItemsIn, actor_mid: uuid.UUID, actor_label: str) -> None:
    if p.status in ("complete", "cancelled"):
        raise RequestError("closed")
    seen = {i.key for i in p.items}
    order = max((i.order for i in p.items), default=0)
    for extra in body.items:
        key = (extra.key or re.sub(r"[^a-z0-9]+", "_", extra.label.lower()).strip("_"))[:60]
        n = 2
        while key in seen:
            key = f"{key}_{n}"; n += 1
        seen.add(key); order += 1
        db.add(RequestItem(tenant_id=tenant.id, pack_id=p.id, key=key, label=extra.label, description=extra.description, category=extra.category, required=extra.required, order=order))
    if p.status in ("submitted", "reviewing", "complete"):
        p.status = "in_progress"
    db.flush()
    db.refresh(p)
    events.emit(db, tenant_id=tenant.id, client_id=p.client_id, module_key="requests", kind="request.items_added", summary=f"{len(body.items)} item(s) added to {p.title}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="request_pack", ref_id=p.id)
    if body.notify and p.token_hash:
        send(db, tenant, p, actor_mid, actor_label, reminder=True)


def cancel(db: Session, p: RequestPack, actor_mid: uuid.UUID, actor_label: str) -> None:
    if p.status == "complete":
        raise RequestError("closed")
    p.status, p.token_hash = "cancelled", None
    events.emit(db, tenant_id=p.tenant_id, client_id=p.client_id, module_key="requests", kind="request.cancelled", summary=f"Request cancelled: {p.title}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="request_pack", ref_id=p.id)


# ------------------------------------------------------------------ client side (token or portal)
class TokenError(Exception):
    pass


def load_by_token(db: Session, raw: str) -> tuple[RequestPack, Tenant]:
    with platform_scope():
        p = db.execute(select(RequestPack).where(RequestPack.token_hash == hash_token(raw))).scalar_one_or_none()
        if p is None:
            raise TokenError("invalid_link")
        t = db.get(Tenant, p.tenant_id)
    bind_tenant(db, p.tenant_id)
    set_tenant(p.tenant_id)
    if p.status == "cancelled":
        raise TokenError("cancelled")
    if p.token_expires_at and p.token_expires_at < utcnow():
        raise TokenError("expired")
    return p, t


def outstanding(p: RequestPack) -> list[str]:
    return [i.label for i in p.items if i.required and i.status in ("pending", "rejected")] + [q["label"] for q in (p.questions or []) if q.get("answer") is None]


def public_pack(db: Session, p: RequestPack, t: Tenant) -> S.PublicPack:
    c = db.get(Client, p.client_id)
    ct = db.get(Contact, p.contact_id) if p.contact_id else None
    docs = _docs(db, p)
    out = outstanding(p)
    return S.PublicPack(practice_name=t.name, client_name=c.name, contact_name=ct.full_name if ct else None, title=p.title, purpose=p.purpose, message=p.message, status=p.status, due_on=p.due_on,
                        items=[item_out(i, docs, {}) for i in p.items], questions=[S.QuestionOut(**q) for q in (p.questions or [])], expires_at=p.token_expires_at, can_submit=not out and p.status in ("sent", "in_progress"), outstanding=out)


def answer_question(db: Session, p: RequestPack, key: str, answer: bool, by: str) -> None:
    qs = copy.deepcopy(p.questions or [])
    q = next((x for x in qs if x["key"] == key), None)
    if q is None:
        raise RequestError("unknown_question")
    q["answer"] = answer
    p.questions = qs
    if answer:
        t = _T.get(p.purpose, _T["custom"])
        existing = {i.key for i in p.items}
        order = max((i.order for i in p.items), default=0)
        for k, l, c, r, et in t["items"]:
            if k in q.get("adds", []) and k not in existing:
                order += 1
                db.add(RequestItem(tenant_id=p.tenant_id, pack_id=p.id, key=k, label=l, category=c, required=r, order=order))
    else:
        for i in list(p.items):
            if i.key in q.get("adds", []) and i.status == "pending":
                db.delete(i)
    if p.status == "sent":
        p.status = "in_progress"
    db.flush()
    db.refresh(p)


def attach(db: Session, p: RequestPack, item: RequestItem, doc: Document, by: str) -> None:
    if p.status in ("complete", "cancelled"):
        raise RequestError("closed")
    if item.status == "accepted":
        raise RequestError("already_accepted", "This item has been accepted — ask the practice to reopen it")
    item.document_id, item.uploaded_at, item.status, item.rejection_reason = doc.id, utcnow(), "uploaded", None
    item.classification = classify(doc.filename, doc.content_type, item)
    if p.status == "sent":
        p.status = "in_progress"
    doc.description = f"{p.title}: {item.label}"
    db.flush()
    events.emit(db, tenant_id=p.tenant_id, client_id=p.client_id, module_key="requests", kind="request.item_uploaded", summary=f"{by} uploaded {doc.filename} for “{item.label}”" + (" ⚑" if item.classification.get("flags") else ""),
                detail={"item": item.key, "classification": item.classification}, actor_label=by, ref_type="request_item", ref_id=item.id)


def mark_not_applicable(db: Session, p: RequestPack, item: RequestItem, note: str, by: str) -> None:
    if item.status == "accepted":
        raise RequestError("already_accepted")
    item.status, item.client_note = "not_applicable", note
    if p.status == "sent":
        p.status = "in_progress"
    db.flush()


def submit(db: Session, p: RequestPack, by: str) -> None:
    out = outstanding(p)
    if out:
        raise RequestError("incomplete", "Still outstanding: " + "; ".join(out))
    if p.status not in ("sent", "in_progress"):
        raise RequestError("closed", f"Request is {p.status}")
    p.status, p.submitted_at = "submitted", utcnow()
    events.emit(db, tenant_id=p.tenant_id, client_id=p.client_id, module_key="requests", kind="request.submitted", summary=f"{by} submitted {p.title}", actor_label=by, ref_type="request_pack", ref_id=p.id)
    if p.created_by_membership_id:
        exc = _counts(p)["exceptions"]
        notify_service.notify(db, tenant_id=p.tenant_id, membership_id=p.created_by_membership_id, kind="request.submitted", title=f"Submitted: {p.title}", body=f"{exc} item(s) flagged for review" if exc else "All items look consistent — review to complete", link=f"/requests/{p.id}", module_key="requests")
    db.flush()


# ------------------------------------------------------------------ review (staff)
def review(db: Session, tenant: Tenant, p: RequestPack, item: RequestItem, body: S.ReviewIn, actor_mid: uuid.UUID, actor_label: str) -> None:
    if item.status not in ("uploaded", "not_applicable", "rejected", "accepted"):
        raise RequestError("nothing_to_review", "The client has not provided this item yet")
    item.reviewed_by_membership_id, item.reviewed_at = actor_mid, utcnow()
    if body.decision == "accept":
        item.status, item.rejection_reason = "accepted", None
    else:
        if not body.reason:
            raise RequestError("reason_required", "A rejection needs a reason the client will see")
        item.status, item.rejection_reason = "rejected", body.reason
        if p.status in ("submitted", "reviewing"):
            p.status = "in_progress"
        ct = db.get(Contact, p.contact_id) if p.contact_id else None
        if ct and ct.email and p.token_hash is None:
            pass
        if ct and ct.email:
            # the client needs a working link to re-upload; rotate and send
            raw, h = new_opaque_token()
            p.token_hash, p.token_expires_at = h, utcnow() + timedelta(days=30)
            subject, text, html = templates.request_item_rejected(name=ct.first_name, practice=tenant.name, title=p.title, item=item.label, reason=body.reason, url=_url(raw))
            mailer.queue_email(db, tenant_id=tenant.id, to=ct.email, subject=subject, text=text, html=html, template="request_item_rejected", ref_type="request_item", ref_id=item.id)
    if p.status == "submitted":
        p.status = "reviewing"
    events.emit(db, tenant_id=tenant.id, client_id=p.client_id, module_key="requests", kind="request.item_reviewed", summary=f"“{item.label}” {item.status}" + (f" — {body.reason}" if body.reason else ""), actor_membership_id=actor_mid, actor_label=actor_label, ref_type="request_item", ref_id=item.id)
    # auto-complete when every required item is accepted/N/A and nothing is awaiting review
    if all(i.status in ("accepted", "not_applicable") or (not i.required and i.status == "pending") for i in p.items) and not any(i.status == "uploaded" for i in p.items):
        complete(db, tenant, p, actor_mid, actor_label)
    db.flush()


def complete(db: Session, tenant: Tenant, p: RequestPack, actor_mid: uuid.UUID | None, actor_label: str) -> None:
    if p.status == "complete":
        return
    p.status, p.completed_at, p.token_hash = "complete", utcnow(), None
    billing_service.record(db, tenant_id=tenant.id, kind="request.completed", module_key="requests", amount_cents=0, status="metered", detail={"pack_id": str(p.id), "items": len(p.items)})
    events.emit(db, tenant_id=tenant.id, client_id=p.client_id, module_key="requests", kind="request.completed", summary=f"Request complete: {p.title}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="request_pack", ref_id=p.id)


def overview(db: Session) -> S.OverviewOut:
    rows = db.execute(select(RequestPack)).scalars().all()
    today = date.today()
    since = utcnow() - timedelta(days=30)
    durations = [(p.submitted_at - p.sent_at).total_seconds() / 86400 for p in rows if p.submitted_at and p.sent_at]
    return S.OverviewOut(awaiting_client=sum(1 for p in rows if p.status in ("sent", "in_progress")), awaiting_review=sum(1 for p in rows if p.status in ("submitted", "reviewing")),
                         exceptions=sum(_counts(p)["exceptions"] for p in rows if p.status not in ("complete", "cancelled")), overdue=sum(1 for p in rows if p.due_on and p.due_on < today and p.status in ("sent", "in_progress")),
                         completed_30d=sum(1 for p in rows if p.completed_at and p.completed_at >= since), avg_days_to_submit=round(statistics.mean(durations), 1) if durations else None)


def remind_overdue(db: Session, now) -> int:
    """Lifecycle: one automatic reminder per pack, 3 days after the due date passes unsubmitted."""
    from app.core.tenancy import tenant_scope
    n = 0
    with platform_scope():
        rows = db.execute(select(RequestPack).where(RequestPack.status.in_(["sent", "in_progress"]), RequestPack.due_on.is_not(None), RequestPack.due_on < now.date() - timedelta(days=3), RequestPack.reminder_count == 0, RequestPack.token_hash.is_not(None))).scalars().all()
    for p in rows:
        with tenant_scope(p.tenant_id):
            db.info["tenant_id"] = p.tenant_id
            t = db.get(Tenant, p.tenant_id)
            try:
                send(db, t, p, None, "EnTIQ Requests", reminder=True)
                n += 1
            except RequestError:
                continue
        db.info.pop("tenant_id", None)
    return n
