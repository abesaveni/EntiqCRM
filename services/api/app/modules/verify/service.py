from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import events
from app.core.config import settings
from app.core.security import utcnow
from app.models.crm import Client, Contact, Relationship
from app.modules.verify import providers, risk as risk_engine
from app.modules.verify import schemas as S
from app.modules.verify.models import RiskAssessment, Screening, Verification
from app.services import billing_service
from app.services.crm_service import member_names

VERIFICATION_PRICE_CENTS = 7000  # $70 per verification — GrowKyc's existing unit price
IDENTITY_VALID_DAYS = 365


# ------------------------------------------------------------------ serialisers
def verification_out(v: Verification, names: dict) -> S.VerificationOut:
    return S.VerificationOut(id=v.id, client_id=v.client_id, contact_id=v.contact_id, subject_type=v.subject_type, subject_name=v.subject_name, provider=v.provider, simulated=v.simulated,
                             status=v.status, verification_url=v.verification_url, result=v.result or {}, failure_reason=v.failure_reason,
                             started_by_name=names.get(v.started_by_membership_id) if v.started_by_membership_id else None, completed_at=v.completed_at, expires_at=v.expires_at, created_at=v.created_at)


def screening_out(s: Screening, names: dict, client_names: dict | None = None) -> S.ScreeningOut:
    return S.ScreeningOut(id=s.id, client_id=s.client_id, client_name=(client_names or {}).get(s.client_id), contact_id=s.contact_id, subject_type=s.subject_type, subject_name=s.subject_name,
                          provider=s.provider, simulated=s.simulated, status=s.status, match_count=s.match_count, matches=s.matches or [], threshold=s.threshold, error=s.error,
                          screened_at=s.screened_at, review_decision=s.review_decision, reviewed_by_name=names.get(s.reviewed_by_membership_id) if s.reviewed_by_membership_id else None,
                          reviewed_at=s.reviewed_at, review_notes=s.review_notes)


def risk_out(r: RiskAssessment, names: dict) -> S.RiskOut:
    return S.RiskOut(id=r.id, client_id=r.client_id, rating=r.rating, score=r.score, method=r.method, factors=r.factors or [], assessed_by_name=names.get(r.assessed_by_membership_id) if r.assessed_by_membership_id else None,
                     assessed_at=r.assessed_at, next_review_at=r.next_review_at, notes=r.notes)


# ------------------------------------------------------------------ identity
def start_verification(db: Session, client: Client, body: S.StartVerificationIn, actor_mid: uuid.UUID, actor_label: str) -> Verification:
    contact = db.get(Contact, body.contact_id) if body.contact_id else None
    if body.subject_type == "individual" and contact is None:
        raise ValueError("contact_id is required for an individual verification")
    subject_name = contact.full_name if contact else client.name
    v = Verification(tenant_id=client.tenant_id, client_id=client.id, contact_id=contact.id if contact else None, subject_type=body.subject_type, subject_name=subject_name,
                     provider="pending", status="pending", started_by_membership_id=actor_mid)
    db.add(v)
    db.flush()
    prov = providers.identity_provider()
    callback = f"{settings.APP_PUBLIC_URL.rstrip('/')}/api/v1/verify/webhooks/{prov.name}" if prov.name != "simulation" else None
    started = prov.start(subject_type=body.subject_type, subject_name=subject_name, vendor_ref=str(v.id), callback_url=callback)
    v.provider, v.provider_ref, v.verification_url, v.status, v.simulated, v.result = started.provider, started.reference, started.url, started.status, started.simulated, started.result
    if v.status == "verified":
        v.completed_at, v.expires_at = utcnow(), utcnow() + timedelta(days=IDENTITY_VALID_DAYS)
    elif v.status == "failed":
        v.completed_at, v.failure_reason = utcnow(), started.result.get("raw_status", "declined")
    billing_service.record(db, tenant_id=client.tenant_id, kind="verification.started", module_key="verify", amount_cents=VERIFICATION_PRICE_CENTS, status="metered",
                           detail={"verification_id": str(v.id), "provider": v.provider, "simulated": v.simulated, "subject_type": v.subject_type})
    events.emit(db, tenant_id=client.tenant_id, client_id=client.id, module_key="verify", kind=f"verification.{'completed' if v.status in ('verified', 'failed') else 'started'}",
                summary=f"Identity {'verified' if v.status == 'verified' else 'check failed' if v.status == 'failed' else 'verification started'}: {subject_name}" + (" (SIMULATED)" if v.simulated else ""),
                detail={"status": v.status, "provider": v.provider, "simulated": v.simulated}, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="verification", ref_id=v.id)
    return v


def refresh_verification(db: Session, v: Verification, actor_label: str = "EnTIQ Verify") -> Verification:
    if v.status in ("verified", "failed", "expired", "cancelled") or not v.provider_ref:
        return v
    prov = providers.identity_provider()
    if prov.name != v.provider:
        return v
    res = prov.fetch(v.provider_ref)
    if res.status != v.status:
        v.status, v.result = res.status, {**(v.result or {}), **res.result}
        if res.status == "verified":
            v.completed_at, v.expires_at = utcnow(), utcnow() + timedelta(days=IDENTITY_VALID_DAYS)
        elif res.status in ("failed", "expired"):
            v.completed_at, v.failure_reason = utcnow(), res.failure_reason
        events.emit(db, tenant_id=v.tenant_id, client_id=v.client_id, module_key="verify", kind="verification.completed", summary=f"Identity {res.status}: {v.subject_name}",
                    detail={"status": res.status, "provider": v.provider}, actor_label=actor_label, ref_type="verification", ref_id=v.id)
    return v


def apply_webhook(db: Session, provider: str, reference: str, status: str, result: dict) -> Verification | None:
    v = db.execute(select(Verification).where(Verification.provider == provider, Verification.provider_ref == reference)).scalar_one_or_none()
    if v is None or v.status in ("verified", "failed", "cancelled"):
        return v
    v.status, v.result = status, {**(v.result or {}), **result}
    if status == "verified":
        v.completed_at, v.expires_at = utcnow(), utcnow() + timedelta(days=IDENTITY_VALID_DAYS)
    elif status in ("failed", "expired"):
        v.completed_at = utcnow()
    events.emit(db, tenant_id=v.tenant_id, client_id=v.client_id, module_key="verify", kind="verification.completed", summary=f"Identity {status}: {v.subject_name}", detail={"status": status, "provider": provider, "via": "webhook"}, ref_type="verification", ref_id=v.id)
    return v


# ------------------------------------------------------------------ screening
def screen(db: Session, client: Client, body: S.ScreenIn, actor_mid: uuid.UUID, actor_label: str) -> Screening:
    contact = db.get(Contact, body.contact_id) if body.contact_id else None
    subject_type = "individual" if contact else ("individual" if client.client_type == "Individual" else "entity")
    subject_name = contact.full_name if contact else client.name
    prov = providers.screening_provider()
    res = prov.screen(subject_type=subject_type, name=subject_name, dob=body.dob, country=client.country)
    s = Screening(tenant_id=client.tenant_id, client_id=client.id, contact_id=contact.id if contact else None, subject_type=subject_type, subject_name=subject_name, provider=res.provider,
                  simulated=res.simulated, status=res.status, match_count=len(res.matches), matches=res.matches, threshold=int(float(settings.OPENSANCTIONS_THRESHOLD) * 100) if float(settings.OPENSANCTIONS_THRESHOLD) <= 1 else int(float(settings.OPENSANCTIONS_THRESHOLD)),
                  error=res.error, screened_at=utcnow())
    db.add(s)
    db.flush()
    billing_service.record(db, tenant_id=client.tenant_id, kind="screening.run", module_key="verify", amount_cents=0, status="metered", detail={"screening_id": str(s.id), "provider": s.provider, "simulated": s.simulated, "matches": s.match_count})
    label = {"clear": "clear", "potential_match": f"{s.match_count} potential match{'es' if s.match_count != 1 else ''} — review required", "error": f"error: {s.error}"}[s.status]
    events.emit(db, tenant_id=client.tenant_id, client_id=client.id, module_key="verify", kind=f"screening.{s.status}", summary=f"PEP/sanctions screening of {subject_name}: {label}" + (" (SIMULATED)" if s.simulated else ""),
                detail={"status": s.status, "matches": s.match_count, "provider": s.provider, "simulated": s.simulated}, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="screening", ref_id=s.id)
    return s


def review_screening(db: Session, s: Screening, body: S.ReviewIn, actor_mid: uuid.UUID, actor_label: str) -> Screening:
    s.review_decision, s.review_notes, s.reviewed_by_membership_id, s.reviewed_at = body.decision, body.notes, actor_mid, utcnow()
    s.status = "confirmed_match" if body.decision == "true_match" else "false_positive"
    events.emit(db, tenant_id=s.tenant_id, client_id=s.client_id, module_key="verify", kind=f"screening.reviewed", summary=f"Screening match for {s.subject_name} reviewed: {body.decision.replace('_', ' ')}",
                detail={"decision": body.decision, "notes": body.notes}, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="screening", ref_id=s.id)
    return s


# ------------------------------------------------------------------ risk
def current_risk(db: Session, client_id: uuid.UUID) -> RiskAssessment | None:
    return db.execute(select(RiskAssessment).where(RiskAssessment.client_id == client_id, RiskAssessment.superseded_at.is_(None)).order_by(RiskAssessment.assessed_at.desc())).scalars().first()


def assess_risk(db: Session, client: Client, body: S.AssessIn, actor_mid: uuid.UUID | None, actor_label: str) -> RiskAssessment:
    contacts = db.execute(select(Contact).where(Contact.client_id == client.id, Contact.archived_at.is_(None))).scalars().all()
    verified_contact_ids = {v.contact_id for v in db.execute(select(Verification).where(Verification.client_id == client.id, Verification.status == "verified")).scalars() if v.contact_id}
    screenings = db.execute(select(Screening).where(Screening.client_id == client.id)).scalars().all()
    contact_ids = [c.id for c in contacts]
    has_graph = bool(contact_ids) and db.execute(select(Relationship.id).where(Relationship.to_id == client.id, Relationship.ended_at.is_(None)).limit(1)).first() is not None
    outcome = risk_engine.assess(client, contacts_total=len(contacts), contacts_verified=len([c for c in contacts if c.id in verified_contact_ids]), screenings=list(screenings), has_ownership_graph=has_graph)
    now = utcnow()
    for old in db.execute(select(RiskAssessment).where(RiskAssessment.client_id == client.id, RiskAssessment.superseded_at.is_(None))).scalars():
        old.superseded_at = now
    r = RiskAssessment(tenant_id=client.tenant_id, client_id=client.id, rating=outcome.rating, score=outcome.score, method="rules_v1", factors=outcome.factors_json(),
                       assessed_by_membership_id=actor_mid, assessed_at=now, next_review_at=now + outcome.review_delta, notes=body.notes)
    db.add(r)
    client.risk_rating, client.risk_assessed_at = outcome.rating, now   # the CRM shows this everywhere
    db.flush()
    events.emit(db, tenant_id=client.tenant_id, client_id=client.id, module_key="verify", kind="risk.assessed", summary=f"Risk rated {outcome.rating} ({outcome.score} pts) — next review {r.next_review_at.strftime('%b %Y')}",
                detail={"rating": outcome.rating, "score": outcome.score, "factors": outcome.factors_json()}, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="risk_assessment", ref_id=r.id)
    return r


# ------------------------------------------------------------------ views
def client_view(db: Session, client: Client) -> S.ClientVerifyOut:
    vs = db.execute(select(Verification).where(Verification.client_id == client.id).order_by(Verification.created_at.desc())).scalars().all()
    ss = db.execute(select(Screening).where(Screening.client_id == client.id).order_by(Screening.screened_at.desc())).scalars().all()
    contacts = db.execute(select(Contact).where(Contact.client_id == client.id, Contact.archived_at.is_(None)).order_by(Contact.is_primary.desc(), Contact.first_name)).scalars().all()
    names = member_names(db, {v.started_by_membership_id for v in vs} | {s.reviewed_by_membership_id for s in ss})
    parties = []
    for c in contacts:
        v = next((x for x in vs if x.contact_id == c.id), None)
        s = next((x for x in ss if x.contact_id == c.id), None)
        parties.append(S.PartyStatus(contact_id=c.id, name=c.full_name, role=c.role, identity_status=v.status if v else "none", identity_simulated=bool(v and v.simulated),
                                     screening_status=s.status if s else "none", screening_simulated=bool(s and s.simulated)))
    cur = current_risk(db, client.id)
    return S.ClientVerifyOut(client_id=client.id, client_name=client.name, client_type=client.client_type, risk=risk_out(cur, member_names(db, {cur.assessed_by_membership_id})) if cur else None,
                             entity_screening=next((screening_out(s, names) for s in ss if s.contact_id is None), None),
                             entity_verification=next((verification_out(v, names) for v in vs if v.contact_id is None), None),
                             parties=parties, verifications=[verification_out(v, names) for v in vs], screenings=[screening_out(s, names) for s in ss], providers=providers.provider_health())


def overview(db: Session) -> S.OverviewOut:
    now = utcnow()
    vp = db.execute(select(func.count()).select_from(Verification).where(Verification.status.in_(["pending", "in_progress"]))).scalar_one()
    vv = db.execute(select(func.count()).select_from(Verification).where(Verification.status == "verified")).scalar_one()
    sr = db.execute(select(func.count()).select_from(Screening).where(Screening.status == "potential_match", Screening.review_decision.is_(None))).scalar_one()
    due = db.execute(select(func.count()).select_from(RiskAssessment).where(RiskAssessment.superseded_at.is_(None), RiskAssessment.next_review_at <= now + timedelta(days=30))).scalar_one()
    unassessed = db.execute(select(func.count()).select_from(Client).where(Client.archived_at.is_(None), Client.risk_rating.is_(None), Client.stage.in_(["Active", "Onboarding", "Review"]))).scalar_one()
    return S.OverviewOut(verifications_pending=vp, verifications_verified=vv, screenings_to_review=sr, reviews_due_30d=due, clients_unassessed=unassessed, providers=providers.provider_health())


def reviews_due(db: Session, days: int = 30) -> list[S.ReviewDueOut]:
    now = utcnow()
    rows = db.execute(select(RiskAssessment, Client.name).join(Client, Client.id == RiskAssessment.client_id).where(RiskAssessment.superseded_at.is_(None), RiskAssessment.next_review_at <= now + timedelta(days=days), Client.archived_at.is_(None)).order_by(RiskAssessment.next_review_at)).all()
    return [S.ReviewDueOut(client_id=r.client_id, client_name=n, rating=r.rating, next_review_at=r.next_review_at, overdue=r.next_review_at < now) for r, n in rows]


def has_verified_identity(db: Session, contact_id: uuid.UUID) -> bool:
    """Used by Sign: can this person's identity be relied on right now?"""
    v = db.execute(select(Verification).where(Verification.contact_id == contact_id, Verification.status == "verified", Verification.simulated.is_(False)).order_by(Verification.completed_at.desc())).scalars().first()
    return bool(v and (v.expires_at is None or v.expires_at > utcnow()))
