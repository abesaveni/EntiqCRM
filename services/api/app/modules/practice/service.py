from __future__ import annotations

import calendar
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import events
from app.core.security import utcnow
from app.models.crm import Client
from app.models.identity import Membership
from app.modules.practice import schemas as S
from app.modules.practice.models import FREQUENCIES, JOB_TYPES, OPEN_STATUSES, Job, RecurringJob, TimeEntry
from app.services import notify_service
from app.services.crm_service import client_name_map, member_names

# ------------------------------------------------------------------ Australian financial-year periods
FY_START_MONTH = 7


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def fy_label(end: date) -> str:
    """Australian FY named by the year it ends in: Jul 2026–Jun 2027 = FY27."""
    fy = end.year + (1 if end.month >= FY_START_MONTH else 0)
    return f"FY{str(fy)[2:]}"


def period_for(frequency: str, on: date) -> tuple[date, date, str]:
    """The period containing `on`: (start, end, label)."""
    if frequency == "monthly":
        start = on.replace(day=1)
        end = _add_months(start, 1) - timedelta(days=1)
        return start, end, start.strftime("%b %Y")
    if frequency == "quarterly":
        # FY quarters: Q1 Jul–Sep, Q2 Oct–Dec, Q3 Jan–Mar, Q4 Apr–Jun
        q_start_month = ((((on.month - FY_START_MONTH) % 12) // 3 * 3 + FY_START_MONTH - 1) % 12) + 1
        year = on.year if q_start_month <= on.month else on.year - 1
        start = date(year, q_start_month, 1)
        end = _add_months(start, 3) - timedelta(days=1)
        qn = ((start.month - FY_START_MONTH) % 12) // 3 + 1
        return start, end, f"Q{qn} {fy_label(end)}"
    if frequency == "biannual":
        first_half = FY_START_MONTH <= on.month <= 12
        start = date(on.year, FY_START_MONTH, 1) if first_half else date(on.year, 1, 1)
        end = _add_months(start, 6) - timedelta(days=1)
        return start, end, f"H{1 if first_half else 2} {fy_label(end)}"
    # annual
    start = date(on.year if on.month >= FY_START_MONTH else on.year - 1, FY_START_MONTH, 1)
    end = _add_months(start, 12) - timedelta(days=1)
    return start, end, fy_label(end)


def next_period_after(frequency: str, end: date) -> tuple[date, date, str]:
    return period_for(frequency, end + timedelta(days=1))


def due_for(r: RecurringJob, period_end: date) -> date:
    target = _add_months(period_end.replace(day=1), r.month_offset)
    return target.replace(day=min(r.day_of_month, calendar.monthrange(target.year, target.month)[1]))


# ------------------------------------------------------------------ statutory calendar (ATO/ASIC standard dates; agent concessions differ)
def statutory_deadlines(frm: date, to: date) -> list[S.DeadlineOut]:
    out: list[S.DeadlineOut] = []
    y = frm.year - 1
    while y <= to.year:
        for m, d, label, detail in [
            (10, 28, "Quarterly BAS Q1 due", "Jul–Sep activity statement (standard date)"),
            (2, 28, "Quarterly BAS Q2 due", "Oct–Dec activity statement"),
            (4, 28, "Quarterly BAS Q3 due", "Jan–Mar activity statement"),
            (7, 28, "Quarterly BAS Q4 due", "Apr–Jun activity statement"),
            (5, 15, "Tax returns due (tax agent program)", "Individuals, trusts, partnerships and most companies on the agent lodgement program"),
            (5, 21, "FBT return due", "Fringe benefits tax year ended 31 March (paper); 25 June if lodged electronically by an agent"),
            (10, 31, "Tax returns due (self-preparers)", "Individuals not using a tax agent"),
            (7, 14, "STP finalisation due", "Single Touch Payroll end-of-year finalisation"),
            (8, 28, "Taxable payments annual report due", "Contractors in building, cleaning, courier, IT, security"),
        ]:
            dt = date(y, m, d)
            if frm <= dt <= to:
                out.append(S.DeadlineOut(on=dt, kind="statutory", label=label, detail=detail, overdue=dt < date.today()))
        # monthly IAS/BAS: 21st of the following month
        for m in range(1, 13):
            dt = date(y, m, 21)
            if frm <= dt <= to:
                out.append(S.DeadlineOut(on=dt, kind="statutory", label="Monthly activity statement due", detail="For the previous month", overdue=dt < date.today()))
        y += 1
    return sorted(out, key=lambda x: x.on)


# ------------------------------------------------------------------ serialisers
def job_out(j: Job, names: dict, clients: dict, minutes: dict[uuid.UUID, int] | None = None) -> S.JobOut:
    today = date.today()
    return S.JobOut(id=j.id, client_id=j.client_id, client_name=clients.get(j.client_id), title=j.title, job_type=j.job_type, period_label=j.period_label, period_start=j.period_start,
                    period_end=j.period_end, due_on=j.due_on, lodgement_due=j.lodgement_due, status=j.status, priority=j.priority, assignee_membership_id=j.assignee_membership_id,
                    assignee_name=names.get(j.assignee_membership_id) if j.assignee_membership_id else None, reviewer_name=names.get(j.reviewer_membership_id) if j.reviewer_membership_id else None,
                    budget_minutes=j.budget_minutes, actual_minutes=(minutes or {}).get(j.id, 0), fee_cents=j.fee_cents, recurring_job_id=j.recurring_job_id, source=j.source,
                    checklist=[S.ChecklistItem(**c) for c in (j.checklist or [])], notes=j.notes, overdue=j.status in OPEN_STATUSES and bool(j.due_on and j.due_on < today),
                    started_at=j.started_at, completed_at=j.completed_at, created_at=j.created_at)


def jobs_out(db: Session, rows: list[Job]) -> list[S.JobOut]:
    if not rows:
        return []
    names = member_names(db, {j.assignee_membership_id for j in rows} | {j.reviewer_membership_id for j in rows})
    clients = client_name_map(db, {j.client_id for j in rows})
    mins = dict(db.execute(select(TimeEntry.job_id, func.coalesce(func.sum(TimeEntry.minutes), 0)).where(TimeEntry.job_id.in_([j.id for j in rows])).group_by(TimeEntry.job_id)).all())
    return [job_out(j, names, clients, mins) for j in rows]


def recurring_out(r: RecurringJob, names: dict, clients: dict) -> S.RecurringOut:
    return S.RecurringOut(id=r.id, client_id=r.client_id, client_name=clients.get(r.client_id), name_template=r.name_template, job_type=r.job_type, frequency=r.frequency, month_offset=r.month_offset,
                          day_of_month=r.day_of_month, advance_days=r.advance_days, assignee_name=names.get(r.assignee_membership_id) if r.assignee_membership_id else None, budget_minutes=r.budget_minutes,
                          fee_cents=r.fee_cents, is_active=r.is_active, last_period_label=r.last_period_label, next_due_on=r.next_due_on, notes=r.notes, created_at=r.created_at)


# ------------------------------------------------------------------ jobs
DEFAULT_CHECKLISTS: dict[str, list[str]] = {
    "BAS": ["Bank reconciliation complete", "GST coding reviewed", "PAYG withholding reconciled", "Client approval", "Lodged"],
    "IAS": ["Payroll reconciled", "PAYG instalment confirmed", "Lodged"],
    "Tax Return": ["Source documents received", "Workpapers prepared", "Reviewed", "Client signed declaration", "Lodged"],
    "Financial Statements": ["Trial balance agreed", "Adjusting journals posted", "Notes drafted", "Reviewed", "Signed"],
    "FBT": ["Benefits schedule received", "Calculations reviewed", "Lodged"],
    "ASIC": ["Annual statement received", "Solvency resolution signed", "Fee paid"],
    "Onboarding": ["Engagement letter on file", "Ledger access granted", "Opening balances loaded", "Recurring work scheduled"],
}


def create_job(db: Session, tenant_id: uuid.UUID, body: S.JobIn, actor_mid: uuid.UUID | None, actor_label: str, *, source: str = "manual", recurring_id: uuid.UUID | None = None) -> Job:
    if db.get(Client, body.client_id) is None:
        raise ValueError("client not found")
    if body.job_type not in JOB_TYPES:
        raise ValueError(f"job_type must be one of {', '.join(JOB_TYPES)}")
    checklist = [c.model_dump() for c in body.checklist] if body.checklist is not None else [{"key": f"c{i}", "label": l, "done": False} for i, l in enumerate(DEFAULT_CHECKLISTS.get(body.job_type, []), 1)]
    j = Job(tenant_id=tenant_id, client_id=body.client_id, title=body.title.strip(), job_type=body.job_type, period_label=body.period_label, period_start=body.period_start, period_end=body.period_end,
            due_on=body.due_on, lodgement_due=body.lodgement_due, priority=body.priority, assignee_membership_id=body.assignee_membership_id, reviewer_membership_id=body.reviewer_membership_id,
            budget_minutes=body.budget_minutes, fee_cents=body.fee_cents, checklist=checklist, notes=body.notes, created_by_membership_id=actor_mid, source=source, recurring_job_id=recurring_id)
    db.add(j)
    db.flush()
    events.emit(db, tenant_id=tenant_id, client_id=j.client_id, module_key="practice", kind="job.created", summary=f"Job opened: {j.title}" + (f" · due {j.due_on:%d %b %Y}" if j.due_on else ""),
                detail={"job_type": j.job_type, "source": source}, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="job", ref_id=j.id)
    if j.assignee_membership_id and j.assignee_membership_id != actor_mid:
        notify_service.notify(db, tenant_id=tenant_id, membership_id=j.assignee_membership_id, kind="job.assigned", title=f"Job assigned: {j.title}", body=f"Due {j.due_on:%d %b %Y}" if j.due_on else None, link=f"/practice/jobs/{j.id}", module_key="practice")
    return j


def patch_job(db: Session, j: Job, body: S.JobPatch, actor_mid: uuid.UUID | None, actor_label: str) -> Job:
    data = body.model_dump(exclude_unset=True)
    if "checklist" in data and data["checklist"] is not None:
        data["checklist"] = [c if isinstance(c, dict) else c.model_dump() for c in data["checklist"]]
    if "job_type" in data and data["job_type"] not in JOB_TYPES:
        raise ValueError("invalid job_type")
    old_assignee = j.assignee_membership_id
    for k, v in data.items():
        setattr(j, k, v)
    db.flush()
    if "assignee_membership_id" in data and j.assignee_membership_id and j.assignee_membership_id != old_assignee and j.assignee_membership_id != actor_mid:
        notify_service.notify(db, tenant_id=j.tenant_id, membership_id=j.assignee_membership_id, kind="job.assigned", title=f"Job assigned: {j.title}", link=f"/practice/jobs/{j.id}", module_key="practice")
    return j


def set_status(db: Session, j: Job, status: str, note: str | None, actor_mid: uuid.UUID | None, actor_label: str) -> Job:
    if status == j.status:
        return j
    old, now = j.status, utcnow()
    j.status = status
    if status == "in_progress" and j.started_at is None:
        j.started_at = now
    if status == "complete":
        j.completed_at = now
    elif old == "complete":
        j.completed_at = None
    events.emit(db, tenant_id=j.tenant_id, client_id=j.client_id, module_key="practice", kind="job.completed" if status == "complete" else "job.status", summary=f"{j.title}: {old.replace('_', ' ')} → {status.replace('_', ' ')}" + (f" — {note}" if note else ""),
                detail={"from": old, "to": status}, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="job", ref_id=j.id)
    if status == "review" and j.reviewer_membership_id and j.reviewer_membership_id != actor_mid:
        notify_service.notify(db, tenant_id=j.tenant_id, membership_id=j.reviewer_membership_id, kind="job.review", title=f"Ready for review: {j.title}", link=f"/practice/jobs/{j.id}", module_key="practice")
    return j


def add_time(db: Session, j: Job, body: S.TimeIn, membership_id: uuid.UUID) -> TimeEntry:
    t = TimeEntry(tenant_id=j.tenant_id, job_id=j.id, membership_id=membership_id, worked_on=body.worked_on, minutes=body.minutes, billable=body.billable, note=body.note)
    db.add(t)
    if j.status == "not_started":
        j.status, j.started_at = "in_progress", utcnow()
    db.flush()
    return t


def time_out(db: Session, rows: list[TimeEntry]) -> list[S.TimeOut]:
    names = member_names(db, {t.membership_id for t in rows})
    return [S.TimeOut(id=t.id, job_id=t.job_id, membership_id=t.membership_id, member_name=names.get(t.membership_id), worked_on=t.worked_on, minutes=t.minutes, billable=t.billable, note=t.note, created_at=t.created_at) for t in rows]


# ------------------------------------------------------------------ recurring
def create_recurring(db: Session, tenant_id: uuid.UUID, body: S.RecurringIn, actor_mid: uuid.UUID | None, actor_label: str, today: date | None = None) -> RecurringJob:
    if db.get(Client, body.client_id) is None:
        raise ValueError("client not found")
    if body.job_type not in JOB_TYPES or body.frequency not in FREQUENCIES:
        raise ValueError("invalid job_type or frequency")
    r = RecurringJob(tenant_id=tenant_id, client_id=body.client_id, name_template=body.name_template, job_type=body.job_type, frequency=body.frequency, month_offset=body.month_offset, day_of_month=body.day_of_month,
                     advance_days=body.advance_days, assignee_membership_id=body.assignee_membership_id, budget_minutes=body.budget_minutes, fee_cents=body.fee_cents, notes=body.notes, created_by_membership_id=actor_mid)
    today = today or date.today()
    # next due = due date of the current period (or the next one if that has already passed)
    _, end, _ = period_for(r.frequency, today)
    due = due_for(r, end)
    while due < today:
        _, end, _ = next_period_after(r.frequency, end)
        due = due_for(r, end)
    r.next_due_on = due
    db.add(r)
    db.flush()
    events.emit(db, tenant_id=tenant_id, client_id=r.client_id, module_key="practice", kind="recurring.created", summary=f"Recurring {r.job_type} scheduled ({r.frequency})", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="recurring_job", ref_id=r.id)
    return r


def _period_for_due(r: RecurringJob, due: date) -> tuple[date, date, str]:
    """The period whose due date is `due` (walk back from the due date by the offset)."""
    probe = _add_months(due.replace(day=1), -r.month_offset)
    return period_for(r.frequency, probe if r.month_offset > 0 else due)


def generate_recurring(db: Session, tenant_id: uuid.UUID, today: date | None = None) -> int:
    """Create the next job for each active schedule whose due date is within `advance_days`. Idempotent per period."""
    today = today or date.today()
    created = 0
    rows = db.execute(select(RecurringJob).where(RecurringJob.tenant_id == tenant_id, RecurringJob.is_active.is_(True), RecurringJob.next_due_on.is_not(None))).scalars().all()
    for r in rows:
        guard = 0
        while r.next_due_on and r.next_due_on - timedelta(days=r.advance_days) <= today and guard < 12:
            guard += 1
            start, end, label = _period_for_due(r, r.next_due_on)
            exists = db.execute(select(func.count()).select_from(Job).where(Job.recurring_job_id == r.id, Job.period_label == label)).scalar_one()
            if not exists:
                title = r.name_template.replace("{type}", r.job_type).replace("{period}", label)
                body = S.JobIn(client_id=r.client_id, title=title, job_type=r.job_type, period_label=label, period_start=start, period_end=end, due_on=r.next_due_on, lodgement_due=r.next_due_on,
                               assignee_membership_id=r.assignee_membership_id, budget_minutes=r.budget_minutes, fee_cents=r.fee_cents, notes=r.notes)
                create_job(db, tenant_id, body, None, "EnTIQ Practice", source="recurring", recurring_id=r.id)
                created += 1
            r.last_period_label = label
            _, nend, _ = next_period_after(r.frequency, end)
            r.next_due_on = due_for(r, nend)
    db.flush()
    return created


# ------------------------------------------------------------------ views
def deadlines(db: Session, days: int = 90) -> list[S.DeadlineOut]:
    today = date.today()
    to = today + timedelta(days=days)
    rows = db.execute(select(Job).where(Job.status.in_(OPEN_STATUSES), Job.due_on.is_not(None), Job.due_on <= to).order_by(Job.due_on)).scalars().all()
    clients = client_name_map(db, {j.client_id for j in rows})
    out = [S.DeadlineOut(on=j.due_on, kind="job", label=j.title, job_id=j.id, client_id=j.client_id, client_name=clients.get(j.client_id), overdue=j.due_on < today, detail=f"{j.job_type}{' · lodgement ' + j.lodgement_due.strftime('%d %b') if j.lodgement_due and j.lodgement_due != j.due_on else ''}") for j in rows]
    return sorted(out + statutory_deadlines(today, to), key=lambda x: (x.on, x.kind))


def team(db: Session, tenant_id: uuid.UUID) -> list[S.TeamMember]:
    members = db.execute(select(Membership).where(Membership.tenant_id == tenant_id, Membership.status == "active")).scalars().all()
    names = member_names(db, {m.id for m in members})
    today = date.today()
    month_start = today.replace(day=1)
    out = []
    for m in members:
        open_jobs = db.execute(select(Job).where(Job.assignee_membership_id == m.id, Job.status.in_(OPEN_STATUSES))).scalars().all()
        mins = db.execute(select(func.coalesce(func.sum(TimeEntry.minutes), 0)).where(TimeEntry.membership_id == m.id, TimeEntry.worked_on >= month_start)).scalar_one()
        out.append(S.TeamMember(membership_id=m.id, name=names.get(m.id, "—"), role=m.role, open_jobs=len(open_jobs), overdue_jobs=sum(1 for j in open_jobs if j.due_on and j.due_on < today),
                                minutes_this_month=int(mins), budget_minutes_open=sum(j.budget_minutes or 0 for j in open_jobs)))
    return sorted(out, key=lambda x: (-x.open_jobs, x.name))


def overview(db: Session, tenant_id: uuid.UUID) -> S.OverviewOut:
    today = date.today()
    open_rows = db.execute(select(Job).where(Job.status.in_(OPEN_STATUSES))).scalars().all()
    by_type: dict[str, int] = {}
    for j in open_rows:
        by_type[j.job_type] = by_type.get(j.job_type, 0) + 1
    completed = db.execute(select(func.count()).select_from(Job).where(Job.status == "complete", Job.completed_at >= utcnow() - timedelta(days=30))).scalar_one()
    mins = db.execute(select(func.coalesce(func.sum(TimeEntry.minutes), 0)).where(TimeEntry.worked_on >= today.replace(day=1))).scalar_one()
    rec = db.execute(select(func.count()).select_from(RecurringJob).where(RecurringJob.is_active.is_(True))).scalar_one()
    return S.OverviewOut(open_jobs=len(open_rows), overdue=sum(1 for j in open_rows if j.due_on and j.due_on < today), due_7d=sum(1 for j in open_rows if j.due_on and today <= j.due_on <= today + timedelta(days=7)),
                         unassigned=sum(1 for j in open_rows if not j.assignee_membership_id), waiting_client=sum(1 for j in open_rows if j.status == "waiting_client"), in_review=sum(1 for j in open_rows if j.status == "review"),
                         completed_30d=completed, by_type=dict(sorted(by_type.items(), key=lambda kv: -kv[1])), minutes_this_month=int(mins), recurring_active=rec, upcoming=deadlines(db, 21)[:8])


# ------------------------------------------------------------------ interlink: Start → Practice
SERVICE_TO_JOB: dict[str, tuple[str, str | None]] = {
    # service category → (job_type, recurring frequency or None for one-off)
    "bas": ("BAS", "quarterly"), "ias": ("IAS", "monthly"), "tax": ("Tax Return", "annual"), "financials": ("Financial Statements", "annual"),
    "bookkeeping": ("Bookkeeping", "monthly"), "payroll": ("Payroll", "monthly"), "asic": ("ASIC", "annual"), "fbt": ("FBT", "annual"), "advisory": ("Advisory", "quarterly"), "smsf": ("Financial Statements", "annual"),
}


def on_onboarding_activated(db: Session, ev) -> None:
    """When Start activates a client, schedule the recurring work implied by the services they selected, plus an onboarding job."""
    from app.core import entitlements
    from app.models.tenant import Tenant
    t = db.get(Tenant, ev.tenant_id)
    try:
        entitlements.check(db, t, "practice")
    except entitlements.NotEntitled:
        return
    if not ev.client_id:
        return
    owner = (ev.detail or {}).get("owner_membership_id")
    owner_id = uuid.UUID(owner) if owner else None
    create_job(db, ev.tenant_id, S.JobIn(client_id=ev.client_id, title="Client onboarding — set-up", job_type="Onboarding", due_on=date.today() + timedelta(days=14), assignee_membership_id=owner_id), None, "EnTIQ Start", source="onboarding")
    for svc in (ev.detail or {}).get("services", []):
        job_type, freq = SERVICE_TO_JOB.get(str(svc.get("category", "")).lower(), ("Other", None))
        if freq:
            create_recurring(db, ev.tenant_id, S.RecurringIn(client_id=ev.client_id, name_template="{type} {period}", job_type=job_type, frequency=freq, assignee_membership_id=owner_id, fee_cents=svc.get("amount_cents")), None, "EnTIQ Start")


def register() -> None:
    events.subscribe("onboarding.activated", on_onboarding_activated)
