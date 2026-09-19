from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import entitlements, events
from app.core.security import utcnow
from app.models.crm import Client, Contact
from app.models.tenant import Tenant
from app.modules.lending import schemas as S
from app.modules.lending.models import STAGES, TERMINAL, Application, ApplicationEvent, Condition
from app.services import billing_service, notify_service
from app.services.crm_service import client_name_map, member_names


class LendingError(Exception):
    def __init__(self, error: str, message: str | None = None):
        super().__init__(message or error)
        self.error, self.message = error, message or error


def _ref(db: Session) -> str:
    from app.core.tenancy import platform_scope
    with platform_scope():
        n = db.execute(select(func.count()).select_from(Application)).scalar_one()
    return f"FIN-{date.today():%Y}-{1000 + n + 1}"


def _log(db: Session, a: Application, kind: str, actor_label: str, *, from_stage: str | None = None, to_stage: str | None = None, note: str | None = None) -> None:
    db.add(ApplicationEvent(tenant_id=a.tenant_id, application_id=a.id, kind=kind, from_stage=from_stage, to_stage=to_stage, note=note, actor_label=actor_label[:120], at=utcnow()))


# ------------------------------------------------------------------ serialisers
def condition_out(c: Condition, names: dict) -> S.ConditionOut:
    return S.ConditionOut(id=c.id, title=c.title, detail=c.detail, kind=c.kind, owner_side=c.owner_side, due_on=c.due_on,
                          overdue=bool(c.due_on and c.due_on < date.today() and c.status == "open"), status=c.status, document_id=c.document_id, note=c.note,
                          satisfied_at=c.satisfied_at, satisfied_by_name=names.get(c.satisfied_by_membership_id) if c.satisfied_by_membership_id else None)


def _dscr(a: Application) -> float | None:
    s = a.serviceability or {}
    ebitda = s.get("ebitda_cents")
    total = (s.get("existing_repayments_cents") or 0) + (s.get("proposed_repayment_cents") or a.repayment_cents or 0)
    if not ebitda or not total:
        return None
    return round(ebitda / total, 2)


def application_out(db: Session, a: Application, names: dict | None = None, clients: dict | None = None) -> S.ApplicationOut:
    names = names if names is not None else member_names(db, {a.owner_membership_id})
    clients = clients if clients is not None else client_name_map(db, {a.client_id})
    ct = db.get(Contact, a.contact_id) if a.contact_id else None
    return S.ApplicationOut(id=a.id, client_id=a.client_id, client_name=clients.get(a.client_id), contact_name=ct.full_name if ct else None, reference=a.reference, purpose=a.purpose, description=a.description,
                            amount_cents=a.amount_cents, term_months=a.term_months, rate_bps=a.rate_bps, repayment_cents=a.repayment_cents, lender=a.lender, stage=a.stage,
                            stage_index=STAGES.index(a.stage) if a.stage in STAGES else -1, owner_name=names.get(a.owner_membership_id) if a.owner_membership_id else None,
                            request_pack_id=a.request_pack_id, readiness_pct=a.readiness_pct, serviceability=a.serviceability or {}, dscr=_dscr(a), decision_note=a.decision_note,
                            submitted_at=a.submitted_at, approved_at=a.approved_at, settled_at=a.settled_at, settlement_date=a.settlement_date, expected_settlement=a.expected_settlement,
                            closed_at=a.closed_at, close_reason=a.close_reason, conditions_open=sum(1 for c in a.conditions if c.status == "open"),
                            conditions_blocking=sum(1 for c in a.conditions if c.status == "open" and c.kind == "precedent"), created_at=a.created_at, updated_at=a.updated_at)


def detail(db: Session, a: Application) -> S.ApplicationDetail:
    base = application_out(db, a)
    names = member_names(db, {c.satisfied_by_membership_id for c in a.conditions})
    outstanding: list[str] = []
    request_status = None
    if a.request_pack_id:
        from app.modules.requests.models import RequestPack
        from app.modules.requests import service as req_svc
        pack = db.get(RequestPack, a.request_pack_id)
        if pack is not None:
            request_status = pack.status
            outstanding = req_svc.outstanding(pack)
    return S.ApplicationDetail(**base.model_dump(), conditions=[condition_out(c, names) for c in a.conditions],
                               events=[S.EventOut(id=e.id, kind=e.kind, from_stage=e.from_stage, to_stage=e.to_stage, note=e.note, actor_label=e.actor_label, at=e.at) for e in a.events],
                               documents_outstanding=outstanding, request_status=request_status)


# ------------------------------------------------------------------ lifecycle
def create(db: Session, tenant: Tenant, body: S.ApplicationIn, actor_mid: uuid.UUID, actor_label: str) -> Application:
    c = db.get(Client, body.client_id)
    if c is None:
        raise LendingError("client_not_found")
    a = Application(tenant_id=tenant.id, client_id=c.id, contact_id=body.contact_id, reference=_ref(db), purpose=body.purpose, description=body.description, amount_cents=body.amount_cents,
                    term_months=body.term_months, rate_bps=body.rate_bps, lender=body.lender, owner_membership_id=body.owner_membership_id or actor_mid, expected_settlement=body.expected_settlement)
    db.add(a)
    db.flush()
    _log(db, a, "created", actor_label, to_stage="enquiry", note=f"{_money(a.amount_cents)} for {a.purpose.replace('_', ' ')}")
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="lending", kind="lending.created", summary=f"Finance enquiry {a.reference}: {_money(a.amount_cents)} for {a.purpose.replace('_', ' ')}",
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="lending_application", ref_id=a.id)
    if body.send_request:
        open_request(db, tenant, a, actor_mid, actor_label)
    _recompute_readiness(db, a)
    return a


def open_request(db: Session, tenant: Tenant, a: Application, actor_mid: uuid.UUID, actor_label: str) -> uuid.UUID | None:
    """Collect the lending checklist through the Requests module, if the practice has it."""
    try:
        entitlements.check(db, tenant, "requests")
    except entitlements.NotEntitled:
        return None
    from app.modules.requests import schemas as RS
    from app.modules.requests import service as req_svc
    pack, _url = req_svc.create(db, tenant, RS.PackIn(client_id=a.client_id, contact_id=a.contact_id, purpose="lending", title=f"Finance application {a.reference} — information needed",
                                                      message=f"For your {_money(a.amount_cents)} {a.purpose.replace('_', ' ')} finance application.", due_in_days=10, send_now=True), actor_mid, actor_label)
    a.request_pack_id = pack.id
    if a.stage == "enquiry":
        set_stage(db, tenant, a, "information", "Information request sent", actor_mid, actor_label)
    db.flush()
    return pack.id


def _recompute_readiness(db: Session, a: Application) -> int:
    """Readiness: documents in, serviceability computed, lender chosen, conditions cleared."""
    score = 0
    if a.amount_cents and a.term_months:
        score += 10
    if a.request_pack_id:
        from app.modules.requests.models import RequestPack
        pack = db.get(RequestPack, a.request_pack_id)
        if pack is not None:
            total = max(1, len([i for i in pack.items if i.required]))
            done = len([i for i in pack.items if i.required and i.status in ("accepted", "not_applicable")])
            score += round(done / total * 45)
    if _dscr(a) is not None:
        score += 20
    if a.lender:
        score += 10
    if a.stage in ("approved", "conditions", "settled"):
        score += 15
    if a.conditions:
        open_prec = sum(1 for c in a.conditions if c.status == "open" and c.kind == "precedent")
        if open_prec == 0:
            score += 10
    a.readiness_pct = max(0, min(100, score))
    return a.readiness_pct


def patch(db: Session, a: Application, body: S.ApplicationPatch) -> Application:
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    _recompute_readiness(db, a)
    db.flush()
    return a


def assess(db: Session, a: Application, body: S.ServiceabilityIn, actor_label: str) -> Application:
    s = dict(a.serviceability or {})
    if body.use_snapshot and body.ebitda_cents is None:
        from app.modules.advisory.models import Snapshot
        snap = db.execute(select(Snapshot).where(Snapshot.client_id == a.client_id).order_by(Snapshot.as_at.desc())).scalars().first()
        if snap is not None and snap.net_profit_cents is not None:
            s["ebitda_cents"] = snap.net_profit_cents
            s["ebitda_source"] = f"Advisory snapshot {snap.as_at:%d %b %Y}" + (" (simulated ledger)" if snap.simulated else "")
    for k in ("ebitda_cents", "existing_repayments_cents", "proposed_repayment_cents"):
        v = getattr(body, k)
        if v is not None:
            s[k] = v
            s.pop("ebitda_source", None) if k == "ebitda_cents" else None
    if body.notes:
        s["notes"] = body.notes
    if s.get("proposed_repayment_cents"):
        a.repayment_cents = s["proposed_repayment_cents"]
    elif a.repayment_cents is None and a.term_months and a.rate_bps is not None:
        a.repayment_cents = _repayment(a.amount_cents, a.rate_bps, a.term_months)
        s["proposed_repayment_cents"] = a.repayment_cents
    a.serviceability = s
    dscr = _dscr(a)
    if dscr is not None:
        s["dscr"] = dscr
        a.serviceability = dict(s)
    _recompute_readiness(db, a)
    _log(db, a, "assessed", actor_label, note=f"DSCR {dscr}" if dscr else "Serviceability updated")
    db.flush()
    return a


def _repayment(principal_cents: int, rate_bps: int, months: int) -> int:
    r = rate_bps / 10000 / 12
    if r == 0:
        return round(principal_cents / months)
    return round(principal_cents * r / (1 - (1 + r) ** -months))


def set_stage(db: Session, tenant: Tenant, a: Application, stage: str, note: str | None, actor_mid: uuid.UUID | None, actor_label: str) -> Application:
    if a.stage == stage:
        return a
    if a.stage in TERMINAL and stage not in ("enquiry",):
        raise LendingError("closed", f"The application is {a.stage}")
    if stage == "settled":
        blocking = [c.title for c in a.conditions if c.status == "open" and c.kind == "precedent"]
        if blocking:
            raise LendingError("conditions_open", "Conditions precedent still open: " + "; ".join(blocking[:5]))
        if not a.approved_at:
            raise LendingError("not_approved", "Record the approval before settlement")
    if stage in ("submitted", "approved") and a.request_pack_id:
        from app.modules.requests.models import RequestPack
        from app.modules.requests import service as req_svc
        pack = db.get(RequestPack, a.request_pack_id)
        if stage == "submitted" and pack is not None and req_svc.outstanding(pack):
            raise LendingError("documents_outstanding", "Still waiting on: " + "; ".join(req_svc.outstanding(pack)[:5]))
    old, now = a.stage, utcnow()
    a.stage = stage
    if stage == "submitted":
        a.submitted_at = now
    elif stage == "approved":
        a.approved_at = now
        a.decision_note = note or a.decision_note
    elif stage == "settled":
        a.settled_at, a.settlement_date, a.closed_at = now, date.today(), now
        billing_service.record(db, tenant_id=tenant.id, kind="lending.settled", module_key="lending", amount_cents=0, status="metered", detail={"application_id": str(a.id), "amount_cents": a.amount_cents, "lender": a.lender})
    elif stage in ("declined", "withdrawn"):
        a.closed_at, a.close_reason = now, note
    _recompute_readiness(db, a)
    _log(db, a, "stage", actor_label, from_stage=old, to_stage=stage, note=note)
    events.emit(db, tenant_id=tenant.id, client_id=a.client_id, module_key="lending", kind=f"lending.{stage}", summary=f"{a.reference}: {old} → {stage}" + (f" — {note}" if note else ""),
                detail={"amount_cents": a.amount_cents, "lender": a.lender}, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="lending_application", ref_id=a.id)
    if stage in ("approved", "declined") and a.owner_membership_id and a.owner_membership_id != actor_mid:
        notify_service.notify(db, tenant_id=tenant.id, membership_id=a.owner_membership_id, kind=f"lending.{stage}", title=f"{a.reference} {stage}", body=note, link=f"/lending/{a.id}", module_key="lending")
    db.flush()
    return a


def add_condition(db: Session, a: Application, body: S.ConditionIn, actor_label: str) -> Condition:
    c = Condition(tenant_id=a.tenant_id, application_id=a.id, title=body.title, detail=body.detail, kind=body.kind, owner_side=body.owner_side, due_on=body.due_on)
    db.add(c)
    db.flush()
    db.refresh(a)
    if a.stage == "approved":
        a.stage = "conditions"
    _recompute_readiness(db, a)
    _log(db, a, "condition_added", actor_label, note=body.title)
    return c


def satisfy_condition(db: Session, a: Application, c: Condition, body: S.ConditionSatisfyIn, actor_mid: uuid.UUID, actor_label: str) -> Condition:
    if c.status != "open":
        raise LendingError("already_closed")
    c.status = "waived" if body.waive else "satisfied"
    c.note, c.document_id, c.satisfied_at, c.satisfied_by_membership_id = body.note, body.document_id, utcnow(), actor_mid
    db.flush()
    db.refresh(a)
    _recompute_readiness(db, a)
    _log(db, a, "condition_" + c.status, actor_label, note=c.title)
    if a.stage == "conditions" and not any(x.status == "open" and x.kind == "precedent" for x in a.conditions):
        events.emit(db, tenant_id=a.tenant_id, client_id=a.client_id, module_key="lending", kind="lending.conditions_cleared", summary=f"{a.reference}: all conditions precedent cleared — ready to settle",
                    actor_membership_id=actor_mid, actor_label=actor_label, ref_type="lending_application", ref_id=a.id)
    return c


def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def on_request_completed(db: Session, ev) -> None:
    """Requests → Lending: when the lending pack completes, move the application on and re-score."""
    if ev.module_key != "requests" or ev.ref_type != "request_pack" or not ev.ref_id:
        return
    try:
        pack_id = uuid.UUID(str(ev.ref_id))
    except ValueError:
        return
    a = db.execute(select(Application).where(Application.request_pack_id == pack_id)).scalars().first()
    if a is None:
        return
    _recompute_readiness(db, a)
    if a.stage == "information":
        tenant = db.get(Tenant, a.tenant_id)
        set_stage(db, tenant, a, "assessment", "All requested information received", None, "EnTIQ Requests")


def register() -> None:
    events.subscribe("request.completed", on_request_completed)


# ------------------------------------------------------------------ overview
def overview(db: Session) -> S.OverviewOut:
    rows = db.execute(select(Application)).scalars().all()
    active = [a for a in rows if a.stage not in TERMINAL]
    since = utcnow() - timedelta(days=90)
    settled = [a for a in rows if a.settled_at and a.settled_at >= since]
    closed = [a for a in rows if a.stage in TERMINAL]
    by_stage: dict[str, int] = {}
    for a in rows:
        if a.stage not in TERMINAL:
            by_stage[a.stage] = by_stage.get(a.stage, 0) + 1
    conditions = db.execute(select(func.count()).select_from(Condition).where(Condition.status == "open")).scalar_one()
    return S.OverviewOut(active=len(active), pipeline_value_cents=sum(a.amount_cents for a in active), settled_90d=len(settled), settled_value_90d_cents=sum(a.amount_cents for a in settled),
                         awaiting_client=sum(1 for a in active if a.stage == "information"), conditions_open=conditions, by_stage=by_stage,
                         conversion_pct=round(sum(1 for a in closed if a.stage == "settled") / len(closed) * 100) if closed else None)
