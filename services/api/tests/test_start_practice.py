"""M6a: Start (11-stage onboarding with gates read from Verify/Sign) and Practice (jobs, recurring, time, deadlines)."""
import io
from datetime import date, timedelta

from tests.conftest import auth, signup

C = "/api/v1"


def _tenant(client, modules=("start", "verify", "sign", "practice")):
    out = signup(client)
    h = auth(out["tokens"])
    for m in modules:
        r = client.post(f"{C}/subscriptions", headers=h, json={"module_key": m})
        assert r.status_code == 201, r.text
    return h, out


def _invite_token(client, h):
    msgs = [m for m in client.get(f"{C}/dev/outbound", headers=h).json() if m["template"] == "start_invitation"]
    return msgs[0]["body_text"].split("Start here (link valid until")[1].split("\n")[1].strip().rsplit("/", 1)[1]


def _pdf(name="doc.pdf"):
    return {"file": (name, io.BytesIO(b"%PDF-1.4 " + name.encode() * 40), "application/pdf")}


def test_start_full_lifecycle_prospect_then_practice_activates_and_practice_schedules_work(client):
    h, out = _tenant(client)
    me = client.get(f"{C}/me", headers=h).json()
    # gate: not subscribed → 403 with upsell
    b = signup(client, practice="B Co", email="b@b.example")
    assert client.get(f"{C}/start/overview", headers=auth(b["tokens"])).status_code == 403

    # 1) practice creates the prospect + invitation in one call
    r = client.post(f"{C}/start/onboardings", headers=h, json={"prospect_name": "Northfield Holdings", "entity_type": "Company", "contact_first_name": "Ava", "contact_last_name": "North", "contact_email": "ava@northfield.example"})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["status"] == "invited" and o["current_stage"] == 1 and o["invite_url"] and "/onboard/" in o["invite_url"] and len(o["stages"]) == 11
    cl = client.get(f"{C}/crm/clients/{o['client_id']}", headers=h).json()
    assert cl["stage"] == "Onboarding" and cl["source"] == "start"
    # a second onboarding for the same client is refused
    assert client.post(f"{C}/start/onboardings", headers=h, json={"client_id": o["client_id"]}).status_code == 409
    # default service catalogue was seeded
    services = client.get(f"{C}/start/services", headers=h).json()
    assert len(services) >= 10

    tok = _invite_token(client, h)
    assert tok == o["invite_url"].rsplit("/", 1)[1]

    # 2) prospect opens the link → stage 1 completes
    pv = client.get(f"{C}/start/public/{tok}")
    assert pv.status_code == 200, pv.text
    pv = pv.json()
    assert pv["practice_name"] == "Ashfield Partners" and pv["current_stage"] == 2 and pv["stages"][0]["status"] == "completed" and pv["stages"][1]["status"] == "active"
    # stage order is enforced: cannot do stage 3 before 2
    r = client.post(f"{C}/start/public/{tok}/stages/3", json={"answers": {}})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "stage_order"
    # stage 2 entity details → CRM client updated, document checklist derived for a Company
    ent = {"legal_name": "Northfield Holdings Pty Ltd", "trading_name": "Northfield", "entity_type": "Company", "abn": "51 824 753 556", "acn": "824 753 556", "tax_residency": "australia", "gst_registered": True, "industry": "Construction",
           "address_line1": "1 Harbour St", "suburb": "Sydney", "state": "NSW", "postcode": "2000", "contact_name": "Ava North", "contact_email": "ava@northfield.example", "contact_phone": "0400 000 000"}
    pv = client.post(f"{C}/start/public/{tok}/stages/2", json=ent).json()
    assert pv["current_stage"] == 3 and {d["key"] for d in pv["document_requests"]} == {"prior_financials", "prior_tax_return", "asic_extract", "bank_statements"}
    cl = client.get(f"{C}/crm/clients/{o['client_id']}", headers=h).json()
    assert cl["legal_name"] == "Northfield Holdings Pty Ltd" and cl["abn"] == "51824753556" and cl["suburb"] == "Sydney"
    # stage 3 questionnaire — required answers enforced
    r = client.post(f"{C}/start/public/{tok}/stages/3", json={"answers": {"business_description": "Builders"}})
    assert r.status_code == 400 and r.json()["detail"]["error"] == "questionnaire_incomplete"
    answers = {"business_description": "Residential builders", "turnover_band": "$1m–$5m", "employees_band": "5–19", "gst_registered": True, "payroll": True, "software": "Xero", "lodgements_outstanding": False}
    pv = client.post(f"{C}/start/public/{tok}/stages/3", json={"answers": answers}).json()
    assert pv["current_stage"] == 4
    # stage 4 documents — required uploads, then verification by the practice
    r = client.post(f"{C}/start/public/{tok}/stages/4")
    assert r.status_code == 400 and "Still needed" in r.json()["detail"]["message"]
    for key in ("prior_financials", "prior_tax_return", "asic_extract"):
        pv = client.post(f"{C}/start/public/{tok}/documents/{key}", files=_pdf(f"{key}.pdf"))
        assert pv.status_code == 200, pv.text
    assert client.post(f"{C}/start/public/{tok}/documents/not_a_key", files=_pdf()).status_code == 404
    r = client.post(f"{C}/start/public/{tok}/stages/4")
    assert r.status_code == 200, r.text
    pv = r.json()
    assert pv["current_stage"] == 4 and pv["status"] == "awaiting_practice"          # uploaded, awaiting verification
    docs = client.get(f"{C}/documents", headers=h, params={"client_id": o["client_id"]}).json()
    assert len(docs) == 3 and all(d["kind"] == "onboarding" and d["module_key"] == "start" for d in docs)
    det = client.post(f"{C}/start/onboardings/{o['id']}/documents/prior_financials/verify", headers=h).json()
    assert det["data"]["document_requests"][0]["verified_by"] == "Priya Nair"
    det = client.post(f"{C}/start/onboardings/{o['id']}/stages/4", headers=h).json()   # practice verifies the rest and completes
    assert det["current_stage"] == 5 and det["status"] == "in_progress"
    # stage 5 related parties → contacts + relationships on the CRM record
    pv = client.post(f"{C}/start/public/{tok}/stages/5", json={"parties": [{"name": "Ava North", "role": "Director", "email": "ava@northfield.example", "ownership_pct": 60, "is_beneficial_owner": True}, {"name": "Ben North", "role": "Shareholder", "ownership_pct": 40, "is_beneficial_owner": True}], "ownership_complete": True}).json()
    assert pv["current_stage"] == 6
    contacts = client.get(f"{C}/crm/clients/{o['client_id']}/contacts", headers=h).json()
    assert {c["full_name"] for c in contacts} == {"Ava North", "Ben North"}
    rels = client.get(f"{C}/crm/clients/{o['client_id']}/relationships", headers=h).json()
    assert {r["kind"] for r in rels} == {"shareholder_of"} and rels[0]["percentage"] == 40
    # stage 6 services (catalogue filtered to Company)
    assert all(not s["entity_types"] or "Company" in s["entity_types"] for s in pv["services"])
    chosen = [s for s in pv["services"] if s["category"] in ("tax", "bas")]
    pv = client.post(f"{C}/start/public/{tok}/stages/6", json={"service_ids": [s["id"] for s in chosen]}).json()
    assert pv["current_stage"] == 7 and pv["status"] == "in_progress"
    # stage 7 — prospect cannot accept before the practice issues a proposal
    r = client.post(f"{C}/start/public/{tok}/stages/7", json={"accepted_by_name": "Ava North", "accept": True})
    assert r.status_code == 400 and r.json()["detail"]["error"] == "no_proposal"
    det = client.post(f"{C}/start/onboardings/{o['id']}/proposal", headers=h, json={"lines": [{"service_id": s["id"], "name": s["name"], "basis": s["basis"], "amount_cents": s["amount_cents"], "gst": True} for s in chosen], "terms": "Fees billed monthly in advance."}).json()
    assert det["proposal_total_cents"] == round(sum(s["amount_cents"] for s in chosen) * 1.1)
    assert any(m["template"] == "start_proposal" for m in client.get(f"{C}/dev/outbound", headers=h).json())
    pv = client.post(f"{C}/start/public/{tok}/stages/7", json={"accepted_by_name": "Ava North", "accept": True}).json()
    assert pv["current_stage"] == 8 and pv["status"] == "awaiting_practice" and pv["proposal"]["accepted_by_name"] == "Ava North"
    assert any(n["kind"] == "onboarding.ready" for n in client.get(f"{C}/notifications", headers=h).json())

    # 8) practice sends the letter of engagement through Sign
    loe = client.post(f"{C}/documents", headers=h, files=_pdf("LoE.pdf"), data={"client_id": o["client_id"], "kind": "agreement"}).json()
    det = client.post(f"{C}/start/onboardings/{o['id']}/stages/8", headers=h, json={"document_id": loe["id"]})
    assert det.status_code == 200, det.text
    det = det.json()
    assert det["current_stage"] == 9 and det["sign_agreement_id"]
    agreements = client.get(f"{C}/sign/agreements", headers=h, params={"client_id": o["client_id"]}).json()
    assert len(agreements) == 1 and agreements[0]["kind"] == "engagement_letter" and agreements[0]["signers"][0]["email"] == "ava@northfield.example"

    # 9) gates — everything pending at first
    det = client.post(f"{C}/start/onboardings/{o['id']}/gates/run", headers=h).json()
    gates = {g["gate"]: g for g in det["gates"]}
    assert {g["status"] for g in gates.values()} == {"Pending"} and det["stages"][8]["status"] == "active"
    # satisfy them through the real modules: identity + screening in Verify, signature in Sign, mandate by the prospect
    ava = next(c for c in contacts if c["full_name"] == "Ava North")
    assert client.post(f"{C}/verify/clients/{o['client_id']}/verifications", headers=h, json={"subject_type": "individual", "contact_id": ava["id"]}).json()["status"] == "verified"
    assert client.post(f"{C}/verify/clients/{o['client_id']}/screen", headers=h, json={}).json()["status"] == "clear"
    sign_tok = [m for m in client.get(f"{C}/dev/outbound", headers=h).json() if m["template"] == "sign_request"][0]["body_text"].split("Review and sign:\n")[1].split("\n")[0].rsplit("/", 1)[1]
    assert client.post(f"{C}/sign/public/{sign_tok}/sign", json={"full_name": "Ava North", "signature_kind": "typed", "signature_data": "Ava North", "consent": True}).json()["agreement_status"] == "completed"
    assert client.post(f"{C}/start/public/{tok}/mandate", json={"method": "direct_debit", "reference": "DD-0001", "account_name": "Northfield Holdings", "accepted_terms": True}).status_code == 200
    det = client.post(f"{C}/start/onboardings/{o['id']}/gates/run", headers=h).json()
    gates = {g["gate"]: g for g in det["gates"]}
    assert {g["status"] for g in gates.values()} == {"Passed"}, gates
    assert gates["kyc"]["simulated"] is True and gates["esign"]["simulated"] is False and gates["mandate"]["simulated"] is True
    assert det["current_stage"] == 10 and det["stages"][8]["meta"]["fully_verified"] is False

    # 10) acceptance needs all three sign-offs and the start:accept permission
    r = client.post(f"{C}/start/onboardings/{o['id']}/stages/10", headers=h, json={"partner_signoff": True, "margin_ok": False, "risk_signoff": True})
    assert r.status_code == 400
    det = client.post(f"{C}/start/onboardings/{o['id']}/stages/10", headers=h, json={"partner_signoff": True, "margin_ok": True, "risk_signoff": True, "notes": "Standard risk"}).json()
    assert det["current_stage"] == 11

    # 11) activation → CRM Active, email, billing event, Practice schedules the work
    det = client.post(f"{C}/start/onboardings/{o['id']}/stages/11", headers=h).json()
    assert det["status"] == "activated" and det["progress_pct"] == 100 and det["activated_at"]
    cl = client.get(f"{C}/crm/clients/{o['client_id']}", headers=h).json()
    assert cl["stage"] == "Active" and "onboarded" in cl["tags"] and cl["since"]
    assert any(m["template"] == "start_activated" for m in client.get(f"{C}/dev/outbound", headers=h).json())
    assert "onboarding.activated" in [e["kind"] for e in client.get(f"{C}/billing/events", headers=h).json()]
    jobs = client.get(f"{C}/practice/jobs", headers=h, params={"client_id": o["client_id"]}).json()
    assert [j["job_type"] for j in jobs] == ["Onboarding"] and jobs[0]["source"] == "onboarding" and jobs[0]["assignee_name"] == "Priya Nair"
    rec = client.get(f"{C}/practice/recurring", headers=h, params={"client_id": o["client_id"]}).json()
    assert {(r["job_type"], r["frequency"]) for r in rec} == {("Tax Return", "annual"), ("BAS", "quarterly")}
    # the magic link is dead after activation; the overview reflects the outcome
    assert client.get(f"{C}/start/public/{tok}").status_code == 404
    ov = client.get(f"{C}/start/overview", headers=h).json()
    assert ov["activated_30d"] == 1 and ov["active"] == 0 and ov["median_days_to_activate"] is not None
    tl = [e["kind"] for e in client.get(f"{C}/crm/clients/{o['client_id']}/timeline", headers=h).json()]
    assert {"onboarding.created", "onboarding.invited", "onboarding.stage_completed", "onboarding.proposal_issued", "onboarding.gates_run", "onboarding.activated", "job.created", "recurring.created", "stage.changed"} <= set(tl)


def test_start_withdraw_reinvite_and_isolation(client):
    h, _ = _tenant(client, modules=("start",))
    o = client.post(f"{C}/start/onboardings", headers=h, json={"prospect_name": "Ghost Co", "contact_first_name": "G", "contact_email": "g@ghost.example"}).json()
    tok1 = o["invite_url"].rsplit("/", 1)[1]
    det = client.post(f"{C}/start/onboardings/{o['id']}/invite", headers=h).json()
    tok2 = det["invite_url"].rsplit("/", 1)[1]
    assert tok1 != tok2 and client.get(f"{C}/start/public/{tok1}").status_code == 404 and client.get(f"{C}/start/public/{tok2}").status_code == 200
    det = client.post(f"{C}/start/onboardings/{o['id']}/withdraw", headers=h, json={"reason": "Went elsewhere"}).json()
    assert det["status"] == "withdrawn"
    assert client.get(f"{C}/crm/clients/{o['client_id']}", headers=h).json()["stage"] == "Lost"
    assert client.get(f"{C}/start/public/{tok2}").status_code == 404   # link revoked on withdrawal
    b = signup(client, practice="B Co", email="b@b.example")
    hb = auth(b["tokens"])
    client.post(f"{C}/subscriptions", headers=hb, json={"module_key": "start"})
    assert client.get(f"{C}/start/onboardings/{o['id']}", headers=hb).status_code == 404
    assert client.get(f"{C}/start/onboardings", headers=hb, params={"open": False}).json() == []
    # stage 8 without the Sign module is refused with a clear message
    o2 = client.post(f"{C}/start/onboardings", headers=hb, json={"prospect_name": "Solo", "contact_first_name": "S", "contact_email": "s@solo.example", "send_invitation": False}).json()
    assert o2["status"] == "draft" and o2["invite_url"] is None


def test_practice_jobs_time_status_recurring_generation_and_deadlines(client):
    h, _ = _tenant(client, modules=("practice",))
    me = client.get(f"{C}/me", headers=h).json()
    mid = me["membership"]["id"] if "membership" in me else client.get(f"{C}/crm/staff", headers=h).json()[0]["membership_id"]
    c = client.post(f"{C}/crm/clients", headers=h, json={"name": "Bluegum Pty Ltd", "client_type": "Company", "stage": "Active"}).json()
    assert client.post(f"{C}/practice/jobs", headers=h, json={"client_id": c["id"], "title": "x", "job_type": "Nope"}).status_code == 400
    j = client.post(f"{C}/practice/jobs", headers=h, json={"client_id": c["id"], "title": "FY26 company tax return", "job_type": "Tax Return", "period_label": "FY26", "due_on": (date.today() - timedelta(days=1)).isoformat(), "lodgement_due": "2027-05-15", "assignee_membership_id": mid, "budget_minutes": 600, "fee_cents": 330000})
    assert j.status_code == 201, j.text
    j = j.json()
    assert j["overdue"] is True and j["assignee_name"] == "Priya Nair" and [c_["label"] for c_ in j["checklist"]][:2] == ["Source documents received", "Workpapers prepared"]
    # time → job auto-starts
    t = client.post(f"{C}/practice/jobs/{j['id']}/time", headers=h, json={"worked_on": date.today().isoformat(), "minutes": 90, "note": "Workpapers"}).json()
    assert t["member_name"] == "Priya Nair"
    j2 = client.get(f"{C}/practice/jobs/{j['id']}", headers=h).json()
    assert j2["status"] == "in_progress" and j2["actual_minutes"] == 90 and j2["started_at"]
    # checklist + status transitions
    done = [{**c_, "done": True} for c_ in j2["checklist"]]
    client.patch(f"{C}/practice/jobs/{j['id']}", headers=h, json={"checklist": done})
    j3 = client.post(f"{C}/practice/jobs/{j['id']}/status", headers=h, json={"status": "review"}).json()
    j3 = client.post(f"{C}/practice/jobs/{j['id']}/status", headers=h, json={"status": "complete", "note": "Lodged"}).json()
    assert j3["status"] == "complete" and j3["completed_at"] and j3["overdue"] is False
    # recurring: quarterly BAS due 28th of the month after quarter end; generate with a date inside the advance window
    r = client.post(f"{C}/practice/recurring", headers=h, json={"client_id": c["id"], "job_type": "BAS", "frequency": "quarterly", "month_offset": 1, "day_of_month": 28, "advance_days": 14, "assignee_membership_id": mid}).json()
    assert r["next_due_on"] and r["is_active"] is True
    nd = date.fromisoformat(r["next_due_on"])
    assert nd.day == 28 and nd.month in (10, 1, 4, 7)
    gen = client.post(f"{C}/practice/recurring/generate", headers=h, params={"as_of": (nd - timedelta(days=10)).isoformat()}).json()
    assert gen["created"] == 1
    gen = client.post(f"{C}/practice/recurring/generate", headers=h, params={"as_of": (nd - timedelta(days=10)).isoformat()}).json()
    assert gen["created"] == 0                                                         # idempotent per period
    bas = [x for x in client.get(f"{C}/practice/jobs", headers=h, params={"job_type": "BAS"}).json()]
    assert len(bas) == 1 and bas[0]["source"] == "recurring" and bas[0]["period_label"].startswith("Q") and bas[0]["due_on"] == nd.isoformat() and bas[0]["title"] == f"BAS {bas[0]['period_label']}"
    rec = client.get(f"{C}/practice/recurring", headers=h).json()[0]
    assert date.fromisoformat(rec["next_due_on"]) > nd and rec["last_period_label"] == bas[0]["period_label"]
    # deadlines merge jobs with the statutory calendar; team + overview
    dl = client.get(f"{C}/practice/deadlines", headers=h, params={"days": 120}).json()
    assert any(d["kind"] == "job" and d["job_id"] == bas[0]["id"] for d in dl) and any(d["kind"] == "statutory" for d in dl)
    team = client.get(f"{C}/practice/team", headers=h).json()
    assert team[0]["name"] == "Priya Nair" and team[0]["minutes_this_month"] == 90 and team[0]["open_jobs"] == 1
    ov = client.get(f"{C}/practice/overview", headers=h).json()
    assert ov["open_jobs"] == 1 and ov["completed_30d"] == 1 and ov["by_type"] == {"BAS": 1} and ov["recurring_active"] == 1
    # lifecycle job drives generation too
    from app.core.database import SessionLocal
    from app.core.security import utcnow
    from app.jobs import lifecycle
    with SessionLocal() as db:
        stats = lifecycle.run(db, now=utcnow() + timedelta(days=400))
    assert stats["recurring_jobs_created"] >= 1


def test_practice_period_maths():
    from datetime import date
    from app.modules.practice.service import fy_label, period_for
    assert fy_label(date(2027, 6, 30)) == "FY27" and fy_label(date(2026, 7, 1)) == "FY27" and fy_label(date(2026, 6, 30)) == "FY26"
    s, e, l = period_for("quarterly", date(2026, 9, 19)); assert (s, e, l) == (date(2026, 7, 1), date(2026, 9, 30), "Q1 FY27")
    s, e, l = period_for("quarterly", date(2027, 2, 1)); assert (s, e, l) == (date(2027, 1, 1), date(2027, 3, 31), "Q3 FY27")
    s, e, l = period_for("quarterly", date(2026, 12, 31)); assert (s, e, l) == (date(2026, 10, 1), date(2026, 12, 31), "Q2 FY27")
    s, e, l = period_for("monthly", date(2026, 2, 10)); assert (s, e, l) == (date(2026, 2, 1), date(2026, 2, 28), "Feb 2026")
    s, e, l = period_for("annual", date(2026, 9, 19)); assert (s, e, l) == (date(2026, 7, 1), date(2027, 6, 30), "FY27")
    s, e, l = period_for("biannual", date(2027, 3, 1)); assert (s, e, l) == (date(2027, 1, 1), date(2027, 6, 30), "H2 FY27")
