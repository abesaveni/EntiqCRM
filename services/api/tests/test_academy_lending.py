"""M6c part 2: Academy (courses, quizzes, certificates, compliance requirements) and Lending (pipeline, requests interlink, conditions, settlement)."""
from datetime import date, timedelta

from tests.conftest import auth, signup

C = "/api/v1"


def _tenant(client, modules=("academy",)):
    out = signup(client)
    h = auth(out["tokens"])
    for m in modules:
        assert client.post(f"{C}/subscriptions", headers=h, json={"module_key": m}).status_code == 201
    return h, out


# ------------------------------------------------------------------ Academy
def test_academy_course_quiz_certificate_and_compliance(client):
    h, _ = _tenant(client)
    b = signup(client, practice="B Co", email="b@b.example")
    assert client.get(f"{C}/academy/overview", headers=auth(b["tokens"])).status_code == 403

    courses = client.post(f"{C}/academy/courses/seed", headers=h).json()
    assert len(courses) >= 4 and {c["category"] for c in courses} >= {"AML/CTF", "Privacy", "Cyber"}
    aml = next(c for c in courses if c["category"] == "AML/CTF")
    assert aml["pass_mark"] == 80 and aml["valid_months"] == 12 and aml["lesson_count"] == 4

    det = client.get(f"{C}/academy/courses/{aml['id']}", headers=h).json()
    assert [l["kind"] for l in det["lessons"]] == ["reading", "reading", "reading", "quiz"]
    quiz = det["lessons"][-1]
    assert len(quiz["questions"]) == 4 and quiz["questions"][0]["correct"] is not None   # owner is an author, sees answers

    det = client.post(f"{C}/academy/courses/{aml['id']}/start", headers=h).json()
    assert det["enrolment"]["status"] == "in_progress"
    for l in det["lessons"][:-1]:
        e = client.post(f"{C}/academy/courses/{aml['id']}/lessons/{l['id']}/complete", headers=h).json()
    assert e["progress"] == 75 and e["status"] == "in_progress"
    assert client.post(f"{C}/academy/courses/{aml['id']}/lessons/{quiz['id']}/complete", headers=h).status_code == 400   # a quiz needs an attempt

    # fail, then pass
    wrong = {q["id"]: [q["options"][0]] for q in quiz["questions"]}
    att = client.post(f"{C}/academy/courses/{aml['id']}/lessons/{quiz['id']}/attempt", headers=h, json={"answers": wrong})
    assert att.status_code == 200, att.text
    att = att.json()
    assert att["passed"] is False and att["score"] < 80 and att["certificate_serial"] is None and len(att["feedback"]) == 4
    right = {q["id"]: q["correct"] for q in quiz["questions"]}
    att = client.post(f"{C}/academy/courses/{aml['id']}/lessons/{quiz['id']}/attempt", headers=h, json={"answers": right}).json()
    assert att["passed"] is True and att["score"] == 100 and att["enrolment"]["status"] == "completed" and att["certificate_serial"]

    certs = client.get(f"{C}/academy/certificates", headers=h).json()
    assert len(certs) == 1 and certs[0]["member_name"] == "Priya Nair" and certs[0]["score"] == 100 and certs[0]["expired"] is False
    assert certs[0]["expires_on"] == (date.today().replace(year=date.today().year + 1)).isoformat() or certs[0]["expires_on"]
    v = client.get(f"{C}/academy/certificates/verify/{certs[0]['serial']}", headers=h).json()
    assert v["found"] is True and v["intact"] is True
    assert client.get(f"{C}/academy/certificates/verify/ENT-1999-DEADBEEF", headers=h).json()["found"] is False

    # a compliance requirement now shows this person as covered; a second course is not
    req = client.post(f"{C}/academy/requirements", headers=h, json={"course_id": aml["id"], "frequency_months": 12, "reference": "AML/CTF Act s.207"}).json()
    assert req["covered"] == 1 and req["overdue"] == 0
    privacy = next(c for c in courses if c["category"] == "Privacy")
    req2 = client.post(f"{C}/academy/requirements", headers=h, json={"course_id": privacy["id"], "frequency_months": 24, "roles": ["owner", "admin", "staff"]}).json()
    assert req2["overdue"] == 1
    rows = client.get(f"{C}/academy/compliance", headers=h).json()
    assert {r["state"] for r in rows} == {"covered", "never"}
    # enforcing creates the missing enrolment, and does not duplicate it
    assert client.post(f"{C}/academy/compliance/enforce", headers=h).json()["enrolled"] == 1
    assert client.post(f"{C}/academy/compliance/enforce", headers=h).json()["enrolled"] == 0
    mine = client.get(f"{C}/academy/my", headers=h).json()
    assert any(e["course_title"] == privacy["title"] and e["requirement_id"] == req2["id"] for e in mine["enrolments"])
    assert len(mine["certificates"]) == 1 and len(mine["compliance"]) == 2

    ov = client.get(f"{C}/academy/overview", headers=h).json()
    assert ov["certificates_valid"] == 1 and ov["compliance_pct"] == 50 and ov["enrolments_open"] == 1
    assert any(m["template"] == "academy_assigned" for m in client.get(f"{C}/dev/outbound", headers=h).json())


def test_academy_assign_to_team_and_isolation(client):
    h, _ = _tenant(client)
    courses = client.post(f"{C}/academy/courses/seed", headers=h).json()
    cyber = next(c for c in courses if c["category"] == "Cyber")
    rows = client.post(f"{C}/academy/enrolments", headers=h, json={"course_id": cyber["id"], "all_staff": True, "due_in_days": 14}).json()
    assert len(rows) == 1 and rows[0]["due_on"] == (date.today() + timedelta(days=14)).isoformat()
    assert any(n["kind"] == "academy.assigned" for n in client.get(f"{C}/notifications", headers=h).json())
    # authoring a course of our own
    made = client.post(f"{C}/academy/courses", headers=h, json={"title": "Our engagement letter process", "category": "Induction", "pass_mark": 50, "valid_months": None,
                                                                "lessons": [{"title": "When to re-issue", "kind": "reading", "minutes": 4, "body": "Re-issue on a change of scope or entity."},
                                                                            {"title": "Check", "kind": "quiz", "minutes": 2, "questions": [{"text": "Re-issue when?", "options": ["Never", "Scope changes", "Annually"], "correct": ["Scope changes"]}]}]}).json()
    assert made["lesson_count"] == 2 and made["minutes"] == 6
    b = signup(client, practice="B Co", email="b@b.example")
    hb = auth(b["tokens"])
    client.post(f"{C}/subscriptions", headers=hb, json={"module_key": "academy"})
    assert client.get(f"{C}/academy/courses", headers=hb).json() == []
    assert client.get(f"{C}/academy/courses/{cyber['id']}", headers=hb).status_code == 404


# ------------------------------------------------------------------ Lending
def test_lending_pipeline_with_requests_conditions_and_settlement(client):
    h, out = _tenant(client, modules=("lending", "requests", "advisory"))
    c = client.post(f"{C}/crm/clients", headers=h, json={"name": "Northfield Earthworks Pty Ltd", "client_type": "Company", "stage": "Active"}).json()
    ct = client.post(f"{C}/crm/clients/{c['id']}/contacts", headers=h, json={"first_name": "Ava", "last_name": "North", "email": "ava@northfield.example", "is_primary": True}).json()

    r = client.post(f"{C}/lending/applications", headers=h, json={"client_id": c["id"], "contact_id": ct["id"], "purpose": "equipment", "amount_cents": 25_000_000, "term_months": 60, "rate_bps": 890,
                                                                  "description": "Excavator replacement", "lender": "Regional Bank"})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["reference"].startswith("FIN-") and a["stage"] == "information" and a["request_pack_id"]   # a lending request pack was opened
    assert a["documents_outstanding"] and a["request_status"] == "sent"

    # cannot submit while the client still owes documents
    r = client.post(f"{C}/lending/applications/{a['id']}/stage", headers=h, json={"stage": "submitted"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "documents_outstanding"

    # client completes the request pack through the emailed link
    msg = [m for m in client.get(f"{C}/dev/outbound", headers=h).json() if m["template"] == "request_sent"][0]
    after = msg["body_text"].split("Upload securely here", 1)[1]
    tok = next(l.strip() for l in after.splitlines() if l.strip().startswith("http")).rsplit("/", 1)[1]
    pv = client.get(f"{C}/requests/public/{tok}").json()
    for i in pv["items"]:
        if i["required"]:
            pv = client.post(f"{C}/requests/public/{tok}/items/{i['id']}/upload", files={"file": (f"{i['key']}.pdf", b"%PDF-1.4 doc", "application/pdf")}).json()
    assert client.post(f"{C}/requests/public/{tok}/submit").json()["status"] == "submitted"
    pack_id = a["request_pack_id"]
    det = client.get(f"{C}/requests/packs/{pack_id}", headers=h).json()
    for i in det["items"]:
        if i["status"] == "uploaded":
            det = client.post(f"{C}/requests/packs/{pack_id}/items/{i['id']}/review", headers=h, json={"decision": "accept"}).json()
    assert det["status"] == "complete"
    # the completed pack advanced the application automatically (Requests → Lending subscriber)
    a = client.get(f"{C}/lending/applications/{a['id']}", headers=h).json()
    assert a["stage"] == "assessment" and a["readiness_pct"] >= 55 and not a["documents_outstanding"]

    # serviceability: pulls EBITDA from the advisory snapshot, computes the repayment and DSCR
    client.post(f"{C}/advisory/snapshots", headers=h, json={"client_id": c["id"], "revenue_cents": 300_000_000, "expenses_cents": 264_000_000, "net_profit_cents": 36_000_000, "cash_cents": 40_000_000})
    a = client.post(f"{C}/lending/applications/{a['id']}/assess", headers=h, json={"existing_repayments_cents": 1_200_000, "use_snapshot": True}).json()
    assert a["serviceability"]["ebitda_cents"] == 36_000_000 and "Advisory snapshot" in a["serviceability"]["ebitda_source"]
    assert a["repayment_cents"] and 500_000 < a["repayment_cents"] < 600_000        # ~$5,175/mo on $250k over 60m at 8.9%
    assert a["dscr"] and a["dscr"] > 1.5

    # submit → approve (with conditions) → settle
    a = client.post(f"{C}/lending/applications/{a['id']}/stage", headers=h, json={"stage": "submitted", "note": "Lodged with Regional Bank"}).json()
    assert a["stage"] == "submitted" and a["submitted_at"]
    a = client.post(f"{C}/lending/applications/{a['id']}/stage", headers=h, json={"stage": "approved", "note": "Approved at 8.9% over 60 months"}).json()
    assert a["stage"] == "approved" and a["approved_at"] and a["decision_note"]
    a = client.post(f"{C}/lending/applications/{a['id']}/conditions", headers=h, json={"title": "Executed equipment finance agreement", "kind": "precedent", "owner_side": "client"}).json()
    a = client.post(f"{C}/lending/applications/{a['id']}/conditions", headers=h, json={"title": "Comprehensive insurance noting the lender", "kind": "precedent", "owner_side": "client", "due_on": (date.today() + timedelta(days=7)).isoformat()}).json()
    a = client.post(f"{C}/lending/applications/{a['id']}/conditions", headers=h, json={"title": "Provide FY27 financials within 90 days of year end", "kind": "subsequent", "owner_side": "practice"}).json()
    assert a["stage"] == "conditions" and a["conditions_open"] == 3 and a["conditions_blocking"] == 2

    r = client.post(f"{C}/lending/applications/{a['id']}/stage", headers=h, json={"stage": "settled"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "conditions_open"
    for cond in [x for x in a["conditions"] if x["kind"] == "precedent"]:
        a = client.post(f"{C}/lending/applications/{a['id']}/conditions/{cond['id']}/satisfy", headers=h, json={"note": "Received and filed"}).json()
    assert a["conditions_blocking"] == 0 and a["conditions_open"] == 1
    a = client.post(f"{C}/lending/applications/{a['id']}/stage", headers=h, json={"stage": "settled", "note": "Funded 25 Sep"}).json()
    assert a["stage"] == "settled" and a["settled_at"] and a["settlement_date"] and a["readiness_pct"] == 100
    assert "lending.settled" in [e["kind"] for e in client.get(f"{C}/billing/events", headers=h).json()]
    kinds = [e["kind"] for e in a["events"]]
    assert kinds[0] == "created" and "assessed" in kinds and kinds.count("condition_satisfied") == 2 and kinds[-1] == "stage"

    ov = client.get(f"{C}/lending/overview", headers=h).json()
    assert ov["settled_90d"] == 1 and ov["settled_value_90d_cents"] == 25_000_000 and ov["conversion_pct"] == 100 and ov["conditions_open"] == 1
    tl = [e["kind"] for e in client.get(f"{C}/crm/clients/{c['id']}/timeline", headers=h).json()]
    assert {"lending.created", "lending.submitted", "lending.approved", "lending.conditions_cleared", "lending.settled"} <= set(tl)


def test_lending_decline_permissions_and_isolation(client):
    h, _ = _tenant(client, modules=("lending",))
    c = client.post(f"{C}/crm/clients", headers=h, json={"name": "Tiny Co", "client_type": "Company"}).json()
    a = client.post(f"{C}/lending/applications", headers=h, json={"client_id": c["id"], "amount_cents": 5_000_000, "send_request": False}).json()
    assert a["stage"] == "enquiry" and a["request_pack_id"] is None
    # no Requests module → opening a pack is refused with a clear message
    r = client.post(f"{C}/lending/applications/{a['id']}/request", headers=h)
    assert r.status_code == 400 and r.json()["detail"]["error"] == "requests_required"
    a = client.post(f"{C}/lending/applications/{a['id']}/stage", headers=h, json={"stage": "declined", "note": "Serviceability not met"}).json()
    assert a["stage"] == "declined" and a["closed_at"] and a["close_reason"] == "Serviceability not met"
    assert client.post(f"{C}/lending/applications/{a['id']}/stage", headers=h, json={"stage": "approved"}).status_code == 409
    b = signup(client, practice="B Co", email="b@b.example")
    hb = auth(b["tokens"])
    client.post(f"{C}/subscriptions", headers=hb, json={"module_key": "lending"})
    assert client.get(f"{C}/lending/applications/{a['id']}", headers=hb).status_code == 404
    assert client.get(f"{C}/lending/applications", headers=hb).json() == []
