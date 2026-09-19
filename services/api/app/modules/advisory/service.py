from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import entitlements, events
from app.core.security import utcnow
from app.models.crm import Client, Task
from app.models.tenant import Tenant
from app.modules.advisory import schemas as S
from app.modules.advisory.models import Action, Alert, Meeting, Snapshot
from app.services import notify_service
from app.services.crm_service import client_name_map, member_names


class AdvisoryError(Exception):
    def __init__(self, error: str, message: str | None = None):
        super().__init__(message or error)
        self.error, self.message = error, message or error


# ------------------------------------------------------------------ deriving a snapshot from workpapers
_SECTION_SIGNS = {"Income": -1, "Expenses": 1, "Assets": 1, "Liabilities": -1, "Equity": -1}
_MATCH = {
    "cash": ("bank", "cash at bank", "savings"),
    "receivables": ("receivable", "debtor"),
    "payables": ("payable", "creditor"),
    "inventory": ("inventory", "stock"),
    "debt": ("loan", "borrowing", "finance", "hire purchase"),
    "tax_provision": ("provision for income tax", "income tax payable"),
    "cogs": ("cost of goods", "cost of sales", "purchases"),
}


def from_workpaper(db: Session, pack) -> dict[str, int | None]:
    """Fold a workpaper's trial balance into the advisory headline figures (all positive-as-reported, in cents)."""
    out: dict[str, int | None] = {k: None for k in ("revenue_cents", "gross_profit_cents", "expenses_cents", "net_profit_cents", "cash_cents", "receivables_cents", "payables_cents", "inventory_cents", "debt_cents", "equity_cents", "tax_provision_cents")}
    totals: dict[str, int] = {}
    buckets: dict[str, int] = {}
    for i in pack.items:
        if i.value_cents is None:
            continue
        totals[i.section] = totals.get(i.section, 0) + i.value_cents
        label = (i.label or "").lower()
        for key, needles in _MATCH.items():
            if any(n in label for n in needles):
                buckets[key] = buckets.get(key, 0) + i.value_cents
    if "Income" in totals:
        out["revenue_cents"] = abs(totals["Income"])
    if "Expenses" in totals:
        out["expenses_cents"] = totals["Expenses"]
    if out["revenue_cents"] is not None and out["expenses_cents"] is not None:
        out["net_profit_cents"] = out["revenue_cents"] - out["expenses_cents"]
    if out["revenue_cents"] is not None and "cogs" in buckets:
        out["gross_profit_cents"] = out["revenue_cents"] - abs(buckets["cogs"])
    for key, field in (("cash", "cash_cents"), ("receivables", "receivables_cents"), ("inventory", "inventory_cents")):
        if key in buckets:
            out[field] = abs(buckets[key])
    for key, field in (("payables", "payables_cents"), ("debt", "debt_cents"), ("tax_provision", "tax_provision_cents")):
        if key in buckets:
            out[field] = abs(buckets[key])
    if "Equity" in totals:
        out["equity_cents"] = abs(totals["Equity"])
    return out


def compute_kpis(s: Snapshot) -> tuple[dict[str, Any], int | None, str | None]:
    k: dict[str, Any] = {}
    rev, np_, gp = s.revenue_cents, s.net_profit_cents, s.gross_profit_cents
    if rev:
        if gp is not None:
            k["gross_margin_pct"] = round(gp / rev * 100, 1)
        if np_ is not None:
            k["net_margin_pct"] = round(np_ / rev * 100, 1)
        if s.receivables_cents is not None:
            k["debtor_days"] = round(s.receivables_cents / rev * 365, 1)
        if s.payables_cents is not None and s.expenses_cents:
            k["creditor_days"] = round(s.payables_cents / s.expenses_cents * 365, 1)
        if s.inventory_cents is not None and gp is not None:
            cogs = rev - gp
            if cogs > 0:
                k["inventory_days"] = round(s.inventory_cents / cogs * 365, 1)
    current_assets = sum(v for v in (s.cash_cents, s.receivables_cents, s.inventory_cents) if v is not None)
    current_liabs = sum(v for v in (s.payables_cents, s.tax_provision_cents) if v is not None)
    if current_liabs:
        k["current_ratio"] = round(current_assets / current_liabs, 2)
    if s.expenses_cents and s.cash_cents is not None:
        monthly_burn = s.expenses_cents / 12
        if monthly_burn > 0:
            k["cash_runway_months"] = round(s.cash_cents / monthly_burn, 1)
    if s.equity_cents and s.debt_cents is not None:
        k["debt_to_equity"] = round(s.debt_cents / s.equity_cents, 2)
    if "debtor_days" in k and "creditor_days" in k:
        k["cash_conversion_days"] = round(k["debtor_days"] + k.get("inventory_days", 0) - k["creditor_days"], 1)
    # health: start at 70, move on the ratios that matter to an owner
    score: float | None = None
    if k:
        score = 70.0
        if "net_margin_pct" in k:
            score += max(-25, min(20, (k["net_margin_pct"] - 5) * 1.5))
        if "current_ratio" in k:
            score += max(-15, min(10, (k["current_ratio"] - 1.2) * 12))
        if "cash_runway_months" in k:
            score += max(-15, min(10, (k["cash_runway_months"] - 3) * 2.5))
        if "debtor_days" in k:
            score += max(-12, min(8, (45 - k["debtor_days"]) * 0.3))
        if "debt_to_equity" in k:
            score += max(-10, min(6, (1.5 - k["debt_to_equity"]) * 6))
        score = max(0, min(100, score))
    band = None if score is None else ("good" if score >= 70 else "watch" if score >= 45 else "needs_action")
    return k, (round(score) if score is not None else None), band


# ------------------------------------------------------------------ alert rules
RULES: list[tuple[str, str, str]] = [
    # code, metric, human name (thresholds live in the function, so the message can carry the number)
    ("low_runway", "cash_runway_months", "Cash runway"),
    ("tight_liquidity", "current_ratio", "Current ratio"),
    ("slow_debtors", "debtor_days", "Debtor days"),
    ("thin_margin", "net_margin_pct", "Net margin"),
    ("high_gearing", "debt_to_equity", "Debt to equity"),
    ("tax_unprovisioned", "tax_cover", "Tax provision cover"),
]


def evaluate(db: Session, s: Snapshot, client: Client) -> list[Alert]:
    k = s.kpis or {}
    found: list[tuple[str, str, str, str, str, float | None, float | None, str]] = []
    if "cash_runway_months" in k and k["cash_runway_months"] < 3:
        found.append(("low_runway", "action" if k["cash_runway_months"] < 1.5 else "watch", "cash_runway_months",
                      f"Cash runway is {k['cash_runway_months']} months", f"Cash of {_m(s.cash_cents)} against annual expenses of {_m(s.expenses_cents)}. Under three months of cover leaves no room for a late payment or a quiet quarter.",
                      k["cash_runway_months"], 3.0, "Build a 13-week cash forecast, chase the oldest debtors this week, and agree a minimum cash floor with the owner."))
    if "current_ratio" in k and k["current_ratio"] < 1.2:
        found.append(("tight_liquidity", "action" if k["current_ratio"] < 1.0 else "watch", "current_ratio",
                      f"Current ratio is {k['current_ratio']}", "Current assets barely cover current liabilities; below 1.0 the business is technically unable to meet short-term obligations from working capital.",
                      k["current_ratio"], 1.5, "Review payment terms both ways, defer discretionary spend, and check whether the ATO balance needs a payment plan."))
    if "debtor_days" in k and k["debtor_days"] > 60:
        found.append(("slow_debtors", "action" if k["debtor_days"] > 90 else "watch", "debtor_days",
                      f"Debtors are averaging {k['debtor_days']} days", f"Receivables of {_m(s.receivables_cents)} on revenue of {_m(s.revenue_cents)}. Every 10 days of debtor time is roughly {_m(int((s.revenue_cents or 0) / 36.5))} of cash locked up.",
                      k["debtor_days"], 45.0, "Send statements weekly, put the top five overdue accounts on a call list, and consider deposits or progress claims for new work."))
    if "net_margin_pct" in k and k["net_margin_pct"] < 5:
        found.append(("thin_margin", "action" if k["net_margin_pct"] < 0 else "watch", "net_margin_pct",
                      f"Net margin is {k['net_margin_pct']}%", f"Net profit of {_m(s.net_profit_cents)} on revenue of {_m(s.revenue_cents)}.",
                      k["net_margin_pct"], 10.0, "Review pricing on the lowest-margin work, and compare the largest three expense lines against last year before they are locked in."))
    if "debt_to_equity" in k and k["debt_to_equity"] > 1.5:
        found.append(("high_gearing", "watch", "debt_to_equity", f"Debt to equity is {k['debt_to_equity']}",
                      f"Borrowings of {_m(s.debt_cents)} against equity of {_m(s.equity_cents)}.", k["debt_to_equity"], 1.0,
                      "Check covenant headroom and refinancing dates; model the effect of a 1% rate rise on serviceability."))
    if s.tax_provision_cents is not None and s.net_profit_cents and s.net_profit_cents > 0:
        expected = int(s.net_profit_cents * 0.25)
        if s.tax_provision_cents < expected * 0.5:
            found.append(("tax_unprovisioned", "action", "tax_cover", "Tax provision looks light",
                          f"Provision of {_m(s.tax_provision_cents)} against profit of {_m(s.net_profit_cents)} — a company rate would suggest around {_m(expected)}.",
                          float(s.tax_provision_cents or 0) / 100, float(expected) / 100,
                          "Estimate the position now, set aside cash monthly, and review PAYG instalments so the shortfall is not a surprise at lodgement."))
    existing = {a.code: a for a in db.execute(select(Alert).where(Alert.client_id == client.id, Alert.status == "open", Alert.auto.is_(True))).scalars()}
    out: list[Alert] = []
    codes = set()
    for code, severity, metric, title, detail, value, benchmark, rec in found:
        codes.add(code)
        a = existing.get(code)
        if a is None:
            a = Alert(tenant_id=s.tenant_id, client_id=client.id, snapshot_id=s.id, code=code, title=title, detail=detail, severity=severity, metric=metric, value=value, benchmark=benchmark, recommendation=rec)
            db.add(a)
        else:
            a.title, a.detail, a.severity, a.value, a.benchmark, a.snapshot_id, a.recommendation = title, detail, severity, value, benchmark, s.id, rec
        out.append(a)
    for code, a in existing.items():
        if code not in codes:
            a.status, a.resolved_at, a.dismissed_reason = "dismissed", utcnow(), "Resolved — the measure is back within range."
    db.flush()
    return out


def _m(cents: int | None) -> str:
    return "—" if cents is None else f"${cents / 100:,.0f}"


# ------------------------------------------------------------------ serialisers
def snapshot_out(s: Snapshot, names: dict, clients: dict) -> S.SnapshotOut:
    return S.SnapshotOut(id=s.id, client_id=s.client_id, client_name=clients.get(s.client_id), as_at=s.as_at, period_label=s.period_label, source=s.source, simulated=s.simulated, workpaper_id=s.workpaper_id,
                         revenue_cents=s.revenue_cents, gross_profit_cents=s.gross_profit_cents, expenses_cents=s.expenses_cents, net_profit_cents=s.net_profit_cents, cash_cents=s.cash_cents,
                         receivables_cents=s.receivables_cents, payables_cents=s.payables_cents, inventory_cents=s.inventory_cents, debt_cents=s.debt_cents, equity_cents=s.equity_cents,
                         tax_provision_cents=s.tax_provision_cents, kpis=s.kpis or {}, health_score=s.health_score, health_band=s.health_band, notes=s.notes,
                         created_by_name=names.get(s.created_by_membership_id) if s.created_by_membership_id else None, created_at=s.created_at)


def alert_out(a: Alert, clients: dict) -> S.AlertOut:
    return S.AlertOut(id=a.id, client_id=a.client_id, client_name=clients.get(a.client_id), snapshot_id=a.snapshot_id, code=a.code, title=a.title, detail=a.detail, severity=a.severity, metric=a.metric,
                      value=a.value, benchmark=a.benchmark, recommendation=a.recommendation, status=a.status, auto=a.auto, created_at=a.created_at)


def action_out(a: Action, names: dict, clients: dict) -> S.ActionOut:
    return S.ActionOut(id=a.id, client_id=a.client_id, client_name=clients.get(a.client_id), meeting_id=a.meeting_id, alert_id=a.alert_id, title=a.title, detail=a.detail, owner_side=a.owner_side,
                       owner_name=names.get(a.owner_membership_id) if a.owner_membership_id else a.owner_label, due_on=a.due_on,
                       overdue=bool(a.due_on and a.due_on < date.today() and a.status in ("open", "in_progress")), status=a.status, visible_to_client=a.visible_to_client,
                       completed_at=a.completed_at, task_id=a.task_id, created_at=a.created_at)


def meeting_out(db: Session, m: Meeting, names: dict, clients: dict) -> S.MeetingOut:
    n = db.execute(select(func.count()).select_from(Action).where(Action.meeting_id == m.id)).scalar_one()
    return S.MeetingOut(id=m.id, client_id=m.client_id, client_name=clients.get(m.client_id), snapshot_id=m.snapshot_id, title=m.title, kind=m.kind, scheduled_for=m.scheduled_for, status=m.status,
                        agenda=[S.AgendaItem(**a) for a in (m.agenda or [])], summary=m.summary,
                        prepared_by_name=names.get(m.prepared_by_membership_id) if m.prepared_by_membership_id else None, held_at=m.held_at, published_at=m.published_at, document_id=m.document_id,
                        action_count=n, created_at=m.created_at)


# ------------------------------------------------------------------ snapshots
def create_snapshot(db: Session, tenant: Tenant, body: S.SnapshotIn, actor_mid: uuid.UUID, actor_label: str) -> Snapshot:
    c = db.get(Client, body.client_id)
    if c is None:
        raise AdvisoryError("client_not_found")
    figures = {k: getattr(body, k) for k in ("revenue_cents", "gross_profit_cents", "expenses_cents", "net_profit_cents", "cash_cents", "receivables_cents", "payables_cents", "inventory_cents", "debt_cents", "equity_cents", "tax_provision_cents")}
    source, simulated, wp_id = "manual", False, None
    if body.workpaper_id:
        from app.modules.workpapers.models import LedgerConnection, Workpaper
        pack = db.get(Workpaper, body.workpaper_id)
        if pack is None or pack.client_id != c.id:
            raise AdvisoryError("workpaper_not_found")
        derived = from_workpaper(db, pack)
        for k, v in derived.items():
            if figures.get(k) is None:
                figures[k] = v
        conn = db.execute(select(LedgerConnection).where(LedgerConnection.client_id == c.id).order_by(LedgerConnection.created_at.desc())).scalars().first()
        source, simulated, wp_id = "workpapers", bool(conn.simulated) if conn else (pack.ledger_source == "simulation"), pack.id
    if all(v is None for v in figures.values()):
        raise AdvisoryError("no_figures", "Give some figures, or point at a workpaper that has been synced")
    s = Snapshot(tenant_id=tenant.id, client_id=c.id, as_at=body.as_at or date.today(), period_label=body.period_label, source=source, simulated=simulated, workpaper_id=wp_id, notes=body.notes,
                 created_by_membership_id=actor_mid, **figures)
    db.add(s)
    db.flush()
    s.kpis, s.health_score, s.health_band = compute_kpis(s)
    alerts = evaluate(db, s, c)
    db.flush()
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="advisory", kind="advisory.snapshot", summary=f"Advisory snapshot at {s.as_at:%d %b %Y}: health {s.health_score or '—'}/100, {len(alerts)} alert(s)",
                detail={"health_band": s.health_band, "kpis": s.kpis, "simulated": simulated}, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="advisory_snapshot", ref_id=s.id)
    action_alerts = [a for a in alerts if a.severity == "action"]
    if action_alerts:
        # the client's owner, or every principal when the client is unowned
        from app.models.identity import Membership
        targets = [c.owner_membership_id] if c.owner_membership_id else [m.id for m in db.execute(select(Membership).where(Membership.tenant_id == tenant.id, Membership.status == "active", Membership.role.in_(["owner", "admin"]))).scalars()]
        for mid in targets:
            notify_service.notify(db, tenant_id=tenant.id, membership_id=mid, kind="advisory.alert", title=f"{c.name}: {len(action_alerts)} item(s) need action",
                                  body="; ".join(a.title for a in action_alerts[:3]), link=f"/advisory/clients/{c.id}", module_key="advisory")
    return s


# ------------------------------------------------------------------ actions
def create_action(db: Session, tenant: Tenant, body: S.ActionIn, actor_mid: uuid.UUID, actor_label: str) -> Action:
    c = db.get(Client, body.client_id)
    if c is None:
        raise AdvisoryError("client_not_found")
    a = Action(tenant_id=tenant.id, client_id=c.id, meeting_id=body.meeting_id, alert_id=body.alert_id, title=body.title, detail=body.detail, owner_side=body.owner_side,
               owner_membership_id=body.owner_membership_id if body.owner_side == "practice" else None, owner_label=body.owner_label, due_on=body.due_on, visible_to_client=body.visible_to_client)
    db.add(a)
    db.flush()
    if body.alert_id:
        al = db.get(Alert, body.alert_id)
        if al is not None and al.status == "open":
            al.status = "actioned"
    # A practice-owned action is also a CRM task, so it shows up in the one place staff look.
    if a.owner_side == "practice":
        t = Task(tenant_id=tenant.id, client_id=c.id, title=a.title[:300], description=a.detail, due_at=None, priority="Normal", status="open",
                 assignee_membership_id=a.owner_membership_id, created_by_membership_id=actor_mid, module_key="advisory", ref_type="advisory_action", ref_id=str(a.id))
        db.add(t)
        db.flush()
        a.task_id = t.id
        events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="advisory", kind="task.created", summary=f"Advisory action: {a.title}", detail={"assignee_membership_id": str(a.owner_membership_id) if a.owner_membership_id else None},
                    actor_membership_id=actor_mid, actor_label=actor_label, ref_type="task", ref_id=t.id)
    return a


def patch_action(db: Session, a: Action, body: S.ActionPatch, actor_mid: uuid.UUID, actor_label: str) -> Action:
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(a, k, v)
    if data.get("status") == "done":
        a.completed_at = utcnow()
        if a.task_id:
            t = db.get(Task, a.task_id)
            if t is not None and t.status == "open":
                t.status, t.done_at = "done", utcnow()
        events.emit(db, tenant_id=a.tenant_id, client_id=a.client_id, module_key="advisory", kind="advisory.action_done", summary=f"Action completed: {a.title}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="advisory_action", ref_id=a.id)
    elif data.get("status") in ("open", "in_progress"):
        a.completed_at = None
    db.flush()
    return a


# ------------------------------------------------------------------ meetings
def create_meeting(db: Session, tenant: Tenant, body: S.MeetingIn, actor_mid: uuid.UUID, actor_label: str) -> Meeting:
    c = db.get(Client, body.client_id)
    if c is None:
        raise AdvisoryError("client_not_found")
    snap = db.get(Snapshot, body.snapshot_id) if body.snapshot_id else db.execute(select(Snapshot).where(Snapshot.client_id == c.id).order_by(Snapshot.as_at.desc())).scalars().first()
    title = body.title or f"{body.kind.title()} advisory meeting — {c.name}"
    m = Meeting(tenant_id=tenant.id, client_id=c.id, snapshot_id=snap.id if snap else None, title=title[:300], kind=body.kind, scheduled_for=body.scheduled_for or (date.today() + timedelta(days=14)),
                prepared_by_membership_id=actor_mid)
    db.add(m)
    db.flush()
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="advisory", kind="advisory.meeting_scheduled", summary=f"{m.title} scheduled for {m.scheduled_for:%d %b %Y}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="advisory_meeting", ref_id=m.id)
    return m


def prepare_meeting(db: Session, m: Meeting, actor_mid: uuid.UUID, actor_label: str) -> Meeting:
    """Build the agenda from the numbers: open alerts, outstanding actions, and the standing items."""
    if m.status in ("held", "published", "cancelled"):
        raise AdvisoryError("wrong_state", f"The meeting is {m.status}")
    snap = db.get(Snapshot, m.snapshot_id) if m.snapshot_id else db.execute(select(Snapshot).where(Snapshot.client_id == m.client_id).order_by(Snapshot.as_at.desc())).scalars().first()
    agenda: list[dict[str, Any]] = []
    if snap:
        m.snapshot_id = snap.id
        k = snap.kpis or {}
        bits = [f"{name} {k[key]}{suffix}" for key, name, suffix in (("net_margin_pct", "net margin", "%"), ("current_ratio", "current ratio", ""), ("cash_runway_months", "cash runway", " months"), ("debtor_days", "debtor days", "")) if key in k]
        agenda.append({"title": "Where the business is", "note": f"As at {snap.as_at:%d %b %Y}: " + (", ".join(bits) if bits else "figures on file") + (f" · health {snap.health_score}/100 ({snap.health_band})" if snap.health_score else "") + (" · figures from a simulated ledger" if snap.simulated else ""), "source": "kpi", "source_ref": str(snap.id), "decision": None})
    for a in db.execute(select(Alert).where(Alert.client_id == m.client_id, Alert.status == "open").order_by(Alert.severity.desc(), Alert.created_at)).scalars():
        agenda.append({"title": a.title, "note": (a.detail or "") + (f"\n\nSuggested: {a.recommendation}" if a.recommendation else ""), "source": "alert", "source_ref": str(a.id), "decision": None})
    carried = db.execute(select(Action).where(Action.client_id == m.client_id, Action.status.in_(["open", "in_progress"]))).scalars().all()
    if carried:
        agenda.append({"title": "Actions carried forward", "note": "\n".join(f"• {a.title} ({a.owner_label or a.owner_side}{', due ' + a.due_on.strftime('%d %b') if a.due_on else ''})" for a in carried), "source": "action", "source_ref": None, "decision": None})
    agenda.append({"title": "Next period — decisions and commitments", "note": None, "source": "manual", "source_ref": None, "decision": None})
    m.agenda = agenda
    m.status = "prepared"
    db.flush()
    return m


def hold_meeting(db: Session, tenant: Tenant, m: Meeting, body: S.HoldIn, actor_mid: uuid.UUID, actor_label: str) -> Meeting:
    if m.status in ("held", "published"):
        raise AdvisoryError("already_held")
    agenda = [dict(a) for a in (m.agenda or [])]
    for a in agenda:
        if a["title"] in body.decisions:
            a["decision"] = body.decisions[a["title"]]
    m.agenda, m.summary, m.status, m.held_at = agenda, body.summary, "held", utcnow()
    for spec in body.actions:
        create_action(db, tenant, S.ActionIn(**{**spec.model_dump(), "client_id": m.client_id, "meeting_id": m.id}), actor_mid, actor_label)
    db.flush()
    events.emit(db, tenant_id=tenant.id, client_id=m.client_id, module_key="advisory", kind="advisory.meeting_held", summary=f"{m.title} held — {len(body.actions)} action(s) agreed", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="advisory_meeting", ref_id=m.id)
    return m


def publish_meeting(db: Session, tenant: Tenant, m: Meeting, actor_mid: uuid.UUID, actor_label: str) -> Meeting:
    if m.status not in ("held", "published"):
        raise AdvisoryError("not_held", "Hold the meeting before publishing the summary")
    m.status, m.published_at = "published", utcnow()
    try:
        entitlements.check(db, tenant, "client")
        from app.modules.client import service as portal_svc
        c = db.get(Client, m.client_id)
        lines = [m.summary or ""]
        acts = db.execute(select(Action).where(Action.meeting_id == m.id, Action.visible_to_client.is_(True))).scalars().all()
        if acts:
            lines.append("\nAgreed actions:\n" + "\n".join(f"• {a.title} — {a.owner_label or ('us' if a.owner_side == 'practice' else 'you')}{', by ' + a.due_on.strftime('%d %b') if a.due_on else ''}" for a in acts))
        portal_svc.post_from_staff(db, tenant, c, f"{m.title}\n\n" + "\n".join(x for x in lines if x), actor_mid, actor_label)
    except entitlements.NotEntitled:
        pass
    events.emit(db, tenant_id=tenant.id, client_id=m.client_id, module_key="advisory", kind="advisory.meeting_published", summary=f"{m.title} summary published to the client", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="advisory_meeting", ref_id=m.id)
    db.flush()
    return m


# ------------------------------------------------------------------ views
def client_view(db: Session, client: Client) -> S.ClientAdvisoryOut:
    names = member_names(db, set())
    clients = {client.id: client.name}
    snaps = db.execute(select(Snapshot).where(Snapshot.client_id == client.id).order_by(Snapshot.as_at.desc())).scalars().all()
    names = member_names(db, {s.created_by_membership_id for s in snaps})
    alerts = db.execute(select(Alert).where(Alert.client_id == client.id).order_by(Alert.status, Alert.severity.desc(), Alert.created_at.desc())).scalars().all()
    actions = db.execute(select(Action).where(Action.client_id == client.id).order_by(Action.status, Action.due_on.is_(None), Action.due_on)).scalars().all()
    anames = member_names(db, {a.owner_membership_id for a in actions})
    meetings = db.execute(select(Meeting).where(Meeting.client_id == client.id).order_by(Meeting.scheduled_for.desc())).scalars().all()
    mnames = member_names(db, {m.prepared_by_membership_id for m in meetings})
    return S.ClientAdvisoryOut(client_id=client.id, client_name=client.name, latest=snapshot_out(snaps[0], names, clients) if snaps else None,
                               history=[snapshot_out(s, names, clients) for s in snaps[:12]], alerts=[alert_out(a, clients) for a in alerts],
                               actions=[action_out(a, anames, clients) for a in actions], meetings=[meeting_out(db, m, mnames, clients) for m in meetings])


def overview(db: Session) -> S.OverviewOut:
    snaps = db.execute(select(Snapshot)).scalars().all()
    alerts = db.execute(select(Alert).where(Alert.status == "open")).scalars().all()
    actions = db.execute(select(Action).where(Action.status.in_(["open", "in_progress"]))).scalars().all()
    meetings = db.execute(select(Meeting)).scalars().all()
    today = date.today()
    latest: dict[uuid.UUID, Snapshot] = {}
    for s in sorted(snaps, key=lambda x: x.as_at):
        latest[s.client_id] = s
    clients = client_name_map(db, set(latest) | {a.client_id for a in alerts})
    scores = [s.health_score for s in latest.values() if s.health_score is not None]
    attention = []
    for cid, s in sorted(latest.items(), key=lambda kv: (kv[1].health_score if kv[1].health_score is not None else 101)):
        ca = [a for a in alerts if a.client_id == cid]
        if s.health_band == "needs_action" or any(a.severity == "action" for a in ca):
            attention.append({"client_id": str(cid), "client_name": clients.get(cid), "health_score": s.health_score, "health_band": s.health_band,
                              "alerts": [a.title for a in ca if a.severity == "action"][:3], "as_at": s.as_at.isoformat()})
    return S.OverviewOut(clients_with_snapshots=len(latest), open_alerts=len(alerts), action_alerts=sum(1 for a in alerts if a.severity == "action"), open_actions=len(actions),
                         overdue_actions=sum(1 for a in actions if a.due_on and a.due_on < today), meetings_scheduled=sum(1 for m in meetings if m.status in ("scheduled", "prepared")),
                         meetings_held_90d=sum(1 for m in meetings if m.held_at and m.held_at >= utcnow() - timedelta(days=90)),
                         avg_health_score=round(sum(scores) / len(scores)) if scores else None, attention=attention[:8])
