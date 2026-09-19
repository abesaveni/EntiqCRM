from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import events
from app.core.security import utcnow
from app.models.crm import Client
from app.models.platform import Document
from app.models.tenant import Tenant
from app.modules.workpapers import ledger as ledger_mod
from app.modules.workpapers import schemas as S
from app.modules.workpapers.models import LedgerConnection, Workpaper, WorkpaperIssue, WorkpaperItem
from app.services import billing_service, notify_service
from app.services.crm_service import client_name_map, member_names

DEFAULT_MATERIALITY_CENTS = 100_000     # $1,000 unless the pack sets its own
VARIANCE_PCT_TRIGGER = 20.0


class WorkpaperError(Exception):
    def __init__(self, error: str, message: str | None = None):
        super().__init__(message or error)
        self.error, self.message = error, message or error


# ------------------------------------------------------------------ templates
TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    # pack type → (section, key, label)
    "financial_statements": [
        ("Checklist", "tb_agreed", "Trial balance agreed to the ledger"),
        ("Checklist", "prior_year", "Prior year comparatives agreed to signed accounts"),
        ("Assets", "bank_rec", "Bank reconciliation at balance date"),
        ("Assets", "debtors", "Debtors listing agreed and aged"),
        ("Assets", "inventory", "Stock on hand — count or valuation"),
        ("Assets", "fixed_assets", "Fixed asset register and depreciation schedule"),
        ("Liabilities", "creditors", "Creditors listing agreed"),
        ("Liabilities", "gst", "GST reconciliation to activity statements"),
        ("Liabilities", "payg", "PAYG withholding reconciled to STP"),
        ("Liabilities", "loans", "Loan balances agreed to statements"),
        ("Equity", "equity_movement", "Equity movements and drawings"),
        ("Income", "revenue", "Revenue reasonableness and cut-off"),
        ("Expenses", "expenses_review", "Expense analytical review"),
        ("Expenses", "wages", "Wages and superannuation reconciled"),
        ("Disclosures", "related_party", "Related party transactions and Division 7A"),
        ("Disclosures", "going_concern", "Going concern / solvency consideration"),
    ],
    "tax_return": [
        ("Checklist", "financials_signed", "Financial statements finalised and signed"),
        ("Tax", "reconciliation", "Accounting profit to taxable income reconciliation"),
        ("Tax", "depreciation_tax", "Tax depreciation and instant asset write-off"),
        ("Tax", "div7a", "Division 7A loans and minimum repayments"),
        ("Tax", "franking", "Franking account balance"),
        ("Tax", "losses", "Carried-forward losses and continuity tests"),
        ("Tax", "payg_instalments", "PAYG instalments paid for the year"),
        ("Tax", "offsets", "Tax offsets and rebates claimed"),
        ("Disclosures", "declaration", "Client declaration signed"),
    ],
    "bas": [
        ("Checklist", "period_closed", "Ledger closed for the period"),
        ("Liabilities", "gst_collected", "GST on sales (1A)"),
        ("Liabilities", "gst_paid", "GST on purchases (1B)"),
        ("Liabilities", "paygw", "PAYG withholding (W1/W2)"),
        ("Checklist", "coding_review", "GST coding exceptions reviewed"),
        ("Checklist", "client_approval", "Client approval received"),
    ],
    "smsf": [
        ("Checklist", "deed_reviewed", "Trust deed and investment strategy reviewed"),
        ("Assets", "investments", "Investments at market value with evidence"),
        ("Assets", "bank_rec", "Bank reconciliation"),
        ("Income", "contributions", "Contributions within caps"),
        ("Expenses", "pensions", "Pension payments meet minimums"),
        ("Disclosures", "audit_ready", "Audit evidence pack prepared"),
    ],
    "audit": [
        ("Checklist", "engagement", "Engagement letter and independence"),
        ("Checklist", "planning", "Planning and materiality memo"),
        ("Assets", "confirmations", "Bank and debtor confirmations"),
        ("Disclosures", "management_rep", "Management representation letter"),
    ],
}
SECTION_ORDER = ["Checklist", "Assets", "Liabilities", "Equity", "Income", "Expenses", "Tax", "Disclosures"]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:80]


# ------------------------------------------------------------------ serialisers
def item_out(i: WorkpaperItem, names: dict, docs: dict, materiality: int) -> S.ItemOut:
    return S.ItemOut(id=i.id, section=i.section, key=i.key, label=i.label, description=i.description, order=i.order, account_code=i.account_code, value_cents=i.value_cents, prior_cents=i.prior_cents,
                     variance_cents=i.variance_cents, variance_pct=i.variance_pct, status=i.status, evidence_state=i.evidence_state, document_id=i.document_id,
                     document_filename=docs.get(i.document_id) if i.document_id else None, workings=i.workings, query=i.query,
                     prepared_by_name=names.get(i.prepared_by_membership_id) if i.prepared_by_membership_id else None, prepared_at=i.prepared_at,
                     reviewed_by_name=names.get(i.reviewed_by_membership_id) if i.reviewed_by_membership_id else None, reviewed_at=i.reviewed_at,
                     material=bool(i.variance_cents and abs(i.variance_cents) >= materiality))


def issue_out(x: WorkpaperIssue, names: dict, items: dict) -> S.IssueOut:
    return S.IssueOut(id=x.id, item_id=x.item_id, item_label=items.get(x.item_id), kind=x.kind, title=x.title, detail=x.detail, severity=x.severity, blocking=x.blocking, status=x.status, auto=x.auto,
                      raised_by_name=names.get(x.raised_by_membership_id) if x.raised_by_membership_id else None, resolved_by_name=names.get(x.resolved_by_membership_id) if x.resolved_by_membership_id else None,
                      resolution=x.resolution, resolved_at=x.resolved_at, created_at=x.created_at)


def _totals(p: Workpaper) -> dict[str, int]:
    t: dict[str, int] = {}
    for i in p.items:
        if i.value_cents is not None:
            t[i.section] = t.get(i.section, 0) + i.value_cents
    return t


def pack_out(db: Session, p: Workpaper, names: dict | None = None, clients: dict | None = None) -> S.PackOut:
    names = names if names is not None else member_names(db, {p.preparer_membership_id, p.reviewer_membership_id, p.signed_off_by_membership_id})
    clients = clients if clients is not None else client_name_map(db, {p.client_id})
    totals = _totals(p)
    net_assets = None
    if any(k in totals for k in ("Assets", "Liabilities")):
        net_assets = totals.get("Assets", 0) + totals.get("Liabilities", 0)
    conn = db.execute(select(LedgerConnection).where(LedgerConnection.client_id == p.client_id).order_by(LedgerConnection.created_at.desc())).scalars().first()
    return S.PackOut(id=p.id, client_id=p.client_id, client_name=clients.get(p.client_id), job_id=p.job_id, title=p.title, pack_type=p.pack_type, period_label=p.period_label, period_start=p.period_start,
                     period_end=p.period_end, status=p.status, preparer_name=names.get(p.preparer_membership_id) if p.preparer_membership_id else None,
                     reviewer_name=names.get(p.reviewer_membership_id) if p.reviewer_membership_id else None, prepared_at=p.prepared_at, reviewed_at=p.reviewed_at, signed_off_at=p.signed_off_at,
                     signed_off_by_name=names.get(p.signed_off_by_membership_id) if p.signed_off_by_membership_id else None, lodged_at=p.lodged_at, lodgement_ref=p.lodgement_ref,
                     materiality_cents=p.materiality_cents, ledger_source=p.ledger_source, ledger_synced_at=p.ledger_synced_at, ledger_simulated=bool(conn.simulated) if conn else True,
                     seal_sha256=p.seal_sha256, items_total=len(p.items), items_done=sum(1 for i in p.items if i.status in ("reviewed", "signed_off", "n_a")),
                     evidence_attached=sum(1 for i in p.items if i.evidence_state != "missing"), open_issues=sum(1 for x in p.issues if x.status == "open"),
                     blocking_issues=sum(1 for x in p.issues if x.status == "open" and x.blocking), net_assets_cents=net_assets, created_at=p.created_at, updated_at=p.updated_at)


def pack_detail(db: Session, p: Workpaper) -> S.PackDetail:
    base = pack_out(db, p)
    names = member_names(db, {i.prepared_by_membership_id for i in p.items} | {i.reviewed_by_membership_id for i in p.items} | {x.raised_by_membership_id for x in p.issues} | {x.resolved_by_membership_id for x in p.issues})
    ids = [i.document_id for i in p.items if i.document_id]
    docs = {d.id: d.filename for d in db.execute(select(Document).where(Document.id.in_(ids))).scalars()} if ids else {}
    labels = {i.id: i.label for i in p.items}
    mat = p.materiality_cents or DEFAULT_MATERIALITY_CENTS
    sections = [s for s in SECTION_ORDER if any(i.section == s for i in p.items)] + sorted({i.section for i in p.items} - set(SECTION_ORDER))
    return S.PackDetail(**base.model_dump(), items=[item_out(i, names, docs, mat) for i in p.items], issues=[issue_out(x, names, labels) for x in sorted(p.issues, key=lambda x: (x.status != "open", x.created_at))],
                        sections=sections, totals=_totals(p), notes=p.notes)


# ------------------------------------------------------------------ lifecycle
def create(db: Session, tenant: Tenant, body: S.PackIn, actor_mid: uuid.UUID, actor_label: str) -> Workpaper:
    c = db.get(Client, body.client_id)
    if c is None:
        raise WorkpaperError("client_not_found")
    title = body.title or f"{body.pack_type.replace('_', ' ').title()}{' · ' + body.period_label if body.period_label else ''} — {c.name}"
    p = Workpaper(tenant_id=tenant.id, client_id=c.id, job_id=body.job_id, title=title[:300], pack_type=body.pack_type, period_label=body.period_label, period_start=body.period_start, period_end=body.period_end,
                  preparer_membership_id=body.preparer_membership_id or actor_mid, reviewer_membership_id=body.reviewer_membership_id, materiality_cents=body.materiality_cents or DEFAULT_MATERIALITY_CENTS)
    db.add(p)
    db.flush()
    if body.use_template:
        for n, (section, key, label) in enumerate(TEMPLATES.get(body.pack_type, []), 1):
            db.add(WorkpaperItem(tenant_id=tenant.id, pack_id=p.id, section=section, key=key, label=label, order=n))
    db.flush()
    db.refresh(p)
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="workpapers", kind="workpaper.created", summary=f"Workpapers opened: {p.title}", detail={"pack_type": p.pack_type, "items": len(p.items)},
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="workpaper", ref_id=p.id)
    if p.preparer_membership_id and p.preparer_membership_id != actor_mid:
        notify_service.notify(db, tenant_id=tenant.id, membership_id=p.preparer_membership_id, kind="workpaper.assigned", title=f"Workpapers to prepare: {p.title}", link=f"/workpapers/{p.id}", module_key="workpapers")
    return p


def add_item(db: Session, p: Workpaper, body: S.ItemIn) -> WorkpaperItem:
    key = body.key or _slug(body.label)
    existing = {i.key for i in p.items}
    n = 2
    while key in existing:
        key = f"{key}_{n}"; n += 1
    it = WorkpaperItem(tenant_id=p.tenant_id, pack_id=p.id, section=body.section, key=key, label=body.label, description=body.description, account_code=body.account_code,
                       order=max((i.order for i in p.items), default=0) + 1, value_cents=body.value_cents, prior_cents=body.prior_cents)
    _recompute(it)
    p.items.append(it)
    db.flush()
    return it


def _recompute(i: WorkpaperItem) -> None:
    if i.value_cents is None or i.prior_cents is None:
        i.variance_cents = i.variance_pct = None
        return
    i.variance_cents = i.value_cents - i.prior_cents
    i.variance_pct = round(i.variance_cents / abs(i.prior_cents) * 100, 2) if i.prior_cents else None


def patch_item(db: Session, p: Workpaper, i: WorkpaperItem, body: S.ItemPatch, actor_mid: uuid.UUID, actor_label: str) -> WorkpaperItem:
    if p.status in ("signed_off", "lodged", "archived"):
        raise WorkpaperError("locked", f"The pack is {p.status.replace('_', ' ')} — reopen it to make changes")
    data = body.model_dump(exclude_unset=True)
    if "document_id" in data:
        if data["document_id"]:
            d = db.get(Document, data["document_id"])
            if d is None or d.deleted_at is not None:
                raise WorkpaperError("document_not_found")
            i.evidence_state = "attached"
        else:
            i.evidence_state = "missing"
    for k, v in data.items():
        setattr(i, k, v)
    if "value_cents" in data or "prior_cents" in data:
        _recompute(i)
    if data.get("status") in ("prepared", "reviewed", "signed_off"):
        if data["status"] == "prepared":
            i.prepared_by_membership_id, i.prepared_at = actor_mid, utcnow()
        else:
            i.reviewed_by_membership_id, i.reviewed_at = actor_mid, utcnow()
    elif "workings" in data and i.status == "not_started":
        i.status, i.prepared_by_membership_id, i.prepared_at = "prepared", actor_mid, utcnow()
    if p.status == "draft":
        p.status = "in_progress"
    db.flush()
    return i


def raise_issue(db: Session, p: Workpaper, body: S.IssueIn, actor_mid: uuid.UUID | None, actor_label: str, *, auto: bool = False) -> WorkpaperIssue:
    x = WorkpaperIssue(tenant_id=p.tenant_id, pack_id=p.id, item_id=body.item_id, kind=body.kind, title=body.title[:300], detail=body.detail, severity=body.severity, blocking=body.blocking,
                       raised_by_membership_id=actor_mid, auto=auto)
    p.issues.append(x)
    # A reviewer's query parks the item; the automatic rules only flag the issue, so a non-blocking
    # variance note never leaves an item stuck in "queried".
    if body.item_id and not auto:
        it = next((i for i in p.items if i.id == body.item_id), None)
        if it and it.status != "signed_off":
            it.status, it.query = "queried", body.title[:600]
    db.flush()
    if not auto:
        events.emit(db, tenant_id=p.tenant_id, client_id=p.client_id, module_key="workpapers", kind="workpaper.issue_raised", summary=f"Query on {p.title}: {x.title}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="workpaper", ref_id=p.id)
        if p.preparer_membership_id and p.preparer_membership_id != actor_mid:
            notify_service.notify(db, tenant_id=p.tenant_id, membership_id=p.preparer_membership_id, kind="workpaper.query", title=f"Review query: {x.title}", body=p.title, link=f"/workpapers/{p.id}", module_key="workpapers")
    return x


def resolve_issue(db: Session, p: Workpaper, x: WorkpaperIssue, body: S.IssueResolveIn, actor_mid: uuid.UUID, actor_label: str) -> WorkpaperIssue:
    if x.status != "open":
        raise WorkpaperError("already_closed")
    x.status, x.resolution, x.resolved_by_membership_id, x.resolved_at = "waived" if body.waive else "resolved", body.resolution, actor_mid, utcnow()
    if x.item_id:
        it = next((i for i in p.items if i.id == x.item_id), None)
        if it and it.status == "queried" and not any(o.item_id == it.id and o.status == "open" and o.id != x.id for o in p.issues):
            it.status, it.query = "prepared", None
    db.flush()
    return x


def run_checks(db: Session, p: Workpaper, actor_label: str = "EnTIQ Workpapers") -> int:
    """
    The rules: material unexplained variances, missing evidence on valued items, and an out-of-balance
    trial balance. Re-running clears auto issues that no longer apply, so the list always reflects the pack.
    """
    mat = p.materiality_cents or DEFAULT_MATERIALITY_CENTS
    wanted: dict[tuple[str, uuid.UUID | None], tuple[str, str, str, bool]] = {}
    for i in p.items:
        if i.variance_cents is not None and abs(i.variance_cents) >= mat and (i.variance_pct is None or abs(i.variance_pct) >= VARIANCE_PCT_TRIGGER) and not i.workings:
            wanted[("variance", i.id)] = ("variance", f"{i.label}: {_money(i.variance_cents)} movement ({i.variance_pct:+.0f}%)" if i.variance_pct is not None else f"{i.label}: {_money(i.variance_cents)} movement",
                                          "Material movement with no workings recorded. Explain or attach evidence.", False)
        if i.value_cents is not None and abs(i.value_cents) >= mat and i.evidence_state == "missing" and i.section in ("Assets", "Liabilities"):
            wanted[("missing_evidence", i.id)] = ("missing_evidence", f"{i.label}: no evidence attached", "Balance-sheet items above materiality need supporting evidence before sign-off.", True)
    totals = _totals(p)
    if any(k in totals for k in ("Assets", "Liabilities", "Equity")):
        out_of_balance = sum(totals.get(k, 0) for k in ("Assets", "Liabilities", "Equity", "Income", "Expenses"))
        if abs(out_of_balance) > 100:   # $1
            wanted[("unreconciled", None)] = ("unreconciled", f"Trial balance does not balance by {_money(out_of_balance)}", "The sum of all sections should be nil. Check the ledger sync or manual entries.", True)
    have = {(x.kind, x.item_id): x for x in p.issues if x.auto and x.status == "open"}
    created = 0
    for key, (kind, title, detail, blocking) in wanted.items():
        if key in have:
            have[key].title, have[key].detail = title[:300], detail
            continue
        raise_issue(db, p, S.IssueIn(item_id=key[1], kind=kind, title=title, detail=detail, severity="high" if blocking else "medium", blocking=blocking), None, actor_label, auto=True)
        created += 1
    for key, x in have.items():
        if key not in wanted:
            x.status, x.resolution, x.resolved_at = "resolved", "Resolved automatically — the condition no longer applies.", utcnow()
    db.flush()
    return created


def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def submit_for_review(db: Session, p: Workpaper, actor_mid: uuid.UUID, actor_label: str) -> Workpaper:
    if p.status in ("signed_off", "lodged", "archived"):
        raise WorkpaperError("locked")
    unprepared = [i.label for i in p.items if i.status == "not_started"]
    if unprepared:
        raise WorkpaperError("not_prepared", f"{len(unprepared)} item(s) not started: " + "; ".join(unprepared[:5]))
    run_checks(db, p)
    p.status, p.prepared_at = "in_review", utcnow()
    events.emit(db, tenant_id=p.tenant_id, client_id=p.client_id, module_key="workpapers", kind="workpaper.submitted", summary=f"{p.title} submitted for review", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="workpaper", ref_id=p.id)
    if p.reviewer_membership_id:
        notify_service.notify(db, tenant_id=p.tenant_id, membership_id=p.reviewer_membership_id, kind="workpaper.review", title=f"Ready for review: {p.title}", body=f"{sum(1 for x in p.issues if x.status == 'open')} open issue(s)", link=f"/workpapers/{p.id}", module_key="workpapers")
    return p


def sign_off(db: Session, tenant: Tenant, p: Workpaper, body: S.SignOffIn, actor_mid: uuid.UUID, actor_label: str) -> Workpaper:
    if p.status == "signed_off":
        raise WorkpaperError("already_signed_off")
    if p.status not in ("in_review", "in_progress"):
        raise WorkpaperError("wrong_state", f"A pack in {p.status.replace('_', ' ')} cannot be signed off")
    run_checks(db, p)
    blocking = [x.title for x in p.issues if x.status == "open" and x.blocking]
    if blocking:
        raise WorkpaperError("blocking_issues", "Resolve or waive first: " + "; ".join(blocking[:5]))
    queried = [i.label for i in p.items if i.status == "queried"]
    if queried:
        raise WorkpaperError("open_queries", "Items still under query: " + "; ".join(queried[:5]))
    now = utcnow()
    for i in p.items:
        if i.status in ("prepared", "reviewed"):
            i.status = "signed_off"
    material = "|".join(f"{i.key}:{i.value_cents}:{i.evidence_state}:{i.document_id}" for i in sorted(p.items, key=lambda x: x.key)) + f"|{now.isoformat()}"
    p.seal_sha256 = hashlib.sha256(material.encode()).hexdigest()
    p.status, p.reviewed_at, p.signed_off_at, p.signed_off_by_membership_id = "signed_off", p.reviewed_at or now, now, actor_mid
    if body.note:
        p.notes = f"{p.notes}\n\n{body.note}" if p.notes else body.note
    billing_service.record(db, tenant_id=tenant.id, kind="workpaper.signed_off", module_key="workpapers", amount_cents=0, status="metered", detail={"pack_id": str(p.id), "pack_type": p.pack_type, "items": len(p.items)})
    events.emit(db, tenant_id=tenant.id, client_id=p.client_id, module_key="workpapers", kind="workpaper.signed_off", summary=f"{p.title} signed off by {actor_label}", detail={"seal": p.seal_sha256}, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="workpaper", ref_id=p.id)
    # close the linked practice job, if any
    if p.job_id:
        from app.modules.practice.models import Job
        from app.modules.practice import service as practice_service
        j = db.get(Job, p.job_id)
        if j is not None and j.status not in ("complete", "cancelled"):
            practice_service.set_status(db, j, "complete", f"Workpapers signed off ({p.title})", actor_mid, actor_label)
    return p


def reopen(db: Session, p: Workpaper, actor_mid: uuid.UUID, actor_label: str) -> Workpaper:
    if p.status not in ("signed_off", "in_review"):
        raise WorkpaperError("wrong_state")
    if p.lodged_at:
        raise WorkpaperError("lodged", "A lodged pack cannot be reopened — prepare an amendment instead")
    p.status, p.signed_off_at, p.signed_off_by_membership_id, p.seal_sha256 = "in_progress", None, None, None
    for i in p.items:
        if i.status == "signed_off":
            i.status = "prepared"
    events.emit(db, tenant_id=p.tenant_id, client_id=p.client_id, module_key="workpapers", kind="workpaper.reopened", summary=f"{p.title} reopened", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="workpaper", ref_id=p.id)
    return p


def lodge(db: Session, p: Workpaper, body: S.LodgeIn, actor_mid: uuid.UUID, actor_label: str) -> Workpaper:
    if p.status != "signed_off":
        raise WorkpaperError("not_signed_off", "Sign off the pack before recording lodgement")
    p.status, p.lodged_at, p.lodgement_ref = "lodged", utcnow(), body.reference
    events.emit(db, tenant_id=p.tenant_id, client_id=p.client_id, module_key="workpapers", kind="workpaper.lodged", summary=f"{p.title} lodged — {body.reference}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="workpaper", ref_id=p.id)
    return p


# ------------------------------------------------------------------ ledger
def connection_out(db: Session, c: LedgerConnection, names: dict | None = None, clients: dict | None = None) -> S.LedgerConnectionOut:
    names = names if names is not None else member_names(db, {c.connected_by_membership_id})
    clients = clients if clients is not None else client_name_map(db, {c.client_id})
    return S.LedgerConnectionOut(id=c.id, client_id=c.client_id, client_name=clients.get(c.client_id) if c.client_id else None, provider=c.provider, status=c.status, simulated=c.simulated,
                                 external_name=c.external_name, external_tenant_id=c.external_tenant_id, scopes=c.scopes, last_sync_at=c.last_sync_at, last_error=c.last_error,
                                 connected_by_name=names.get(c.connected_by_membership_id) if c.connected_by_membership_id else None, created_at=c.created_at)


def connect(db: Session, tenant: Tenant, body: S.ConnectIn, actor_mid: uuid.UUID, actor_label: str) -> tuple[LedgerConnection, str | None]:
    c = db.get(Client, body.client_id)
    if c is None:
        raise WorkpaperError("client_not_found")
    conn = db.execute(select(LedgerConnection).where(LedgerConnection.client_id == c.id, LedgerConnection.provider == body.provider)).scalars().first()
    if conn is None:
        conn = LedgerConnection(tenant_id=tenant.id, client_id=c.id, provider=body.provider, connected_by_membership_id=actor_mid)
        db.add(conn)
    live = ledger_mod.live_available() and body.provider == "xero"
    conn.simulated = not live
    conn.status = "pending" if live else "connected"
    conn.external_name = None if live else f"{c.name} (simulated ledger)"
    conn.external_tenant_id = conn.external_tenant_id or (None if live else f"sim-{c.id.hex[:12]}")
    conn.scopes = ledger_mod.XERO_SCOPES if body.provider == "xero" else None
    db.flush()
    url = ledger_mod.provider_for(body.provider).authorize_url(str(conn.id)) if live else None
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="workpapers", kind="ledger.connected", summary=f"{body.provider.title()} {'authorisation started' if live else 'connected in simulation'} for {c.name}",
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="ledger_connection", ref_id=conn.id)
    return conn, url


def sync(db: Session, p: Workpaper, actor_mid: uuid.UUID, actor_label: str) -> tuple[int, bool, str, str]:
    """Pull the trial balance onto the pack: matched items update, unmatched accounts are added."""
    if p.status in ("signed_off", "lodged", "archived"):
        raise WorkpaperError("locked")
    c = db.get(Client, p.client_id)
    conn = db.execute(select(LedgerConnection).where(LedgerConnection.client_id == p.client_id, LedgerConnection.status.in_(["connected", "pending"])).order_by(LedgerConnection.created_at.desc())).scalars().first()
    provider = ledger_mod.provider_for(conn.provider if conn else "xero")
    try:
        result = provider.trial_balance(client_name=c.name, period_end=p.period_end, external_tenant_id=conn.external_tenant_id if conn else None, token=None)
    except Exception as e:  # noqa: BLE001 — a ledger outage must not break the pack
        if conn:
            conn.status, conn.last_error = "error", str(e)[:500]
            db.flush()
        raise WorkpaperError("ledger_unavailable", f"Could not read the ledger: {e}")
    by_code = {i.account_code: i for i in p.items if i.account_code}
    order = max((i.order for i in p.items), default=0)
    n = 0
    for line in result.lines:
        it = by_code.get(line.account_code)
        if it is None:
            order += 1
            it = WorkpaperItem(tenant_id=p.tenant_id, pack_id=p.id, section=line.section, key=_slug(f"{line.account_code}_{line.label}"), label=line.label, account_code=line.account_code, order=order)
            p.items.append(it)
        it.value_cents, it.prior_cents = line.value_cents, line.prior_cents
        _recompute(it)
        n += 1
    p.ledger_source = result.source
    p.ledger_synced_at = utcnow()
    p.ledger_ref = result.organisation
    if p.status == "draft":
        p.status = "in_progress"
    if conn:
        conn.status, conn.last_sync_at, conn.last_error, conn.simulated = "connected", utcnow(), None, result.simulated
    db.flush()
    run_checks(db, p)
    events.emit(db, tenant_id=p.tenant_id, client_id=p.client_id, module_key="workpapers", kind="ledger.synced", summary=f"Trial balance synced from {result.source}{' (simulated)' if result.simulated else ''}: {n} accounts",
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="workpaper", ref_id=p.id)
    return n, result.simulated, result.source, (result.detail or {}).get("note", "")


# ------------------------------------------------------------------ overview
def overview(db: Session) -> S.OverviewOut:
    rows = db.execute(select(Workpaper)).scalars().all()
    since = utcnow() - timedelta(days=30)
    by_type: dict[str, int] = {}
    for p in rows:
        if p.status in ("in_progress", "in_review"):
            by_type[p.pack_type] = by_type.get(p.pack_type, 0) + 1
    issues = db.execute(select(WorkpaperIssue).where(WorkpaperIssue.status == "open")).scalars().all()
    return S.OverviewOut(in_progress=sum(1 for p in rows if p.status == "in_progress"), in_review=sum(1 for p in rows if p.status == "in_review"),
                         signed_off_30d=sum(1 for p in rows if p.signed_off_at and p.signed_off_at >= since), lodged_30d=sum(1 for p in rows if p.lodged_at and p.lodged_at >= since),
                         open_issues=len(issues), blocking_issues=sum(1 for x in issues if x.blocking), by_type=by_type,
                         ledger_connections=db.execute(select(func.count()).select_from(LedgerConnection).where(LedgerConnection.status == "connected")).scalar_one(), ledger_live=ledger_mod.live_available())
