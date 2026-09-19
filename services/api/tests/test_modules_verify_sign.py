"""M5: Verify (simulation providers in tests) and Sign, including the identity interlink."""
import base64
import io

from tests.conftest import STRONG_PW, auth, signup

C = "/api/v1"
PNG_1x1 = "data:image/png;base64," + base64.b64encode(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da6360000000020001e221bc330000000049454e44ae426082")).decode()


def _setup(client, modules=("verify", "sign")):
    out = signup(client)
    h = auth(out["tokens"])
    for m in modules:
        client.post(f"{C}/subscriptions", headers=h, json={"module_key": m})
    c = client.post(f"{C}/crm/clients", headers=h, json={"name": "Ashfield Family Trust", "client_type": "Trust", "abn": "62 114 887 302", "stage": "Active"}).json()
    p1 = client.post(f"{C}/crm/clients/{c['id']}/contacts", headers=h, json={"first_name": "Margaret", "last_name": "Ashfield", "role": "Trustee", "is_primary": True, "email": "margaret@ashfield.example"}).json()
    p2 = client.post(f"{C}/crm/clients/{c['id']}/contacts", headers=h, json={"first_name": "Tom", "last_name": "Ashfield", "role": "Beneficiary", "email": "tom@ashfield.example"}).json()
    return h, c, p1, p2


def _doc(client, h, cid):
    return client.post(f"{C}/documents", headers=h, files={"file": ("Engagement Letter.pdf", io.BytesIO(b"%PDF-1.4 engagement letter FY27 " * 50), "application/pdf")}, data={"client_id": cid, "kind": "agreement"}).json()


# ------------------------------------------------------------------ Verify
def test_verify_gate_and_simulated_identity_screening_risk_flow(client):
    out = signup(client)
    h = auth(out["tokens"])
    assert client.get(f"{C}/verify/overview", headers=h).status_code == 403          # not subscribed
    client.post(f"{C}/subscriptions", headers=h, json={"module_key": "verify"})
    ov = client.get(f"{C}/verify/overview", headers=h).json()
    assert ov["providers"]["identity"]["provider"] == "simulation" and ov["providers"]["identity"]["live"] is False
    c = client.post(f"{C}/crm/clients", headers=h, json={"name": "Marlow Constructions Pty Ltd", "client_type": "Company", "abn": "48 902 337 115", "stage": "Active"}).json()
    p = client.post(f"{C}/crm/clients/{c['id']}/contacts", headers=h, json={"first_name": "Gavin", "last_name": "Marlow", "role": "Director", "is_primary": True}).json()
    # identity — simulation completes instantly and is marked as such
    v = client.post(f"{C}/verify/clients/{c['id']}/verifications", headers=h, json={"subject_type": "individual", "contact_id": p["id"]})
    assert v.status_code == 201, v.text
    v = v.json()
    assert v["status"] == "verified" and v["simulated"] is True and v["provider"] == "simulation" and v["expires_at"]
    assert client.post(f"{C}/verify/clients/{c['id']}/verifications", headers=h, json={"subject_type": "individual"}).status_code == 400  # contact required
    # a subject named *fail* is declined by the simulation
    pf = client.post(f"{C}/crm/clients/{c['id']}/contacts", headers=h, json={"first_name": "Will", "last_name": "Failsworth"}).json()
    assert client.post(f"{C}/verify/clients/{c['id']}/verifications", headers=h, json={"subject_type": "individual", "contact_id": pf["id"]}).json()["status"] == "failed"
    # screening — clear for the entity, a synthetic hit for a PEP-named person
    s = client.post(f"{C}/verify/clients/{c['id']}/screen", headers=h, json={}).json()
    assert s["status"] == "clear" and s["subject_type"] == "entity" and s["simulated"] is True
    pep = client.post(f"{C}/crm/clients/{c['id']}/contacts", headers=h, json={"first_name": "Peppa", "last_name": "Politically-Exposed"}).json()
    hit = client.post(f"{C}/verify/clients/{c['id']}/screen", headers=h, json={"contact_id": pep["id"]}).json()
    assert hit["status"] == "potential_match" and hit["match_count"] == 1 and hit["matches"][0]["topics"] == ["role.pep"]
    assert len(client.get(f"{C}/verify/screenings", headers=h, params={"review_queue": True}).json()) == 1
    # risk — unreviewed hit + identity gaps + no ownership graph → Medium
    r = client.post(f"{C}/verify/clients/{c['id']}/assess", headers=h, json={}).json()
    factors = {f["factor"] for f in r["factors"]}
    assert {"entity_type", "screening_pending", "identity_gaps", "ownership_unknown"} <= factors
    assert r["rating"] == "Medium" and 30 <= r["score"] < 60
    assert client.get(f"{C}/crm/clients/{c['id']}", headers=h).json()["risk_rating"] == "Medium"   # written onto the CRM record
    # review the hit as a true match → risk re-assessed to High automatically
    rv = client.post(f"{C}/verify/screenings/{hit['id']}/review", headers=h, json={"decision": "true_match", "notes": "Confirmed via DFAT list"}).json()
    assert rv["status"] == "confirmed_match" and rv["reviewed_by_name"] == "Priya Nair"
    cl = client.get(f"{C}/crm/clients/{c['id']}", headers=h).json()
    assert cl["risk_rating"] == "High"
    hist = client.get(f"{C}/verify/clients/{c['id']}/risk-history", headers=h).json()
    assert len(hist) == 2 and hist[0]["rating"] == "High"
    # client verify view + reviews due (High → 6 months, not within 30 days)
    cv = client.get(f"{C}/verify/clients/{c['id']}", headers=h).json()
    assert cv["risk"]["rating"] == "High" and cv["entity_screening"]["status"] == "clear"
    assert {p_["name"]: p_["identity_status"] for p_ in cv["parties"]}["Gavin Marlow"] == "verified"
    assert client.get(f"{C}/verify/reviews-due", headers=h).json() == []
    assert client.get(f"{C}/verify/reviews-due", headers=h, params={"days": 365}).json()[0]["rating"] == "High"
    # metered billing + timeline
    kinds = [e["kind"] for e in client.get(f"{C}/billing/events", headers=h).json()]
    assert kinds.count("verification.started") == 2 and "screening.run" in kinds
    tl = [e["kind"] for e in client.get(f"{C}/crm/clients/{c['id']}/timeline", headers=h).json()]
    assert {"verification.completed", "screening.clear", "screening.potential_match", "risk.assessed", "screening.reviewed"} <= set(tl)


def test_verify_webhook_updates_by_provider_ref_without_auth(client):
    from app.core.database import SessionLocal
    from app.core.tenancy import platform_scope
    from app.modules.verify.models import Verification
    h, c, p1, _ = _setup(client, modules=("verify",))
    v = client.post(f"{C}/verify/clients/{c['id']}/verifications", headers=h, json={"subject_type": "individual", "contact_id": p1["id"]}).json()
    # pretend this one came from Didit and is still in progress
    with SessionLocal() as db, platform_scope():
        row = db.get(Verification, __import__("uuid").UUID(v["id"]))
        row.provider, row.provider_ref, row.status, row.simulated, row.completed_at = "didit", "sess_123", "in_progress", False, None
        db.commit()
    r = client.post(f"{C}/verify/webhooks/didit", json={"session_id": "sess_123", "status": "Approved"})
    assert r.status_code == 202 and r.json()["matched"] is True
    assert client.get(f"{C}/verify/verifications", headers=h).json()[0]["status"] == "verified"
    assert client.post(f"{C}/verify/webhooks/didit", json={"session_id": "unknown", "status": "Approved"}).json()["matched"] is False


# ------------------------------------------------------------------ Sign
def test_sign_full_flow_two_signers_seal_certificate_and_evidence_chain(client):
    h, c, p1, p2 = _setup(client)
    d = _doc(client, h, c["id"])
    r = client.post(f"{C}/sign/agreements", headers=h, json={"title": "FY27 Engagement Letter", "document_id": d["id"], "client_id": c["id"], "kind": "engagement_letter", "message": "Please sign by Friday.",
                                                            "signers": [{"name": "Margaret Ashfield", "email": "margaret@ashfield.example", "contact_id": p1["id"]}, {"name": "Tom Ashfield", "email": "tom@ashfield.example", "contact_id": p2["id"]}]})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["status"] == "sent" and [s["status"] for s in a["signers"]] == ["sent", "sent"] and a["sent_at"]
    assert [e["kind"] for e in a["events"]] == ["created", "sent", "sent"]
    # the document is now under hold
    docs = client.get(f"{C}/documents", headers=h, params={"client_id": c["id"]}).json()
    assert docs[0]["retention_hold"] is True
    # signing links were emailed
    out = client.get(f"{C}/dev/outbound", headers=h).json()
    links = {m["to_address"]: m["body_text"].split("Review and sign:\n")[1].split("\n")[0] for m in out if m["template"] == "sign_request"}
    assert set(links) == {"margaret@ashfield.example", "tom@ashfield.example"}
    tok_m = links["margaret@ashfield.example"].rsplit("/", 1)[1]
    tok_t = links["tom@ashfield.example"].rsplit("/", 1)[1]
    # public: view (no auth) → viewed; document downloadable through the token
    pv = client.get(f"{C}/sign/public/{tok_m}")
    assert pv.status_code == 200 and pv.json()["signer_status"] == "viewed" and pv.json()["practice_name"] == "Ashfield Partners" and pv.json()["identity_ok"] is True
    pd = client.get(f"{C}/sign/public/{tok_m}/document")
    assert pd.status_code == 200 and pd.headers["x-content-sha256"] == d["sha256"]
    # consent is mandatory
    assert client.post(f"{C}/sign/public/{tok_m}/sign", json={"full_name": "Margaret Ashfield", "signature_kind": "typed", "signature_data": "Margaret Ashfield", "consent": False}).status_code == 400
    # first signer signs (typed) → partially signed
    s1 = client.post(f"{C}/sign/public/{tok_m}/sign", json={"full_name": "Margaret Ashfield", "signature_kind": "typed", "signature_data": "Margaret Ashfield", "consent": True})
    assert s1.status_code == 200 and s1.json()["signer_status"] == "signed" and s1.json()["agreement_status"] == "partially_signed"
    assert client.get(f"{C}/sign/public/{tok_m}").status_code == 404   # single-use token is gone
    # second signer signs (drawn PNG) → completed + sealed
    bad = client.post(f"{C}/sign/public/{tok_t}/sign", json={"full_name": "Tom Ashfield", "signature_kind": "drawn", "signature_data": "not-a-png", "consent": True})
    assert bad.status_code == 400
    s2 = client.post(f"{C}/sign/public/{tok_t}/sign", json={"full_name": "Tom Ashfield", "signature_kind": "drawn", "signature_data": PNG_1x1, "consent": True})
    assert s2.status_code == 200 and s2.json()["agreement_status"] == "completed"
    det = client.get(f"{C}/sign/agreements/{a['id']}", headers=h).json()
    assert det["status"] == "completed" and det["sealed_sha256"] and det["certificate"]["sealed_sha256"] == det["sealed_sha256"]
    assert det["certificate"]["document"]["sha256"] == d["sha256"] and len(det["certificate"]["signers"]) == 2
    kinds = [e["kind"] for e in det["events"]]
    assert kinds[:3] == ["created", "sent", "sent"] and kinds[-1] == "completed" and kinds.count("signed") == 2 and kinds.count("consented") == 2
    chain = client.get(f"{C}/sign/agreements/{a['id']}/verify-chain", headers=h).json()
    assert chain["ok"] is True and chain["matches_agreement"] is True and chain["head"] == det["certificate"]["evidence_chain_head"]
    pdf = client.get(f"{C}/sign/agreements/{a['id']}/certificate.pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 1500
    # completion emails, creator notification, billing, timeline
    templates = [m["template"] for m in client.get(f"{C}/dev/outbound", headers=h).json()]
    assert templates.count("sign_completed") == 2
    assert any(n["kind"] == "agreement.completed" for n in client.get(f"{C}/notifications", headers=h).json())
    kinds = [e["kind"] for e in client.get(f"{C}/billing/events", headers=h).json()]
    assert "envelope.sent" in kinds and "envelope.completed" in kinds
    tl = [e["kind"] for e in client.get(f"{C}/crm/clients/{c['id']}/timeline", headers=h).json()]
    assert {"agreement.created", "agreement.sent", "agreement.signed", "agreement.completed"} <= set(tl)
    # completed agreements cannot be voided; the held document cannot be deleted
    assert client.post(f"{C}/sign/agreements/{a['id']}/void", headers=h, json={"reason": "oops"}).status_code == 400
    assert client.delete(f"{C}/documents/{d['id']}", headers=h).status_code == 409
    assert client.get(f"{C}/sign/overview", headers=h).json()["completed_30d"] == 1


def test_sign_decline_void_remind_and_isolation(client):
    h, c, p1, _ = _setup(client)
    d = _doc(client, h, c["id"])
    a = client.post(f"{C}/sign/agreements", headers=h, json={"title": "Trust Resolution", "document_id": d["id"], "client_id": c["id"], "kind": "resolution", "signers": [{"name": "Margaret Ashfield", "email": "margaret@ashfield.example"}]}).json()
    tok = [m for m in client.get(f"{C}/dev/outbound", headers=h).json() if m["template"] == "sign_request"][0]["body_text"].split("Review and sign:\n")[1].split("\n")[0].rsplit("/", 1)[1]
    # remind re-issues a link and records an event
    rem = client.post(f"{C}/sign/agreements/{a['id']}/remind", headers=h).json()
    assert "reminded" in [e["kind"] for e in rem["events"]]
    assert client.get(f"{C}/sign/public/{tok}").status_code == 404     # old link rotated
    tok2 = [m for m in client.get(f"{C}/dev/outbound", headers=h).json() if m["template"] == "sign_reminder"][0]["body_text"].split("Review and sign:\n")[1].split("\n")[0].rsplit("/", 1)[1]
    dec = client.post(f"{C}/sign/public/{tok2}/decline", json={"reason": "Wrong entity name"})
    assert dec.status_code == 200 and dec.json()["agreement_status"] == "declined"
    assert any(n["kind"] == "agreement.declined" for n in client.get(f"{C}/notifications", headers=h).json())
    # a second agreement can be voided while pending
    a2 = client.post(f"{C}/sign/agreements", headers=h, json={"title": "Draft", "document_id": d["id"], "signers": [{"name": "X", "email": "x@y.example"}], "send_now": False}).json()
    assert a2["status"] == "draft"
    v = client.post(f"{C}/sign/agreements/{a2['id']}/void", headers=h, json={"reason": "superseded"}).json()
    assert v["status"] == "voided"
    # another tenant sees nothing
    b = signup(client, practice="B Co", email="b@b.example")
    hb = auth(b["tokens"])
    client.post(f"{C}/subscriptions", headers=hb, json={"module_key": "sign"})
    assert client.get(f"{C}/sign/agreements/{a['id']}", headers=hb).status_code == 404
    assert client.get(f"{C}/sign/agreements", headers=hb).json() == []


def test_sign_requires_verified_identity_when_asked(client):
    h, c, p1, _ = _setup(client)
    d = _doc(client, h, c["id"])
    a = client.post(f"{C}/sign/agreements", headers=h, json={"title": "Declaration", "document_id": d["id"], "client_id": c["id"], "kind": "declaration", "require_identity": True,
                                                            "signers": [{"name": "Margaret Ashfield", "email": "margaret@ashfield.example", "contact_id": p1["id"]}]}).json()
    tok = [m for m in client.get(f"{C}/dev/outbound", headers=h).json() if m["template"] == "sign_request"][0]["body_text"].split("Review and sign:\n")[1].split("\n")[0].rsplit("/", 1)[1]
    pv = client.get(f"{C}/sign/public/{tok}").json()
    assert pv["require_identity"] is True and pv["identity_ok"] is False          # no real verification on file
    r = client.post(f"{C}/sign/public/{tok}/sign", json={"full_name": "Margaret Ashfield", "signature_kind": "typed", "signature_data": "M Ashfield", "consent": True})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "identity_required"
    # a SIMULATED verification does not count as identity evidence
    client.post(f"{C}/verify/clients/{c['id']}/verifications", headers=h, json={"subject_type": "individual", "contact_id": p1["id"]})
    assert client.get(f"{C}/sign/public/{tok}").json()["identity_ok"] is False
    # …but a real (non-simulated) verified record does
    from app.core.database import SessionLocal
    from app.core.tenancy import platform_scope
    from app.modules.verify.models import Verification
    with SessionLocal() as db, platform_scope():
        row = db.execute(__import__("sqlalchemy").select(Verification)).scalars().first()
        row.provider, row.simulated = "didit", False
        db.commit()
    assert client.get(f"{C}/sign/public/{tok}").json()["identity_ok"] is True
    ok = client.post(f"{C}/sign/public/{tok}/sign", json={"full_name": "Margaret Ashfield", "signature_kind": "typed", "signature_data": "M Ashfield", "consent": True})
    assert ok.status_code == 200 and ok.json()["agreement_status"] == "completed"
    det = client.get(f"{C}/sign/agreements/{a['id']}", headers=h).json()
    assert det["signers"][0]["identity_verified"] is True and "identity_checked" in [e["kind"] for e in det["events"]]
    # require_identity is refused for a tenant without Verify
    b = signup(client, practice="B Co", email="b@b.example")
    hb = auth(b["tokens"])
    client.post(f"{C}/subscriptions", headers=hb, json={"module_key": "sign"})
    db_ = client.post(f"{C}/documents", headers=hb, files={"file": ("x.pdf", io.BytesIO(b"%PDF x" * 20), "application/pdf")}).json()
    r = client.post(f"{C}/sign/agreements", headers=hb, json={"title": "T", "document_id": db_["id"], "require_identity": True, "signers": [{"name": "A", "email": "a@a.example"}]})
    assert r.status_code == 400 and "Verify" in r.json()["detail"]["message"]


def test_sign_expiry_via_lifecycle_job(client):
    from datetime import timedelta
    from app.core.database import SessionLocal
    from app.core.security import utcnow
    from app.jobs import lifecycle
    h, c, p1, _ = _setup(client)
    d = _doc(client, h, c["id"])
    a = client.post(f"{C}/sign/agreements", headers=h, json={"title": "Short fuse", "document_id": d["id"], "client_id": c["id"], "expires_in_days": 1, "signers": [{"name": "Margaret Ashfield", "email": "margaret@ashfield.example"}]}).json()
    tok = [m for m in client.get(f"{C}/dev/outbound", headers=h).json() if m["template"] == "sign_request"][0]["body_text"].split("Review and sign:\n")[1].split("\n")[0].rsplit("/", 1)[1]
    assert client.get(f"{C}/sign/public/{tok}").status_code == 200
    with SessionLocal() as db:
        stats = lifecycle.run(db, now=utcnow() + timedelta(days=2))
    assert stats["agreements_expired"] == 1
    det = client.get(f"{C}/sign/agreements/{a['id']}", headers=h).json()
    assert det["status"] == "expired" and det["events"][-1]["kind"] == "expired"
    assert client.get(f"{C}/sign/public/{tok}").status_code == 404
    assert "agreement.expired" in [e["kind"] for e in client.get(f"{C}/crm/clients/{c['id']}/timeline", headers=h).json()]
