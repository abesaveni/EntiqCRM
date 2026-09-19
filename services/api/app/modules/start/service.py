from __future__ import annotations

import copy
import statistics
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import entitlements, events, mailer
from app.core.config import settings
from app.core.database import bind_tenant
from app.core.security import hash_token, new_opaque_token, utcnow
from app.core.tenancy import platform_scope, set_tenant
from app.models.crm import Client, Contact, Relationship
from app.models.platform import Document
from app.models.tenant import Tenant
from app.modules.start import schemas as S
from app.modules.start.models import GATES, STAGES, Onboarding, OnboardingStage, ServiceOffering
from app.notify import templates
from app.schemas_crm import ContactIn
from app.services import billing_service, crm_service, notify_service
from app.services.crm_service import client_name_map, member_names

STAGE_BY_NUMBER = {n: (n, key, name, actor, desc) for n, key, name, actor, desc in STAGES}
STAGE_BY_KEY = {key: n for n, key, *_ in STAGES}
GATE_LABEL = {"kyc": "Identity (KYC)", "aml": "Screening (AML/CTF)", "esign": "Engagement letter signed", "mandate": "Payment mandate"}


class StageError(Exception):
    def __init__(self, error: str, message: str | None = None):
        super().__init__(message or error)
        self.error, self.message = error, message or error


# ------------------------------------------------------------------ catalogue
DEFAULT_SERVICES: list[dict[str, Any]] = [
    {"name": "Company tax return", "category": "tax", "basis": "annual", "amount_cents": 330000, "entity_types": ["Company"], "sort": 10},
    {"name": "Trust tax return", "category": "tax", "basis": "annual", "amount_cents": 275000, "entity_types": ["Trust"], "sort": 11},
    {"name": "Individual tax return", "category": "tax", "basis": "annual", "amount_cents": 38500, "entity_types": ["Individual"], "sort": 12},
    {"name": "Partnership tax return", "category": "tax", "basis": "annual", "amount_cents": 220000, "entity_types": ["Partnership"], "sort": 13},
    {"name": "SMSF administration & annual return", "category": "smsf", "basis": "annual", "amount_cents": 330000, "entity_types": ["SMSF"], "sort": 14},
    {"name": "Financial statements", "category": "financials", "basis": "annual", "amount_cents": 220000, "entity_types": ["Company", "Trust", "Partnership"], "sort": 20},
    {"name": "Quarterly BAS preparation & lodgement", "category": "bas", "basis": "quarterly", "amount_cents": 55000, "entity_types": [], "sort": 30},
    {"name": "Monthly IAS / payroll lodgement", "category": "ias", "basis": "monthly", "amount_cents": 22000, "entity_types": [], "sort": 31},
    {"name": "Bookkeeping", "category": "bookkeeping", "basis": "monthly", "amount_cents": 66000, "entity_types": [], "sort": 40},
    {"name": "Payroll processing", "category": "payroll", "basis": "monthly", "amount_cents": 33000, "entity_types": ["Company", "Trust", "Partnership"], "sort": 41},
    {"name": "ASIC corporate secretarial", "category": "asic", "basis": "annual", "amount_cents": 49500, "entity_types": ["Company"], "sort": 50},
    {"name": "FBT return", "category": "fbt", "basis": "annual", "amount_cents": 99000, "entity_types": ["Company", "Trust"], "sort": 51},
    {"name": "Business advisory (quarterly meetings)", "category": "advisory", "basis": "quarterly", "amount_cents": 165000, "entity_types": [], "sort": 60},
]


def seed_default_services(db: Session, tenant_id: uuid.UUID) -> int:
    existing = db.execute(select(func.count()).select_from(ServiceOffering)).scalar_one()
    if existing:
        return 0
    for s in DEFAULT_SERVICES:
        db.add(ServiceOffering(tenant_id=tenant_id, description=None, gst=True, is_active=True, **s))
    db.flush()
    return len(DEFAULT_SERVICES)


def service_out(s: ServiceOffering) -> S.ServiceOut:
    return S.ServiceOut(id=s.id, name=s.name, category=s.category, description=s.description, basis=s.basis, amount_cents=s.amount_cents, gst=s.gst, entity_types=s.entity_types or [], is_active=s.is_active, sort=s.sort)


def services_for(db: Session, entity_type: str | None) -> list[ServiceOffering]:
    rows = db.execute(select(ServiceOffering).where(ServiceOffering.is_active.is_(True)).order_by(ServiceOffering.sort, ServiceOffering.name)).scalars().all()
    return [s for s in rows if not entity_type or not s.entity_types or entity_type in s.entity_types]


# ------------------------------------------------------------------ serialisers
def _stage_out(st: OnboardingStage) -> S.StageOut:
    n, key, name, actor, desc = STAGE_BY_NUMBER[st.number]
    return S.StageOut(number=n, key=key, name=name, actor=actor, description=desc, status=st.status, started_at=st.started_at, completed_at=st.completed_at, completed_by=st.completed_by, meta=st.meta or {})


def _gates_out(o: Onboarding) -> list[S.GateOut]:
    out = []
    for g in GATES:
        r = (o.gates or {}).get(g) or {}
        out.append(S.GateOut(gate=g, label=GATE_LABEL[g], status=r.get("status", "Not run"), simulated=bool(r.get("simulated")), detail=r.get("detail"), checked_at=r.get("checked_at")))
    return out


def _progress(o: Onboarding) -> int:
    done = sum(1 for s in o.stages if s.status in ("completed", "skipped"))
    return round(done / len(STAGES) * 100)


def out(db: Session, o: Onboarding, names: dict | None = None) -> S.OnboardingOut:
    c = db.get(Client, o.client_id)
    ct = db.get(Contact, o.primary_contact_id) if o.primary_contact_id else None
    names = names if names is not None else member_names(db, {o.owner_membership_id})
    return S.OnboardingOut(id=o.id, client_id=o.client_id, client_name=c.name if c else "—", client_type=c.client_type if c else "—", client_stage=c.stage if c else "—", primary_contact_name=ct.full_name if ct else None,
                           primary_contact_email=ct.email if ct else None, owner_name=names.get(o.owner_membership_id) if o.owner_membership_id else None, status=o.status, current_stage=o.current_stage, progress_pct=_progress(o),
                           channel=o.channel, invited_at=o.invited_at, opened_at=o.opened_at, activated_at=o.activated_at, withdrawn_at=o.withdrawn_at, withdraw_reason=o.withdraw_reason, token_expires_at=o.token_expires_at,
                           proposal_total_cents=o.proposal_total_cents, sign_agreement_id=o.sign_agreement_id, risk_rating=c.risk_rating if c else None, created_at=o.created_at, updated_at=o.updated_at)


def detail(db: Session, o: Onboarding, invite_url: str | None = None) -> S.OnboardingDetail:
    base = out(db, o)
    return S.OnboardingDetail(**base.model_dump(), stages=[_stage_out(s) for s in o.stages], gates=_gates_out(o), data=o.data or {}, invite_url=invite_url, notes=o.notes)


# ------------------------------------------------------------------ create + invite
def create(db: Session, tenant: Tenant, body: S.OnboardingIn, actor_mid: uuid.UUID, actor_label: str) -> tuple[Onboarding, str | None]:
    if body.client_id:
        c = db.get(Client, body.client_id)
        if c is None:
            raise StageError("client_not_found")
        if db.execute(select(func.count()).select_from(Onboarding).where(Onboarding.client_id == c.id, Onboarding.status.notin_(["withdrawn", "activated"]))).scalar_one():
            raise StageError("onboarding_exists", "An onboarding is already in progress for this client")
        contact = db.execute(select(Contact).where(Contact.client_id == c.id, Contact.archived_at.is_(None)).order_by(Contact.is_primary.desc(), Contact.created_at)).scalars().first()
    else:
        if not body.prospect_name or not body.contact_email or not body.contact_first_name:
            raise StageError("prospect_required", "prospect_name, contact_first_name and contact_email are required when no client_id is given")
        from app.schemas_crm import ClientIn
        c = crm_service.create_client(db, tenant.id, ClientIn(name=body.prospect_name, client_type=body.entity_type, stage="Lead", source="start", owner_membership_id=body.owner_membership_id or actor_mid, email=body.contact_email), actor_mid, actor_label)
        contact = crm_service.add_contact(db, c, ContactIn(first_name=body.contact_first_name, last_name=body.contact_last_name, email=body.contact_email, is_primary=True), actor_mid, actor_label)
    o = Onboarding(tenant_id=tenant.id, client_id=c.id, primary_contact_id=contact.id if contact else None, owner_membership_id=body.owner_membership_id or c.owner_membership_id or actor_mid, status="draft", current_stage=1, notes=body.notes)
    db.add(o)
    db.flush()
    for n, key, *_ in STAGES:
        db.add(OnboardingStage(tenant_id=tenant.id, onboarding_id=o.id, number=n, key=key, status="active" if n == 1 else "pending", started_at=utcnow() if n == 1 else None))
    db.flush()
    db.refresh(o)
    seed_default_services(db, tenant.id)
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="start", kind="onboarding.created", summary=f"Onboarding opened for {c.name}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="onboarding", ref_id=o.id)
    url = None
    if body.send_invitation:
        url = invite(db, tenant, o, actor_mid, actor_label, valid_days=body.invite_valid_days)
    return o, url


def _invite_url(raw: str) -> str:
    return f"{settings.APP_PUBLIC_URL.rstrip('/')}/onboard/{raw}"


def invite(db: Session, tenant: Tenant, o: Onboarding, actor_mid: uuid.UUID | None, actor_label: str, *, valid_days: int = 30) -> str:
    if o.status in ("activated", "withdrawn"):
        raise StageError("closed", f"Onboarding is {o.status}")
    ct = db.get(Contact, o.primary_contact_id) if o.primary_contact_id else None
    if ct is None or not ct.email:
        raise StageError("no_contact_email", "The prospect needs a primary contact with an email address")
    c = db.get(Client, o.client_id)
    raw, h = new_opaque_token()
    o.token_hash, o.token_expires_at, o.invited_at = h, utcnow() + timedelta(days=valid_days), utcnow()
    if o.status == "draft":
        o.status = "invited"
    url = _invite_url(raw)
    subject, text, html = templates.start_invitation(name=ct.first_name, practice=tenant.name, prospect=c.name, url=url, expires=o.token_expires_at.strftime("%d %b %Y"))
    mailer.queue_email(db, tenant_id=tenant.id, to=ct.email, subject=subject, text=text, html=html, template="start_invitation", ref_type="onboarding", ref_id=o.id)
    if c.stage in ("Lead", "Proposal"):
        crm_service.change_stage(db, c, "Onboarding", "Invitation sent", actor_mid, actor_label)
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="start", kind="onboarding.invited", summary=f"Invitation sent to {ct.full_name} <{ct.email}>", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="onboarding", ref_id=o.id)
    db.flush()
    return url


def withdraw(db: Session, o: Onboarding, reason: str, actor_mid: uuid.UUID, actor_label: str) -> Onboarding:
    if o.status == "activated":
        raise StageError("closed", "An activated client cannot be withdrawn — archive it in the CRM instead")
    o.status, o.withdrawn_at, o.withdraw_reason, o.token_hash = "withdrawn", utcnow(), reason, None
    c = db.get(Client, o.client_id)
    if c and c.stage == "Onboarding":
        crm_service.change_stage(db, c, "Lost", reason, actor_mid, actor_label)
    events.emit(db, tenant_id=o.tenant_id, client_id=o.client_id, module_key="start", kind="onboarding.withdrawn", summary=f"Onboarding withdrawn — {reason}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="onboarding", ref_id=o.id)
    return o


# ------------------------------------------------------------------ the stage engine
def _stage(o: Onboarding, n: int) -> OnboardingStage:
    return next(s for s in o.stages if s.number == n)


def _assert_can_complete(o: Onboarding, n: int) -> None:
    if o.status in ("activated", "withdrawn"):
        raise StageError("closed", f"Onboarding is {o.status}")
    for s in o.stages:
        if s.number < n and s.status not in ("completed", "skipped"):
            raise StageError("stage_order", f"Stage {s.number} ({STAGE_BY_NUMBER[s.number][2]}) must be completed first")
    if _stage(o, n).status == "completed":
        raise StageError("already_completed", f"Stage {n} is already complete")


def _complete(db: Session, o: Onboarding, n: int, by: str, meta: dict | None = None) -> None:
    st = _stage(o, n)
    now = utcnow()
    st.status, st.completed_at, st.completed_by = "completed", now, by[:120]
    st.meta = {**(st.meta or {}), **(meta or {})}
    if n < len(STAGES):
        nxt = _stage(o, n + 1)
        if nxt.status == "pending":
            nxt.status, nxt.started_at = "active", now
        o.current_stage = n + 1
        next_actor = STAGE_BY_NUMBER[n + 1][3]
        o.status = "awaiting_practice" if next_actor == "practice" else "in_progress"
    _, key, name, actor, _ = STAGE_BY_NUMBER[n]
    events.emit(db, tenant_id=o.tenant_id, client_id=o.client_id, module_key="start", kind="onboarding.stage_completed", summary=f"Stage {n} · {name} completed", detail={"stage": key, "by": by, **(meta or {})}, actor_label=by, ref_type="onboarding", ref_id=o.id)
    # tell the owner when the ball moves to the practice
    if n < len(STAGES) and STAGE_BY_NUMBER[n + 1][3] == "practice" and actor == "prospect" and o.owner_membership_id:
        c = db.get(Client, o.client_id)
        notify_service.notify(db, tenant_id=o.tenant_id, membership_id=o.owner_membership_id, kind="onboarding.ready", title=f"{c.name if c else 'Prospect'} is ready for {STAGE_BY_NUMBER[n + 1][2].lower()}", link=f"/start/onboardings/{o.id}", module_key="start")
    db.flush()


def _put(o: Onboarding, key: str, value: Any) -> None:
    # SQLAlchemy detects JSON changes by comparing with the loaded snapshot, so nested in-place edits would be lost:
    # always assign a fresh, deep-copied structure.
    o.data = {**copy.deepcopy(o.data or {}), key: copy.deepcopy(value)}


def _get(o: Onboarding, key: str, default=None):
    return copy.deepcopy((o.data or {}).get(key, default))


# stage 1 — opened by the prospect
def mark_opened(db: Session, o: Onboarding) -> None:
    if o.opened_at is None:
        o.opened_at = utcnow()
    if _stage(o, 1).status != "completed":
        _complete(db, o, 1, "Prospect", {"channel": o.channel})


# stage 2
def complete_entity_details(db: Session, o: Onboarding, body: S.EntityDetailsIn, by: str, actor_mid: uuid.UUID | None = None) -> None:
    _assert_can_complete(o, 2)
    c = db.get(Client, o.client_id)
    from app.schemas_crm import ClientPatch
    patch = ClientPatch(name=body.trading_name or body.legal_name, legal_name=body.legal_name, client_type=body.entity_type, abn=body.abn, acn=body.acn, email=body.contact_email, phone=body.contact_phone,
                        address_line1=body.address_line1, suburb=body.suburb, state=body.state, postcode=body.postcode)
    crm_service.update_client(db, c, patch, actor_mid, by)
    if body.industry:
        c.custom = {**(c.custom or {}), "industry": body.industry, "tax_residency": body.tax_residency, "gst_registered": body.gst_registered}
    ct = db.get(Contact, o.primary_contact_id) if o.primary_contact_id else None
    if ct:
        parts = body.contact_name.strip().split(" ", 1)
        ct.first_name, ct.last_name, ct.email, ct.phone = parts[0], (parts[1] if len(parts) > 1 else ct.last_name), body.contact_email, body.contact_phone or ct.phone
    _put(o, "entity_details", body.model_dump(mode="json"))
    # stage 4's checklist depends on the entity type
    reqs = [{"key": k, "label": l, "required": r, "document_id": None, "uploaded_at": None, "verified_by": None, "verified_at": None} for k, l, r in S.DOCUMENT_REQUESTS.get(body.entity_type, S.DOCUMENT_REQUESTS["Other"])]
    _put(o, "document_requests", reqs)
    _complete(db, o, 2, by, {"entity_type": body.entity_type, "abn": body.abn})


# stage 3
def complete_questionnaire(db: Session, o: Onboarding, body: S.QuestionnaireIn, by: str) -> None:
    _assert_can_complete(o, 3)
    missing = [q["label"] for q in S.QUESTIONNAIRE if q["required"] and body.answers.get(q["key"]) in (None, "", [])]
    if missing:
        raise StageError("questionnaire_incomplete", "Please answer: " + "; ".join(missing))
    _put(o, "questionnaire", body.answers)
    _complete(db, o, 3, by, {"answered": len([k for k, v in body.answers.items() if v not in (None, "")])})


# stage 4
def attach_document(db: Session, o: Onboarding, req_key: str, doc: Document, by: str) -> None:
    reqs = _get(o, "document_requests", []) or []
    hit = next((r for r in reqs if r["key"] == req_key), None)
    if hit is None:
        raise StageError("unknown_document_request")
    hit["document_id"], hit["uploaded_at"] = str(doc.id), utcnow().isoformat()
    _put(o, "document_requests", reqs)
    st = _stage(o, 4)
    if st.status == "active" and st.started_at is None:
        st.started_at = utcnow()
    db.flush()


def verify_document(db: Session, o: Onboarding, req_key: str, by: str) -> None:
    reqs = _get(o, "document_requests", []) or []
    hit = next((r for r in reqs if r["key"] == req_key), None)
    if hit is None or not hit.get("document_id"):
        raise StageError("nothing_to_verify")
    hit["verified_by"], hit["verified_at"] = by, utcnow().isoformat()
    _put(o, "document_requests", reqs)
    db.flush()


def complete_documents(db: Session, o: Onboarding, by: str, *, practice: bool) -> None:
    _assert_can_complete(o, 4)
    reqs = _get(o, "document_requests", []) or []
    missing = [r["label"] for r in reqs if r["required"] and not r.get("document_id")]
    if missing:
        raise StageError("documents_missing", "Still needed: " + "; ".join(missing))
    unverified = [r["label"] for r in reqs if r.get("document_id") and not r.get("verified_by")]
    if not practice and unverified:
        # the prospect has uploaded everything; the stage completes once the practice verifies — hand over now
        o.status = "awaiting_practice"
        if o.owner_membership_id:
            notify_service.notify(db, tenant_id=o.tenant_id, membership_id=o.owner_membership_id, kind="onboarding.documents", title="Documents uploaded — verification needed", link=f"/start/onboardings/{o.id}", module_key="start")
        db.flush()
        return
    if practice and unverified:
        for r in reqs:
            if r.get("document_id") and not r.get("verified_by"):
                r["verified_by"], r["verified_at"] = by, utcnow().isoformat()
        _put(o, "document_requests", reqs)
    _complete(db, o, 4, by, {"documents": sum(1 for r in reqs if r.get("document_id"))})


# stage 5
def complete_related_parties(db: Session, o: Onboarding, body: S.RelatedPartiesIn, by: str, actor_mid: uuid.UUID | None = None) -> None:
    _assert_can_complete(o, 5)
    c = db.get(Client, o.client_id)
    existing = {(ct.full_name.lower()) for ct in db.execute(select(Contact).where(Contact.client_id == c.id)).scalars()}
    created = 0
    for p in body.parties:
        if p.name.strip().lower() in existing:
            continue
        parts = p.name.strip().split(" ", 1)
        ct = crm_service.add_contact(db, c, ContactIn(first_name=parts[0], last_name=parts[1] if len(parts) > 1 else None, email=p.email, phone=p.phone, role=p.role), actor_mid, by)
        kind = {"Director": "director_of", "Secretary": "secretary_of", "Shareholder": "shareholder_of", "Trustee": "trustee_of", "Beneficiary": "beneficiary_of", "Appointor": "appointor_of", "Partner": "partner_of", "Member": "member_of", "Owner": "owner_of"}.get(p.role, "related_entity")
        db.add(Relationship(tenant_id=c.tenant_id, from_type="contact", from_id=ct.id, to_type="client", to_id=c.id, kind=kind, percentage=p.ownership_pct, notes="Beneficial owner" if p.is_beneficial_owner else None))
        created += 1
    _put(o, "related_parties", body.model_dump(mode="json"))
    c.custom = {**(c.custom or {}), "ownership_complete": body.ownership_complete}
    _complete(db, o, 5, by, {"parties": len(body.parties), "contacts_created": created, "ownership_complete": body.ownership_complete})


# stage 6
def complete_service_selection(db: Session, o: Onboarding, body: S.ServiceSelectionIn, by: str) -> None:
    _assert_can_complete(o, 6)
    rows = db.execute(select(ServiceOffering).where(ServiceOffering.id.in_(body.service_ids))).scalars().all()
    if len(rows) != len(set(body.service_ids)):
        raise StageError("unknown_service")
    sel = [service_out(s).model_dump(mode="json") for s in rows]
    _put(o, "service_selection", {"services": sel, "notes": body.notes})
    _complete(db, o, 6, by, {"services": [s["name"] for s in sel]})


# stage 7 — practice issues, prospect accepts
def issue_proposal(db: Session, o: Onboarding, body: S.ProposalIssueIn, by: str, actor_mid: uuid.UUID) -> None:
    if _stage(o, 6).status != "completed":
        raise StageError("stage_order", "Services must be selected before a proposal is issued")
    if _stage(o, 7).status == "completed":
        raise StageError("already_completed")
    total = sum(l.amount_cents for l in body.lines)
    gst = sum(round(l.amount_cents * settings.GST_RATE_BPS / 10000) for l in body.lines if l.gst)
    prop = {"lines": [l.model_dump(mode="json") for l in body.lines], "terms": body.terms, "issued_at": utcnow().isoformat(), "issued_by": by, "valid_until": (utcnow() + timedelta(days=body.valid_days)).isoformat(),
            "subtotal_cents": total, "gst_cents": gst, "total_cents": total + gst, "accepted_at": None, "accepted_by_name": None, "declined_at": None}
    _put(o, "proposal", prop)
    o.proposal_total_cents = total + gst
    c = db.get(Client, o.client_id)
    ct = db.get(Contact, o.primary_contact_id) if o.primary_contact_id else None
    if ct and ct.email and o.token_hash:
        # the prospect uses the same magic link; remind them a proposal is waiting
        subject, text, html = templates.start_proposal(name=ct.first_name, practice=db.get(Tenant, o.tenant_id).name, total=f"${(total + gst) / 100:,.2f}", url=f"{settings.APP_PUBLIC_URL.rstrip('/')}/onboard", valid_until=prop["valid_until"][:10])
        mailer.queue_email(db, tenant_id=o.tenant_id, to=ct.email, subject=subject, text=text, html=html, template="start_proposal", ref_type="onboarding", ref_id=o.id)
    if c.stage == "Onboarding":
        pass
    events.emit(db, tenant_id=o.tenant_id, client_id=o.client_id, module_key="start", kind="onboarding.proposal_issued", summary=f"Proposal issued: ${(total + gst) / 100:,.2f} inc GST ({len(body.lines)} lines)", actor_membership_id=actor_mid, actor_label=by, ref_type="onboarding", ref_id=o.id)
    o.status = "in_progress"
    db.flush()


def accept_proposal(db: Session, o: Onboarding, body: S.ProposalAcceptIn, by: str) -> None:
    _assert_can_complete(o, 7)
    prop = _get(o, "proposal")
    if not prop:
        raise StageError("no_proposal", "The practice has not issued a proposal yet")
    if not body.accept:
        prop["declined_at"] = utcnow().isoformat()
        _put(o, "proposal", prop)
        o.status = "awaiting_practice"
        if o.owner_membership_id:
            notify_service.notify(db, tenant_id=o.tenant_id, membership_id=o.owner_membership_id, kind="onboarding.proposal_declined", title="Proposal declined", body=f"{body.accepted_by_name} declined the fee proposal", link=f"/start/onboardings/{o.id}", module_key="start")
        events.emit(db, tenant_id=o.tenant_id, client_id=o.client_id, module_key="start", kind="onboarding.proposal_declined", summary=f"Proposal declined by {body.accepted_by_name}", actor_label=by, ref_type="onboarding", ref_id=o.id)
        db.flush()
        return
    prop["accepted_at"], prop["accepted_by_name"], prop["declined_at"] = utcnow().isoformat(), body.accepted_by_name, None
    _put(o, "proposal", prop)
    _complete(db, o, 7, body.accepted_by_name, {"total_cents": prop["total_cents"]})


# stage 8 — the practice sends the letter of engagement through Sign
def prepare_engagement(db: Session, tenant: Tenant, o: Onboarding, body: S.EngagementPrepIn, actor_mid: uuid.UUID, by: str) -> uuid.UUID:
    _assert_can_complete(o, 8)
    try:
        entitlements.check(db, tenant, "sign")
    except entitlements.NotEntitled:
        raise StageError("sign_required", "Sending the engagement letter needs the Sign module")
    from app.modules.sign import schemas as SignS
    from app.modules.sign import service as sign_svc
    ct = db.get(Contact, o.primary_contact_id) if o.primary_contact_id else None
    if ct is None or not ct.email:
        raise StageError("no_contact_email")
    c = db.get(Client, o.client_id)
    a = sign_svc.create(db, tenant, SignS.AgreementIn(title=body.title or f"Letter of engagement — {c.name}", document_id=body.document_id, client_id=c.id, kind="engagement_letter", message=body.message,
                                                       signers=[SignS.SignerIn(name=ct.full_name, email=ct.email, contact_id=ct.id)], require_identity=body.require_identity, send_now=True), actor_mid, by)
    o.sign_agreement_id = a.id
    _put(o, "engagement", {"agreement_id": str(a.id), "sent_at": utcnow().isoformat(), "document_id": str(body.document_id)})
    _complete(db, o, 8, by, {"agreement_id": str(a.id)})
    return a.id


# stage 9 — gates read from the other modules; nothing is re-implemented here
def run_gates(db: Session, tenant: Tenant, o: Onboarding, by: str) -> dict:
    if _stage(o, 8).status != "completed":
        raise StageError("stage_order", "Send the engagement letter before running checks")
    from app.modules.sign.models import Agreement
    from app.modules.verify import service as verify_svc
    from app.modules.verify.models import Screening, Verification
    now = utcnow().isoformat()
    results: dict[str, dict] = dict(o.gates or {})
    c = db.get(Client, o.client_id)
    ct = db.get(Contact, o.primary_contact_id) if o.primary_contact_id else None

    def entitled(k: str) -> bool:
        try:
            entitlements.check(db, tenant, k)
            return True
        except entitlements.NotEntitled:
            return False

    # KYC — the primary contact (the person signing) holds a current identity verification
    if not entitled("verify"):
        results["kyc"] = {"status": "Error", "simulated": False, "detail": "Verify module not subscribed", "checked_at": now}
        results["aml"] = {"status": "Error", "simulated": False, "detail": "Verify module not subscribed", "checked_at": now}
    else:
        v = db.execute(select(Verification).where(Verification.contact_id == (ct.id if ct else None)).order_by(Verification.created_at.desc())).scalars().first() if ct else None
        if v and v.status == "verified" and (v.expires_at is None or v.expires_at > utcnow()):
            results["kyc"] = {"status": "Passed", "simulated": bool(v.simulated), "detail": f"{ct.full_name} verified via {v.provider}", "checked_at": now, "ref": str(v.id)}
        elif v and v.status in ("pending", "in_progress"):
            results["kyc"] = {"status": "Pending", "simulated": bool(v.simulated), "detail": "Identity verification in progress", "checked_at": now, "ref": str(v.id)}
        elif v and v.status == "failed":
            results["kyc"] = {"status": "Failed", "simulated": bool(v.simulated), "detail": v.failure_reason or "Identity verification failed", "checked_at": now, "ref": str(v.id)}
        else:
            results["kyc"] = {"status": "Pending", "simulated": False, "detail": f"No identity verification for {ct.full_name if ct else 'the primary contact'} — start one in Verify", "checked_at": now}
        # AML — entity screened and clear (or reviewed as false positive); no confirmed match on any party
        scr = db.execute(select(Screening).where(Screening.client_id == c.id).order_by(Screening.screened_at.desc())).scalars().all()
        entity = next((s for s in scr if s.subject_type == "entity"), None)
        confirmed = [s for s in scr if s.status == "confirmed_match"]
        pending = [s for s in scr if s.status == "potential_match"]
        if confirmed:
            results["aml"] = {"status": "Failed", "simulated": any(s.simulated for s in confirmed), "detail": f"Confirmed match: {', '.join(s.subject_name for s in confirmed)}", "checked_at": now}
        elif entity is None:
            results["aml"] = {"status": "Pending", "simulated": False, "detail": "Entity not yet screened — run screening in Verify", "checked_at": now}
        elif pending:
            results["aml"] = {"status": "Pending", "simulated": any(s.simulated for s in pending), "detail": f"{len(pending)} screening hit(s) awaiting review", "checked_at": now}
        else:
            results["aml"] = {"status": "Passed", "simulated": bool(entity.simulated), "detail": f"Entity clear ({entity.provider}); {len(scr)} screening(s) on file", "checked_at": now, "ref": str(entity.id)}
    # eSign — the letter of engagement is completed
    a = db.get(Agreement, o.sign_agreement_id) if o.sign_agreement_id else None
    if a is None:
        results["esign"] = {"status": "Pending", "simulated": False, "detail": "No engagement letter on file", "checked_at": now}
    elif a.status == "completed":
        results["esign"] = {"status": "Passed", "simulated": False, "detail": f"Signed {a.completed_at:%d %b %Y}; seal {a.sealed_sha256[:12]}…", "checked_at": now, "ref": str(a.id)}
    elif a.status in ("declined", "voided", "expired"):
        results["esign"] = {"status": "Failed", "simulated": False, "detail": f"Engagement letter {a.status}", "checked_at": now, "ref": str(a.id)}
    else:
        results["esign"] = {"status": "Pending", "simulated": False, "detail": f"Awaiting signature ({a.status.replace('_', ' ')})", "checked_at": now, "ref": str(a.id)}
    # Mandate — recorded by the prospect (or the practice on their behalf)
    m = (o.data or {}).get("mandate")
    if m:
        results["mandate"] = {"status": "Passed", "simulated": bool(m.get("simulated", True)), "detail": f"{m['method'].replace('_', ' ')} · {m.get('reference') or 'no reference'}", "checked_at": now}
    else:
        results["mandate"] = {"status": "Pending", "simulated": False, "detail": "Payment mandate not yet provided", "checked_at": now}
    o.gates = copy.deepcopy(results)
    all_passed = all(results[g]["status"] == "Passed" for g in GATES)
    st = _stage(o, 9)
    if all_passed and st.status != "completed":
        _complete(db, o, 9, by, {"simulated_gates": [g for g in GATES if results[g].get("simulated")], "fully_verified": not any(results[g].get("simulated") for g in GATES)})
    elif not all_passed:
        st.status = "blocked" if any(results[g]["status"] in ("Failed", "Error") for g in GATES) else "active"
    events.emit(db, tenant_id=o.tenant_id, client_id=o.client_id, module_key="start", kind="onboarding.gates_run", summary="Checks: " + ", ".join(f"{GATE_LABEL[g].split(' (')[0]} {results[g]['status']}" for g in GATES), actor_label=by, ref_type="onboarding", ref_id=o.id)
    db.flush()
    return results


def record_mandate(db: Session, o: Onboarding, body: S.MandateIn, by: str) -> None:
    if o.status in ("activated", "withdrawn"):
        raise StageError("closed")
    if not body.accepted_terms:
        raise StageError("terms_required", "The direct debit / payment terms must be accepted")
    # BILLING_MODE=simulate: the mandate is a recorded intent; with Stripe it becomes a SetupIntent/mandate reference
    _put(o, "mandate", {"method": body.method, "reference": body.reference, "account_name": body.account_name, "accepted_at": utcnow().isoformat(), "by": by, "simulated": settings.BILLING_MODE != "stripe"})
    events.emit(db, tenant_id=o.tenant_id, client_id=o.client_id, module_key="start", kind="onboarding.mandate", summary=f"Payment mandate recorded ({body.method.replace('_', ' ')})", actor_label=by, ref_type="onboarding", ref_id=o.id)
    db.flush()


# stage 10
def accept_internally(db: Session, o: Onboarding, body: S.AcceptanceIn, actor_mid: uuid.UUID, by: str) -> None:
    _assert_can_complete(o, 10)
    if not (body.partner_signoff and body.margin_ok and body.risk_signoff):
        raise StageError("acceptance_incomplete", "Partner sign-off, margin check and risk sign-off are all required")
    _put(o, "acceptance", {**body.model_dump(), "by": by, "at": utcnow().isoformat()})
    _complete(db, o, 10, by, {"notes": body.notes})


# stage 11 — handover: the CRM client becomes Active; downstream modules react to the event
def activate(db: Session, tenant: Tenant, o: Onboarding, actor_mid: uuid.UUID, by: str) -> None:
    _assert_can_complete(o, 11)
    c = db.get(Client, o.client_id)
    crm_service.change_stage(db, c, "Active", "Onboarding completed", actor_mid, by)
    c.tags = sorted(set(c.tags or []) | {"onboarded"})
    o.status, o.activated_at, o.token_hash = "activated", utcnow(), None
    services = ((o.data or {}).get("service_selection") or {}).get("services", [])
    _complete(db, o, 11, by, {"services": [s["name"] for s in services]})
    o.status = "activated"
    billing_service.record(db, tenant_id=tenant.id, kind="onboarding.activated", module_key="start", amount_cents=0, status="metered", detail={"onboarding_id": str(o.id), "client_id": str(c.id)})
    ct = db.get(Contact, o.primary_contact_id) if o.primary_contact_id else None
    if ct and ct.email:
        subject, text, html = templates.start_activated(name=ct.first_name, practice=tenant.name, prospect=c.name)
        mailer.queue_email(db, tenant_id=tenant.id, to=ct.email, subject=subject, text=text, html=html, template="start_activated", ref_type="onboarding", ref_id=o.id)
    events.emit(db, tenant_id=tenant.id, client_id=c.id, module_key="start", kind="onboarding.activated", summary=f"{c.name} activated as a client",
                detail={"services": services, "owner_membership_id": str(o.owner_membership_id) if o.owner_membership_id else None, "proposal_total_cents": o.proposal_total_cents},
                actor_membership_id=actor_mid, actor_label=by, ref_type="onboarding", ref_id=o.id)
    db.flush()


# ------------------------------------------------------------------ public (prospect) surface
class TokenError(Exception):
    pass


def load_by_token(db: Session, raw: str) -> tuple[Onboarding, Tenant]:
    with platform_scope():
        o = db.execute(select(Onboarding).where(Onboarding.token_hash == hash_token(raw))).scalar_one_or_none()
        if o is None:
            raise TokenError("invalid_link")
        t = db.get(Tenant, o.tenant_id)
    bind_tenant(db, o.tenant_id)
    set_tenant(o.tenant_id)
    if o.status == "withdrawn":
        raise TokenError("withdrawn")
    if o.token_expires_at and o.token_expires_at < utcnow():
        raise TokenError("expired")
    return o, t


def public_view(db: Session, o: Onboarding, t: Tenant) -> S.PublicView:
    c = db.get(Client, o.client_id)
    ct = db.get(Contact, o.primary_contact_id) if o.primary_contact_id else None
    ent = ((o.data or {}).get("entity_details") or {}).get("entity_type") or c.client_type
    services = [service_out(s) for s in services_for(db, ent)]
    data = {k: v for k, v in (o.data or {}).items() if k not in ("acceptance", "engagement")}
    return S.PublicView(practice_name=t.name, prospect_name=c.name, contact_name=ct.full_name if ct else None, status=o.status, current_stage=o.current_stage, stages=[_stage_out(s) for s in o.stages], data=data,
                        questionnaire=S.QUESTIONNAIRE, document_requests=(o.data or {}).get("document_requests") or [], services=services, proposal=(o.data or {}).get("proposal"), expires_at=o.token_expires_at)


# ------------------------------------------------------------------ overview
def overview(db: Session) -> S.OverviewOut:
    rows = db.execute(select(Onboarding)).scalars().all()
    since = utcnow() - timedelta(days=30)
    open_ = [o for o in rows if o.status not in ("activated", "withdrawn")]
    by_stage: dict[str, int] = {}
    for o in open_:
        key = STAGE_BY_NUMBER[o.current_stage][2]
        by_stage[key] = by_stage.get(key, 0) + 1
    durations = [(o.activated_at - o.created_at).total_seconds() / 86400 for o in rows if o.activated_at]
    return S.OverviewOut(active=len(open_), awaiting_prospect=sum(1 for o in open_ if STAGE_BY_NUMBER[o.current_stage][3] == "prospect"), awaiting_practice=sum(1 for o in open_ if STAGE_BY_NUMBER[o.current_stage][3] == "practice"),
                         activated_30d=sum(1 for o in rows if o.activated_at and o.activated_at >= since), withdrawn_30d=sum(1 for o in rows if o.withdrawn_at and o.withdrawn_at >= since), by_stage=by_stage,
                         median_days_to_activate=round(statistics.median(durations), 1) if durations else None)
