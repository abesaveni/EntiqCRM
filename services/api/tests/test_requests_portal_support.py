"""M6b: Requests (adaptive packs, tokened client surface, exceptions-only review), Client portal (magic-link auth, home, documents, messages, requests), Support (tenant ↔ operator with SLA)."""
import io
from datetime import timedelta

from tests.conftest import STRONG_PW, auth, signup

C = "/api/v1"


def _tenant(client, modules=("requests", "client", "sign", "practice")):
    out = signup(client)
    h = auth(out["tokens"])
    for m in modules:
        assert client.post(f"{C}/subscriptions", headers=h, json={"module_key": m}).status_code == 201
    c = client.post(f"{C}/crm/clients", headers=h, json={"name": "Marlow Constructions Pty Ltd", "client_type": "Company", "stage": "Active"}).json()
    ct = client.post(f"{C}/crm/clients/{c['id']}/contacts", headers=h, json={"first_name": "Gavin", "last_name": "Marlow", "role": "Director", "is_primary": True, "email": "gavin@marlow.example"}).json()
    return h, c, ct


def _link(client, h, template, marker):
    m = [x for x in client.get(f"{C}/dev/outbound", headers=h).json() if x["template"] == template][0]
    after = m["body_text"].split(marker, 1)[1]
    url = next(line.strip() for line in after.splitlines() if line.strip().startswith("http"))
    return url.rsplit("/", 1)[1]


def _file(name, ct="application/pdf"):
    return {"file": (name, io.BytesIO(b"%PDF-1.4 " + name.encode() * 30), ct)}


# ------------------------------------------------------------------ Requests
def test_requests_adaptive_pack_client_flow_and_exceptions_review(client):
    h, c, ct = _tenant(client, modules=("requests",))
    tpl = {t["purpose"]: t for t in client.get(f"{C}/requests/templates", headers=h).json()}
    assert "rental" in {q["key"] for q in tpl["tax_return"]["questions"]}
    r = client.post(f"{C}/requests/packs", headers=h, json={"client_id": c["id"], "purpose": "tax_return", "period_label": "FY26", "message": "Please send by end of month.", "items": [{"label": "Vehicle purchase contract", "category": "financial", "required": False}], "due_in_days": 10})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "sent" and p["request_url"] and "/r/" in p["request_url"] and p["contact_email"] == "gavin@marlow.example"
    keys = {i["key"] for i in p["items"]}
    assert {"bank_statements", "prior_financials", "vehicle_purchase_contract"} <= keys and "rental_statements" not in keys and "income_summary" not in keys   # Company → no PAYG; conditional items absent
    assert len(p["questions"]) == 3
    tok = p["request_url"].rsplit("/", 1)[1]
    assert tok == _link(client, h, "request_sent", "Upload securely here by")

    # client answers yes to rental → items added; no to crypto
    pv = client.post(f"{C}/requests/public/{tok}/questions", json={"key": "rental", "answer": True}).json()
    assert {"rental_statements", "rental_expenses"} <= {i["key"] for i in pv["items"]} and pv["status"] == "in_progress"
    client.post(f"{C}/requests/public/{tok}/questions", json={"key": "crypto", "answer": False})
    client.post(f"{C}/requests/public/{tok}/questions", json={"key": "vehicle", "answer": False})
    pv = client.get(f"{C}/requests/public/{tok}").json()
    assert pv["can_submit"] is False and "Bank statements for the year" in pv["outstanding"]
    items = {i["key"]: i for i in pv["items"]}
    # uploads: a well-named bank statement is clean; a payslip uploaded as "prior financials" is flagged (exceptions-only review)
    pv = client.post(f"{C}/requests/public/{tok}/items/{items['bank_statements']['id']}/upload", files=_file("ANZ bank statement FY26.pdf"))
    assert pv.status_code == 200, pv.text
    pv = client.post(f"{C}/requests/public/{tok}/items/{items['prior_financials']['id']}/upload", files=_file("payslip march.pdf")).json()
    flagged = next(i for i in pv["items"] if i["key"] == "prior_financials")
    assert flagged["status"] == "uploaded" and "looks_like_payroll" in flagged["classification"]["flags"] and flagged["classification"]["matches_item"] is False
    clean = next(i for i in pv["items"] if i["key"] == "bank_statements")
    assert clean["classification"]["detected"] == "bank" and clean["classification"]["flags"] == []
    # N/A with a note for the rest of the required items
    for k in ("rental_statements", "trust_distribution"):
        if k in items or any(i["key"] == k for i in pv["items"]):
            iid = next(i["id"] for i in pv["items"] if i["key"] == k)
            pv = client.post(f"{C}/requests/public/{tok}/items/{iid}/not-applicable", json={"note": "Sold before the year started"}).json()
    r = client.post(f"{C}/requests/public/{tok}/submit")
    assert r.status_code == 200, r.text
    pv = r.json()
    assert pv["status"] == "submitted" and pv["can_submit"] is False
    # practice: notified, exceptions counted, documents on the client record
    assert any(n["kind"] == "request.submitted" and "1 item(s) flagged" in (n["body"] or "") for n in client.get(f"{C}/notifications", headers=h).json())
    det = client.get(f"{C}/requests/packs/{p['id']}", headers=h).json()
    assert det["exceptions"] == 1 and det["items_uploaded"] == 2
    docs = client.get(f"{C}/documents", headers=h, params={"client_id": c["id"]}).json()
    assert len(docs) == 2 and {d["kind"] for d in docs} == {"bank", "financial"}
    ov = client.get(f"{C}/requests/overview", headers=h).json()
    assert ov["awaiting_review"] == 1 and ov["exceptions"] == 1
    # review: reject the flagged one (client emailed with a fresh link), accept the clean one
    fin = next(i for i in det["items"] if i["key"] == "prior_financials"); bank = next(i for i in det["items"] if i["key"] == "bank_statements")
    r = client.post(f"{C}/requests/packs/{p['id']}/items/{fin['id']}/review", headers=h, json={"decision": "reject"})
    assert r.status_code == 400
    det = client.post(f"{C}/requests/packs/{p['id']}/items/{fin['id']}/review", headers=h, json={"decision": "reject", "reason": "This is a payslip, we need the financial statements"}).json()
    assert det["status"] == "in_progress" and det["items_rejected"] == 1
    tok2 = _link(client, h, "request_item_rejected", "Re-upload here:")
    assert tok2 != tok and client.get(f"{C}/requests/public/{tok}").status_code == 404
    det = client.post(f"{C}/requests/packs/{p['id']}/items/{bank['id']}/review", headers=h, json={"decision": "accept"}).json()
    assert next(i for i in det["items"] if i["key"] == "bank_statements")["status"] == "accepted"
    # client re-uploads the right file → submit again → accept → auto-complete + metered
    pv = client.get(f"{C}/requests/public/{tok2}").json()
    assert "Prior year financial statements" in pv["outstanding"]
    fin_id = next(i["id"] for i in pv["items"] if i["key"] == "prior_financials")
    client.post(f"{C}/requests/public/{tok2}/items/{fin_id}/upload", files=_file("Marlow financial statements FY25.pdf"))
    assert client.post(f"{C}/requests/public/{tok2}/submit").json()["status"] == "submitted"
    det = client.post(f"{C}/requests/packs/{p['id']}/items/{fin_id}/review", headers=h, json={"decision": "accept"}).json()
    assert det["status"] == "complete" and det["completed_at"] and det["token_expires_at"]
    assert client.get(f"{C}/requests/public/{tok2}").status_code == 404
    assert "request.completed" in [e["kind"] for e in client.get(f"{C}/billing/events", headers=h).json()]
    tl = [e["kind"] for e in client.get(f"{C}/crm/clients/{c['id']}/timeline", headers=h).json()]
    assert {"request.sent", "request.item_uploaded", "request.submitted", "request.item_reviewed", "request.completed"} <= set(tl)


def test_requests_reminders_cancel_and_isolation(client):
    from app.core.database import SessionLocal
    from app.core.security import utcnow
    from app.jobs import lifecycle
    h, c, ct = _tenant(client, modules=("requests",))
    p = client.post(f"{C}/requests/packs", headers=h, json={"client_id": c["id"], "purpose": "bas", "period_label": "Q1 FY27", "due_in_days": 2}).json()
    det = client.post(f"{C}/requests/packs/{p['id']}/remind", headers=h).json()
    assert det["reminder_count"] == 1
    # lifecycle auto-reminder: only once, 3 days past due, for packs with no reminder yet
    p2 = client.post(f"{C}/requests/packs", headers=h, json={"client_id": c["id"], "purpose": "financials", "due_in_days": 1}).json()
    with SessionLocal() as db:
        stats = lifecycle.run(db, now=utcnow() + timedelta(days=6))
    assert stats["request_reminders"] == 1
    assert client.get(f"{C}/requests/packs/{p2['id']}", headers=h).json()["reminder_count"] == 1
    det = client.post(f"{C}/requests/packs/{p['id']}/cancel", headers=h).json()
    assert det["status"] == "cancelled"
    b = signup(client, practice="B Co", email="b@b.example"); hb = auth(b["tokens"])
    client.post(f"{C}/subscriptions", headers=hb, json={"module_key": "requests"})
    assert client.get(f"{C}/requests/packs/{p['id']}", headers=hb).status_code == 404 and client.get(f"{C}/requests/packs", headers=hb).json() == []


# ------------------------------------------------------------------ Client portal
def test_portal_invite_magic_link_home_documents_messages_and_requests(client):
    h, c, ct = _tenant(client)
    # invite → email with one-time link; unknown emails get a silent 202
    r = client.post(f"{C}/client/contacts/{ct['id']}/invite", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["has_portal_access"] is True and r.json()["invited_at"]
    assert client.get(f"{C}/crm/clients/{c['id']}/contacts", headers=h).json()[0]["has_portal_access"] is True
    tok = _link(client, h, "portal_invite", "on the portal page):")
    assert client.post(f"{C}/portal/auth/request-link", json={"email": "nobody@nowhere.example"}).status_code == 202
    # exchange → portal JWT; link is single-use
    x = client.post(f"{C}/portal/auth/exchange", json={"token": tok})
    assert x.status_code == 200, x.text
    ph = {"Authorization": "Bearer " + x.json()["access_token"]}
    assert x.json()["practice_name"] == "Ashfield Partners" and x.json()["client_name"] == c["name"]
    assert client.post(f"{C}/portal/auth/exchange", json={"token": tok}).status_code == 401
    # staff tokens are not portal tokens and vice versa
    assert client.get(f"{C}/portal/me", headers=h).status_code == 401
    assert client.get(f"{C}/crm/clients", headers=ph).status_code == 401
    me = client.get(f"{C}/portal/me", headers=ph).json()
    assert me["name"] == "Gavin Marlow" and me["features"] == {"documents": True, "messages": True, "requests": True, "agreements": True, "jobs": True}
    # documents: staff upload is hidden until shared; client upload is visible
    d = client.post(f"{C}/documents", headers=h, files=_file("FY26 financial statements.pdf"), data={"client_id": c["id"], "kind": "financial"}).json()
    assert client.get(f"{C}/portal/documents", headers=ph).json() == []
    assert client.get(f"{C}/portal/documents/{d['id']}/download", headers=ph).status_code == 404
    r = client.post(f"{C}/documents/{d['id']}/share", headers=h, json={"visible_to_client": True})
    assert r.status_code == 200, r.text
    assert r.json()["visible_to_client"] is True
    pdocs = client.get(f"{C}/portal/documents", headers=ph).json()
    assert [x["filename"] for x in pdocs] == ["FY26 financial statements.pdf"] and pdocs[0]["uploaded_by"] == "Practice"
    assert client.get(f"{C}/portal/documents/{d['id']}/download", headers=ph).status_code == 200
    up = client.post(f"{C}/portal/documents", headers=ph, files=_file("signed minutes.pdf"))
    assert up.status_code == 201 and up.json()["uploaded_by"] == "You"
    staff_docs = client.get(f"{C}/documents", headers=h, params={"client_id": c["id"]}).json()
    assert any(x["filename"] == "signed minutes.pdf" and x["module_key"] == "client" and x["visible_to_client"] for x in staff_docs)
    # messages both ways: client → owner notified; staff → client emailed; read receipts
    client.post(f"{C}/portal/messages", headers=ph, json={"body": "When is my BAS due?"})
    assert any(n["kind"] == "portal.message" for n in client.get(f"{C}/notifications", headers=h).json())
    thread = client.get(f"{C}/client/clients/{c['id']}/messages", headers=h).json()
    assert len(thread) == 1 and thread[0]["from_client"] is True and thread[0]["read"] is True
    client.post(f"{C}/client/clients/{c['id']}/messages", headers=h, json={"body": "28 October — we'll send a request for your statements."})
    assert any(m["template"] == "portal_message" for m in client.get(f"{C}/dev/outbound", headers=h).json())
    home = client.get(f"{C}/portal/home", headers=ph).json()
    assert len(home["messages"]) == 2 and home["me"]["counts"]["shared_documents"] == 2
    # a request pack appears in the portal and can be worked without the emailed token
    p = client.post(f"{C}/requests/packs", headers=h, json={"client_id": c["id"], "purpose": "bas", "period_label": "Q1 FY27"}).json()
    home = client.get(f"{C}/portal/home", headers=ph).json()
    assert [r_["title"] for r_ in home["requests"]] == [p["title"]] and home["me"]["counts"]["open_requests"] == 1
    pv = client.get(f"{C}/portal/requests/{p['id']}", headers=ph).json()
    for it in pv["items"]:
        if it["required"]:
            r = client.post(f"{C}/portal/requests/{p['id']}/items/{it['id']}/upload", headers=ph, files=_file(f"{it['key']} q1.pdf"))
            assert r.status_code == 200, r.text
    assert client.post(f"{C}/portal/requests/{p['id']}/submit", headers=ph).json()["status"] == "submitted"
    # agreements: one sent to this contact shows as awaiting; resend from the portal works
    loe = client.post(f"{C}/documents", headers=h, files=_file("LoE.pdf"), data={"client_id": c["id"], "kind": "agreement"}).json()
    a = client.post(f"{C}/sign/agreements", headers=h, json={"title": "Engagement", "document_id": loe["id"], "client_id": c["id"], "signers": [{"name": "Gavin Marlow", "email": "gavin@marlow.example", "contact_id": ct["id"]}]}).json()
    home = client.get(f"{C}/portal/home", headers=ph).json()
    assert home["agreements"][0]["my_status"] == "sent" and home["me"]["counts"]["awaiting_signature"] == 1
    assert client.post(f"{C}/portal/agreements/{a['id']}/resend", headers=ph).json()["sent"] == 1
    # jobs (practice) visible read-only; client-visible timeline excludes internal kinds
    client.post(f"{C}/practice/jobs", headers=h, json={"client_id": c["id"], "title": "BAS Q1 FY27", "job_type": "BAS"})
    home = client.get(f"{C}/portal/home", headers=ph).json()
    assert home["jobs"][0]["title"] == "BAS Q1 FY27" and all(e["kind"] in ("document.uploaded", "agreement.sent", "request.sent", "stage.changed", "agreement.completed", "request.completed", "request.item_reviewed", "job.completed", "onboarding.activated") for e in home["recent"])
    # overview + revoke kills the session immediately
    ov = client.get(f"{C}/client/overview", headers=h).json()
    assert ov["contacts_with_access"] == 1 and ov["logins_30d"] == 1 and ov["shared_documents"] >= 2
    client.post(f"{C}/client/contacts/{ct['id']}/revoke", headers=h)
    assert client.get(f"{C}/portal/me", headers=ph).status_code == 401
    # login link after re-invite: request-link path
    client.post(f"{C}/client/contacts/{ct['id']}/invite", headers=h)
    assert client.post(f"{C}/portal/auth/request-link", json={"email": "GAVIN@marlow.example"}).status_code == 202
    tok2 = _link(client, h, "portal_login", "(valid 30 minutes):")
    assert client.post(f"{C}/portal/auth/exchange", json={"token": tok2}).status_code == 200


def test_portal_closed_when_practice_unsubscribes(client):
    h, c, ct = _tenant(client, modules=("client",))
    client.post(f"{C}/client/contacts/{ct['id']}/invite", headers=h)
    tok = _link(client, h, "portal_invite", "on the portal page):")
    ph = {"Authorization": "Bearer " + client.post(f"{C}/portal/auth/exchange", json={"token": tok}).json()["access_token"]}
    assert client.get(f"{C}/portal/me", headers=ph).status_code == 200
    assert client.delete(f"{C}/subscriptions/client", headers=h).status_code in (200, 204)
    assert client.get(f"{C}/portal/me", headers=ph).status_code == 403


# ------------------------------------------------------------------ Support
def test_support_ticket_tenant_and_operator_with_sla(client):
    from app.core.database import SessionLocal
    from app.core.tenancy import platform_scope
    from app.models.identity import User
    h, c, ct = _tenant(client, modules=())
    r = client.post(f"{C}/hq/support", headers=h, json={"subject": "Xero import fails", "body": "The MYOB CSV import stops at row 40 with no error.", "category": "problem", "priority": "high", "module_key": "crm"})
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["number"] >= 1001 and t["status"] == "open" and t["sla_state"] == "ok" and t["first_response_due_at"]
    assert any(m["template"] == "support_ack" for m in client.get(f"{C}/dev/outbound", headers=h).json())
    # operators only
    assert client.get(f"{C}/control/support", headers=h).status_code == 403
    op = signup(client, practice="EnTIQ Ops", email="ops@entiq.example", name="Ops Person")
    with SessionLocal() as db, platform_scope():
        u = db.execute(__import__("sqlalchemy").select(User).where(User.email == "ops@entiq.example")).scalar_one()
        u.is_operator = True
        db.commit()
    oh = auth(client.post(f"{C}/auth/login", json={"email": "ops@entiq.example", "password": STRONG_PW}).json()["tokens"])
    q = client.get(f"{C}/control/support", headers=oh).json()
    assert len(q) == 1 and q[0]["practice_name"] == "Ashfield Partners" and q[0]["priority"] == "high"
    st = client.get(f"{C}/control/support/stats", headers=oh).json()
    assert st["open"] == 1 and st["unassigned"] == 1
    # internal note is invisible to the tenant; public reply sets first response, assigns, moves to pending, emails + notifies
    client.post(f"{C}/control/support/{t['id']}/comments", headers=oh, json={"body": "Looks like the encoding bug", "internal": True})
    det = client.post(f"{C}/control/support/{t['id']}/comments", headers=oh, json={"body": "Thanks — can you attach the CSV? We suspect a BOM at row 40."}).json()
    assert det["status"] == "pending" and det["first_response_at"] and det["assigned_operator_name"] == "Ops Person" and det["sla_state"] in ("ok", "met") and len(det["comments"]) == 2
    mine = client.get(f"{C}/hq/support/{t['id']}", headers=h).json()
    assert len(mine["comments"]) == 1 and mine["comments"][0]["is_operator"] is True
    assert any(n["kind"] == "support.reply" for n in client.get(f"{C}/notifications", headers=h).json())
    assert any(m["template"] == "support_reply" for m in client.get(f"{C}/dev/outbound", headers=h).json())
    # tenant replies → back to open; operator resolves; tenant closes with a rating
    det = client.post(f"{C}/hq/support/{t['id']}/comments", headers=h, json={"body": "Attached."}).json()
    assert det["status"] == "open"
    det = client.post(f"{C}/control/support/{t['id']}/status", headers=oh, json={"status": "resolved"}).json()
    assert det["status"] == "resolved" and det["resolved_at"] and det["sla_breached"] is False
    det = client.post(f"{C}/hq/support/{t['id']}/close", headers=h, json={"status": "closed", "satisfaction": 5}).json()
    assert det["status"] == "closed" and det["satisfaction"] == 5
    # another tenant cannot see it
    b = signup(client, practice="B Co", email="b@b.example"); hb = auth(b["tokens"])
    assert client.get(f"{C}/hq/support", headers=hb).json() == [] and client.get(f"{C}/hq/support/{t['id']}", headers=hb).status_code == 404
