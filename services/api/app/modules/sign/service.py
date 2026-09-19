from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import entitlements, events, mailer
from app.core.config import settings
from app.core.security import hash_token, new_opaque_token, utcnow
from app.core.storage import get_storage
from app.core.database import bind_tenant
from app.core.tenancy import platform_scope, set_tenant
from app.models.crm import Client
from app.models.platform import Document
from app.models.tenant import Tenant
from app.modules.sign import schemas as S
from app.modules.sign.models import Agreement, Signer, SignEvent
from app.notify import templates
from app.services import billing_service, notify_service
from app.services.crm_service import client_name_map, member_names

GENESIS = "0" * 64


# ------------------------------------------------------------------ evidence chain
def _canon(d: dict[str, Any]) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)


def record_event(db: Session, a: Agreement, kind: str, *, signer: Signer | None = None, ip: str | None = None, ua: str | None = None, detail: dict | None = None) -> SignEvent:
    prev = a.chain_head or GENESIS
    now = utcnow()
    body = {"agreement_id": str(a.id), "signer_id": str(signer.id) if signer else None, "kind": kind, "at": now.isoformat(), "ip": ip, "detail": detail or {}}
    h = hashlib.sha256((prev + _canon(body)).encode()).hexdigest()
    ev = SignEvent(tenant_id=a.tenant_id, agreement_id=a.id, signer_id=signer.id if signer else None, kind=kind, at=now, ip=ip, user_agent=(ua or "")[:300] or None, detail=detail or {}, prev_hash=prev, hash=h)
    db.add(ev)
    a.chain_head = h
    db.flush()
    return ev


def verify_chain(db: Session, a: Agreement) -> dict[str, Any]:
    rows = db.execute(select(SignEvent).where(SignEvent.agreement_id == a.id).order_by(SignEvent.at, SignEvent.id)).scalars().all()
    prev = GENESIS
    for r in rows:
        body = {"agreement_id": str(r.agreement_id), "signer_id": str(r.signer_id) if r.signer_id else None, "kind": r.kind, "at": r.at.isoformat(), "ip": r.ip, "detail": r.detail or {}}
        expect = hashlib.sha256((prev + _canon(body)).encode()).hexdigest()
        if r.prev_hash != prev or r.hash != expect:
            return {"ok": False, "events": len(rows), "first_break": str(r.id)}
        prev = r.hash
    return {"ok": True, "events": len(rows), "head": prev, "matches_agreement": prev == (a.chain_head or GENESIS)}


# ------------------------------------------------------------------ serialisers
def signer_out(s: Signer) -> S.SignerOut:
    return S.SignerOut(id=s.id, name=s.name, email=s.email, contact_id=s.contact_id, order=s.order, status=s.status, viewed_at=s.viewed_at, signed_at=s.signed_at, declined_at=s.declined_at,
                       decline_reason=s.decline_reason, signature_kind=s.signature_kind, signature_sha256=s.signature_sha256, identity_verified=s.identity_verification_id is not None)


def agreement_out(db: Session, a: Agreement, names: dict | None = None, client_names: dict | None = None) -> S.AgreementOut:
    doc = db.get(Document, a.document_id)
    names = names if names is not None else member_names(db, {a.created_by_membership_id})
    client_names = client_names if client_names is not None else client_name_map(db, {a.client_id})
    return S.AgreementOut(id=a.id, client_id=a.client_id, client_name=client_names.get(a.client_id) if a.client_id else None, document_id=a.document_id,
                          document_filename=doc.filename if doc else None, document_sha256=doc.sha256 if doc else None, title=a.title, kind=a.kind, message=a.message, status=a.status,
                          require_identity=a.require_identity, created_by_name=names.get(a.created_by_membership_id) if a.created_by_membership_id else None, sent_at=a.sent_at,
                          completed_at=a.completed_at, expires_at=a.expires_at, voided_at=a.voided_at, void_reason=a.void_reason, sealed_sha256=a.sealed_sha256, chain_head=a.chain_head,
                          signers=[signer_out(s) for s in a.signers], created_at=a.created_at)


def agreement_detail(db: Session, a: Agreement) -> S.AgreementDetail:
    base = agreement_out(db, a)
    evs = db.execute(select(SignEvent).where(SignEvent.agreement_id == a.id).order_by(SignEvent.at, SignEvent.id)).scalars().all()
    by_id = {s.id: s.name for s in a.signers}
    return S.AgreementDetail(**base.model_dump(), events=[S.SignEventOut(id=e.id, kind=e.kind, at=e.at, signer_name=by_id.get(e.signer_id) if e.signer_id else None, ip=e.ip, detail=e.detail or {}, hash=e.hash) for e in evs], certificate=a.certificate)


# ------------------------------------------------------------------ lifecycle
def create(db: Session, tenant: Tenant, body: S.AgreementIn, actor_mid: uuid.UUID, actor_label: str) -> Agreement:
    doc = db.get(Document, body.document_id)
    if doc is None or doc.deleted_at is not None:
        raise ValueError("document not found")
    if body.client_id and db.get(Client, body.client_id) is None:
        raise ValueError("client not found")
    if len({s.email.lower() for s in body.signers}) != len(body.signers):
        raise ValueError("each signer needs a distinct email")
    if body.require_identity:
        try:
            entitlements.check(db, tenant, "verify")
        except entitlements.NotEntitled:
            raise ValueError("require_identity needs the Verify module")
    a = Agreement(tenant_id=tenant.id, client_id=body.client_id, document_id=doc.id, title=body.title.strip(), kind=body.kind, message=body.message, status="draft", require_identity=body.require_identity,
                  created_by_membership_id=actor_mid, expires_at=utcnow() + timedelta(days=body.expires_in_days))
    db.add(a)
    db.flush()
    for i, s in enumerate(body.signers, start=1):
        db.add(Signer(tenant_id=tenant.id, agreement_id=a.id, contact_id=s.contact_id, name=s.name.strip(), email=s.email.lower(), order=i, status="pending"))
    db.flush()
    db.refresh(a)
    # A held document cannot be deleted while an agreement depends on it — place the hold now.
    if not doc.retention_hold:
        doc.retention_hold = True
    record_event(db, a, "created", detail={"title": a.title, "document_sha256": doc.sha256, "signers": [s.email for s in a.signers], "require_identity": a.require_identity, "by": actor_label})
    events.emit(db, tenant_id=tenant.id, client_id=a.client_id, module_key="sign", kind="agreement.created", summary=f"Agreement drafted: {a.title}", detail={"kind": a.kind, "signers": len(a.signers)},
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="agreement", ref_id=a.id)
    if body.send_now:
        send(db, tenant, a, actor_mid, actor_label)
    return a


def _signing_url(raw_token: str) -> str:
    return f"{settings.APP_PUBLIC_URL.rstrip('/')}/s/{raw_token}"  # short public path, outside the authenticated shell


def send(db: Session, tenant: Tenant, a: Agreement, actor_mid: uuid.UUID | None, actor_label: str, *, reminder: bool = False) -> int:
    if a.status in ("completed", "declined", "voided", "expired"):
        raise ValueError(f"agreement is {a.status}")
    now = utcnow()
    sent = 0
    for s in a.signers:
        if s.status in ("signed", "declined"):
            continue
        raw, h = new_opaque_token()
        s.token_hash, s.token_expires_at = h, a.expires_at
        if s.status == "pending":
            s.status = "sent"
        subject, text, html = templates.sign_request(name=s.name.split()[0], practice=tenant.name, title=a.title, message=a.message, url=_signing_url(raw),
                                                     expires=a.expires_at.strftime("%d %b %Y") if a.expires_at else None, reminder=reminder)
        mailer.queue_email(db, tenant_id=tenant.id, to=s.email, subject=subject, text=text, html=html, template="sign_reminder" if reminder else "sign_request", ref_type="signer", ref_id=s.id)
        record_event(db, a, "reminded" if reminder else "sent", signer=s, detail={"email": s.email, "by": actor_label})
        sent += 1
    if not reminder:
        a.sent_at, a.status = now, "sent" if a.status == "draft" else a.status
        billing_service.record(db, tenant_id=tenant.id, kind="envelope.sent", module_key="sign", amount_cents=0, status="metered", detail={"agreement_id": str(a.id), "signers": len(a.signers)})
        events.emit(db, tenant_id=tenant.id, client_id=a.client_id, module_key="sign", kind="agreement.sent", summary=f"Sent for signature: {a.title} → {', '.join(s.name for s in a.signers)}",
                    actor_membership_id=actor_mid, actor_label=actor_label, ref_type="agreement", ref_id=a.id)
    else:
        events.emit(db, tenant_id=tenant.id, client_id=a.client_id, module_key="sign", kind="agreement.reminded", summary=f"Reminder sent for {a.title}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="agreement", ref_id=a.id)
    db.flush()
    return sent


def void(db: Session, a: Agreement, reason: str, actor_mid: uuid.UUID, actor_label: str) -> Agreement:
    if a.status == "completed":
        raise ValueError("a completed agreement cannot be voided — issue a new one")
    a.status, a.voided_at, a.void_reason = "voided", utcnow(), reason
    for s in a.signers:
        s.token_hash = None
    record_event(db, a, "voided", detail={"reason": reason, "by": actor_label})
    events.emit(db, tenant_id=a.tenant_id, client_id=a.client_id, module_key="sign", kind="agreement.voided", summary=f"Voided: {a.title} — {reason}", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="agreement", ref_id=a.id)
    return a


# ------------------------------------------------------------------ public signing
class TokenError(Exception):
    pass


def load_by_token(db: Session, raw: str) -> tuple[Signer, Agreement, Tenant, Document]:
    with platform_scope():
        s = db.execute(select(Signer).where(Signer.token_hash == hash_token(raw))).scalar_one_or_none()
        if s is None:
            raise TokenError("invalid_link")
        a = db.get(Agreement, s.agreement_id)
        t = db.get(Tenant, s.tenant_id)
        d = db.get(Document, a.document_id)
    # The signing token is this request's tenant proof: bind the signer's tenant for the rest of the request
    # so every later query (signers, events, documents) is filtered exactly as a staff request would be.
    bind_tenant(db, s.tenant_id)
    set_tenant(s.tenant_id)
    if a.status in ("voided", "declined"):
        raise TokenError(f"agreement_{a.status}")
    if a.expires_at and a.expires_at < utcnow() and a.status != "completed":
        raise TokenError("agreement_expired")
    return s, a, t, d


def identity_ok_for(db: Session, s: Signer, a: Agreement) -> tuple[bool, uuid.UUID | None]:
    if not a.require_identity:
        return True, None
    if not s.contact_id:
        return False, None
    from app.modules.verify.models import Verification
    with platform_scope():
        v = db.execute(select(Verification).where(Verification.contact_id == s.contact_id, Verification.status == "verified", Verification.simulated.is_(False)).order_by(Verification.completed_at.desc())).scalars().first()
    ok = bool(v and (v.expires_at is None or v.expires_at > utcnow()))
    return ok, (v.id if ok else None)


def public_view(db: Session, s: Signer, a: Agreement, t: Tenant, d: Document) -> S.PublicSignerView:
    ok, _ = identity_ok_for(db, s, a)
    return S.PublicSignerView(agreement_id=a.id, title=a.title, kind=a.kind, message=a.message, practice_name=t.name, document_filename=d.filename, document_content_type=d.content_type,
                              document_sha256=d.sha256, signer_name=s.name, signer_email=s.email, signer_status=s.status, agreement_status=a.status, require_identity=a.require_identity,
                              identity_ok=ok, expires_at=a.expires_at, other_signers=[{"name": o.name, "status": o.status} for o in a.signers if o.id != s.id])


def record_view(db: Session, s: Signer, a: Agreement, ip: str | None, ua: str | None) -> None:
    if s.status == "sent":
        s.status, s.viewed_at = "viewed", utcnow()
        record_event(db, a, "viewed", signer=s, ip=ip, ua=ua)
    elif s.viewed_at is None:
        s.viewed_at = utcnow()


def sign(db: Session, s: Signer, a: Agreement, t: Tenant, d: Document, body: S.PublicSignIn, ip: str | None, ua: str | None) -> Agreement:
    if s.status in ("signed", "declined"):
        raise TokenError(f"already_{s.status}")
    if not body.consent:
        raise TokenError("consent_required")
    if body.signature_kind == "drawn" and not body.signature_data.startswith("data:image/png;base64,"):
        raise TokenError("drawn_signature_must_be_png")
    ok, vid = identity_ok_for(db, s, a)
    if not ok:
        raise TokenError("identity_required")
    now = utcnow()
    with platform_scope():
        record_event(db, a, "consented", signer=s, ip=ip, ua=ua, detail={"text": "I agree to sign electronically and that my electronic signature is binding (Electronic Transactions Act 1999)."})
        if vid:
            s.identity_verification_id = vid
            record_event(db, a, "identity_checked", signer=s, ip=ip, ua=ua, detail={"verification_id": str(vid)})
        sig_hash = hashlib.sha256(body.signature_data.encode()).hexdigest()
        s.status, s.signed_at, s.consented_at, s.signature_kind, s.signature_data, s.signature_sha256, s.ip, s.user_agent = "signed", now, now, body.signature_kind, body.signature_data, sig_hash, ip, (ua or "")[:300]
        s.name = body.full_name.strip() or s.name
        s.token_hash = None  # single use
        record_event(db, a, "signed", signer=s, ip=ip, ua=ua, detail={"signature_kind": body.signature_kind, "signature_sha256": sig_hash, "name_as_signed": s.name, "document_sha256": d.sha256})
        remaining = [x for x in a.signers if x.status != "signed"]
        if remaining:
            a.status = "partially_signed"
            events.emit(db, tenant_id=a.tenant_id, client_id=a.client_id, module_key="sign", kind="agreement.signed", summary=f"{s.name} signed {a.title} ({len(a.signers) - len(remaining)} of {len(a.signers)})", actor_label="EnTIQ Sign", ref_type="agreement", ref_id=a.id)
        else:
            _complete(db, a, t, d, now)
        db.flush()
    return a


def _complete(db: Session, a: Agreement, t: Tenant, d: Document, now) -> None:
    a.status, a.completed_at = "completed", now
    material = d.sha256 + "".join(s.signature_sha256 or "" for s in sorted(a.signers, key=lambda x: x.order)) + now.isoformat()
    a.sealed_sha256 = hashlib.sha256(material.encode()).hexdigest()
    ev = record_event(db, a, "completed", detail={"sealed_sha256": a.sealed_sha256, "document_sha256": d.sha256})
    a.certificate = {
        "version": "entiq-sign-cert-1", "agreement_id": str(a.id), "title": a.title, "kind": a.kind, "practice": t.name, "document": {"filename": d.filename, "sha256": d.sha256, "size_bytes": d.size_bytes},
        "signers": [{"name": s.name, "email": s.email, "signed_at": s.signed_at.isoformat() if s.signed_at else None, "ip": s.ip, "signature_kind": s.signature_kind, "signature_sha256": s.signature_sha256,
                     "identity_verified": s.identity_verification_id is not None} for s in a.signers],
        "sealed_sha256": a.sealed_sha256, "seal_recipe": "sha256(document_sha256 + signature_sha256[in signer order] + completed_at_iso)", "completed_at": now.isoformat(), "evidence_chain_head": ev.hash,
    }
    d.retention_hold = True  # an executed agreement's document is a legal record
    billing_service.record(db, tenant_id=a.tenant_id, kind="envelope.completed", module_key="sign", amount_cents=0, status="metered", detail={"agreement_id": str(a.id), "signers": len(a.signers)})
    events.emit(db, tenant_id=a.tenant_id, client_id=a.client_id, module_key="sign", kind="agreement.completed", summary=f"Completed: {a.title} — signed by {', '.join(s.name for s in a.signers)}",
                detail={"sealed_sha256": a.sealed_sha256}, actor_label="EnTIQ Sign", ref_type="agreement", ref_id=a.id)
    for s in a.signers:
        subject, text, html = templates.sign_completed(name=s.name.split()[0], title=a.title, practice=t.name, sealed=a.sealed_sha256 or "")
        mailer.queue_email(db, tenant_id=a.tenant_id, to=s.email, subject=subject, text=text, html=html, template="sign_completed", ref_type="agreement", ref_id=a.id)
    if a.created_by_membership_id:
        notify_service.notify(db, tenant_id=a.tenant_id, membership_id=a.created_by_membership_id, kind="agreement.completed", title=f"Signed: {a.title}", body="All parties have signed. Certificate available.", link=f"/sign/agreements/{a.id}", module_key="sign")


def decline(db: Session, s: Signer, a: Agreement, t: Tenant, body: S.PublicDeclineIn, ip: str | None, ua: str | None) -> Agreement:
    if s.status in ("signed", "declined"):
        raise TokenError(f"already_{s.status}")
    now = utcnow()
    with platform_scope():
        s.status, s.declined_at, s.decline_reason, s.ip, s.token_hash = "declined", now, body.reason, ip, None
        a.status = "declined"
        record_event(db, a, "declined", signer=s, ip=ip, ua=ua, detail={"reason": body.reason})
        events.emit(db, tenant_id=a.tenant_id, client_id=a.client_id, module_key="sign", kind="agreement.declined", summary=f"{s.name} declined to sign {a.title}: {body.reason}", actor_label="EnTIQ Sign", ref_type="agreement", ref_id=a.id)
        if a.created_by_membership_id:
            notify_service.notify(db, tenant_id=a.tenant_id, membership_id=a.created_by_membership_id, kind="agreement.declined", title=f"Declined: {a.title}", body=f"{s.name}: {body.reason}", link=f"/sign/agreements/{a.id}", module_key="sign")
        db.flush()
    return a


def document_bytes(d: Document) -> bytes:
    return get_storage().get(d.storage_key)


# ------------------------------------------------------------------ overview
def overview(db: Session) -> S.OverviewOut:
    now = utcnow()
    awaiting = db.execute(select(func.count()).select_from(Agreement).where(Agreement.status.in_(["sent", "partially_signed"]))).scalar_one()
    completed = db.execute(select(func.count()).select_from(Agreement).where(Agreement.status == "completed", Agreement.completed_at >= now - timedelta(days=30))).scalar_one()
    declined = db.execute(select(func.count()).select_from(Agreement).where(Agreement.status == "declined")).scalar_one()
    expiring = db.execute(select(func.count()).select_from(Agreement).where(Agreement.status.in_(["sent", "partially_signed"]), Agreement.expires_at <= now + timedelta(days=7))).scalar_one()
    return S.OverviewOut(awaiting=awaiting, completed_30d=completed, declined=declined, expiring_7d=expiring)


# ------------------------------------------------------------------ certificate PDF
def certificate_pdf(a: Agreement, t: Tenant) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    cert = a.certificate or {}
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 25 * mm

    def line(text: str, size: int = 10, bold: bool = False, gap: float = 5.5):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        for chunk in _wrap(text, 95 if size <= 10 else 70):
            c.drawString(20 * mm, y, chunk)
            y -= size * 0.55 * mm + gap
        if y < 30 * mm:
            c.showPage(); y = h - 25 * mm

    c.setFillColorRGB(0.055, 0.486, 0.62)
    c.rect(0, h - 12 * mm, w, 12 * mm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1); c.setFont("Helvetica-Bold", 11); c.drawString(20 * mm, h - 8 * mm, "EnTIQ Sign — Certificate of Completion")
    c.setFillColorRGB(0.125, 0.122, 0.118)
    line(cert.get("title", a.title), 16, True, 8)
    line(f"Practice: {t.name}    Agreement ID: {a.id}", 9)
    line(f"Kind: {a.kind.replace('_', ' ')}    Completed: {cert.get('completed_at', '')}", 9, gap=9)
    line("Document", 12, True)
    doc = cert.get("document", {})
    line(f"{doc.get('filename', '')}  ({doc.get('size_bytes', 0)} bytes)", 10)
    line(f"SHA-256: {doc.get('sha256', '')}", 8, gap=9)
    line("Signers", 12, True)
    for s in cert.get("signers", []):
        line(f"{s.get('name')}  <{s.get('email')}>", 10, True, 2)
        line(f"Signed {s.get('signed_at')}   IP {s.get('ip') or '—'}   Method: {s.get('signature_kind')}   Identity verified: {'yes' if s.get('identity_verified') else 'no'}", 8, gap=2)
        line(f"Signature SHA-256: {s.get('signature_sha256')}", 8, gap=7)
    line("Seal", 12, True)
    line(f"Sealed SHA-256: {cert.get('sealed_sha256', '')}", 8)
    line(f"Recipe: {cert.get('seal_recipe', '')}", 8)
    line(f"Evidence chain head: {cert.get('evidence_chain_head', '')}", 8, gap=9)
    line("Anyone holding the original document and this certificate can recompute the document hash and the seal to confirm the agreement has not been altered since signing. "
         "Consent to sign electronically was recorded for every signer under the Electronic Transactions Act 1999 (Cth).", 8)
    c.showPage(); c.save()
    return buf.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > width:
            out.append(cur); cur = wd
        else:
            cur = f"{cur} {wd}".strip()
    if cur:
        out.append(cur)
    return out or [""]
