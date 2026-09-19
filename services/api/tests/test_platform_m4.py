"""M4: notifications, outbox, documents, billing ledger, lifecycle job."""
import hashlib
import io

from tests.conftest import STRONG_PW, auth, signup

C = "/api/v1"


def _invite_staff(client, h_owner, email="sam@a.example"):
    inv = client.post(f"{C}/users/invite", headers=h_owner, json={"email": email, "role": "staff", "modules": []}).json()
    acc = client.post(f"{C}/auth/accept-invite", json={"token": inv["accept_url"].split("token=")[1], "full_name": "Sam Whitlock", "password": STRONG_PW}).json()
    return acc


# ------------------------------------------------------------------ outbox + notifications
def test_signup_and_invite_queue_emails_visible_in_dev_outbox(client):
    h = auth(signup(client)["tokens"])
    client.post(f"{C}/users/invite", headers=h, json={"email": "sam@ashfield.example", "role": "staff", "modules": []})
    out = client.get(f"{C}/dev/outbound", headers=h).json()
    templates = {m["template"] for m in out}
    assert {"welcome", "invitation"} <= templates
    assert all(m["status"] == "queued" for m in out)
    inv = next(m for m in out if m["template"] == "invitation")
    assert "accept-invite?token=" in inv["body_text"] and inv["to_address"] == "sam@ashfield.example"
    # delivery with no SMTP configured marks messages skipped, never fails the flow
    counts = client.post(f"{C}/dev/deliver-outbound", headers=h).json()
    assert counts["skipped"] >= 2 and counts["failed"] == 0
    assert all(m["status"] == "skipped" for m in client.get(f"{C}/dev/outbound", headers=h).json())


def test_task_assignment_notifies_assignee_not_actor(client):
    owner = signup(client)
    h = auth(owner["tokens"])
    staff = _invite_staff(client, h)
    hs = auth(staff["tokens"])
    members = client.get(f"{C}/users", headers=h).json()
    sam = next(m for m in members if m["email"] == "sam@a.example")
    # owner assigns Sam a task
    client.post(f"{C}/crm/tasks", headers=h, json={"title": "Chase trust deed", "assignee_membership_id": sam["membership_id"]})
    assert client.get(f"{C}/notifications/unread-count", headers=hs).json()["unread"] == 1
    assert client.get(f"{C}/notifications/unread-count", headers=h).json()["unread"] == 0
    n = client.get(f"{C}/notifications", headers=hs).json()[0]
    assert n["kind"] == "task.assigned" and "Chase trust deed" in n["title"] and n["link"] == "/tasks"
    # …and Sam gets an email too
    assert any(m["template"] == "task_assigned" and m["to_address"] == "sam@a.example" for m in client.get(f"{C}/dev/outbound", headers=h).json())
    # self-assignment does not notify
    client.post(f"{C}/crm/tasks", headers=hs, json={"title": "My own task", "assignee_membership_id": sam["membership_id"]})
    assert client.get(f"{C}/notifications/unread-count", headers=hs).json()["unread"] == 1
    # mark read
    r = client.post(f"{C}/notifications/{n['id']}/read", headers=hs)
    assert r.status_code == 200 and r.json()["read_at"]
    assert client.get(f"{C}/notifications/unread-count", headers=hs).json()["unread"] == 0
    # cannot read someone else's notification
    assert client.post(f"{C}/notifications/{n['id']}/read", headers=h).status_code == 404


def test_module_added_notifies_other_admins(client):
    owner = signup(client)
    h = auth(owner["tokens"])
    inv = client.post(f"{C}/users/invite", headers=h, json={"email": "admin@a.example", "role": "admin", "modules": []}).json()
    adm = client.post(f"{C}/auth/accept-invite", json={"token": inv["accept_url"].split("token=")[1], "full_name": "Ada Admin", "password": STRONG_PW}).json()
    client.post(f"{C}/subscriptions", headers=h, json={"module_key": "sign"})
    ns = client.get(f"{C}/notifications", headers=auth(adm["tokens"])).json()
    assert any(n["kind"] == "subscription.added" and "Sign" in n["title"] for n in ns)
    assert client.get(f"{C}/notifications/unread-count", headers=h).json()["unread"] == 0  # actor excluded


# ------------------------------------------------------------------ documents
def test_document_upload_download_delete_and_hold(client):
    h = auth(signup(client)["tokens"])
    c = client.post(f"{C}/crm/clients", headers=h, json={"name": "Ashfield Family Trust", "client_type": "Trust"}).json()
    data = b"%PDF-1.4 trust deed variation " * 100
    r = client.post(f"{C}/documents", headers=h, files={"file": ("Trust Deed.pdf", io.BytesIO(data), "application/pdf")}, data={"client_id": c["id"], "kind": "legal", "description": "Deed variation"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["filename"] == "Trust Deed.pdf" and d["size_bytes"] == len(data) and d["sha256"] == hashlib.sha256(data).hexdigest()
    assert d["scan_status"] == "unavailable" and d["uploaded_by_name"] == "Priya Nair"  # no ClamAV in test → recorded, allowed outside production
    assert client.get(f"{C}/crm/clients/{c['id']}", headers=h).json()["document_count"] == 1
    assert any(e["kind"] == "document.uploaded" for e in client.get(f"{C}/crm/clients/{c['id']}/timeline", headers=h).json())
    dl = client.get(f"{C}/documents/{d['id']}/download", headers=h)
    assert dl.status_code == 200 and dl.content == data and dl.headers["x-content-sha256"] == d["sha256"] and "attachment" in dl.headers["content-disposition"]
    # hold → delete refused; lift hold (owner) → delete works
    assert client.post(f"{C}/documents/{d['id']}/hold", headers=h, json={"hold": True, "reason": "AML record"}).json()["retention_hold"] is True
    assert client.delete(f"{C}/documents/{d['id']}", headers=h).status_code == 409
    assert client.post(f"{C}/documents/{d['id']}/hold", headers=h, json={"hold": False}).json()["retention_hold"] is False
    assert client.delete(f"{C}/documents/{d['id']}", headers=h).status_code == 204
    assert client.get(f"{C}/documents", headers=h, params={"client_id": c["id"]}).json() == []
    assert client.get(f"{C}/documents/{d['id']}/download", headers=h).status_code == 404


def test_document_hold_release_needs_admin_and_tenant_isolation(client):
    a = signup(client, practice="A Co", email="a@a.example")
    h = auth(a["tokens"])
    staff = _invite_staff(client, h)
    hs = auth(staff["tokens"])
    d = client.post(f"{C}/documents", headers=hs, files={"file": ("id.jpg", io.BytesIO(b"\xff\xd8\xff" + b"x" * 500, ), "image/jpeg")}, data={"kind": "identity"}).json()
    assert client.post(f"{C}/documents/{d['id']}/hold", headers=hs, json={"hold": True}).status_code == 200          # staff may place
    assert client.post(f"{C}/documents/{d['id']}/hold", headers=hs, json={"hold": False}).status_code == 403         # but not lift
    b = signup(client, practice="B Co", email="b@b.example")
    assert client.get(f"{C}/documents/{d['id']}/download", headers=auth(b["tokens"])).status_code == 404
    assert client.get(f"{C}/documents", headers=auth(b["tokens"])).json() == []
    assert client.post(f"{C}/documents", headers=h, files={"file": ("e.txt", io.BytesIO(b""), "text/plain")}).status_code == 400


# ------------------------------------------------------------------ billing ledger
def test_billing_ledger_records_trial_subscriptions_and_verifies(client):
    out = signup(client)
    h = auth(out["tokens"])
    client.post(f"{C}/subscriptions", headers=h, json={"module_key": "verify"})
    ev = client.get(f"{C}/billing/events", headers=h).json()
    kinds = [e["kind"] for e in ev]
    assert kinds[-1] == "trial.started" and kinds.count("subscription.started") == 2  # documents (dependency) + verify
    verify_ev = next(e for e in ev if e["kind"] == "subscription.started" and e["module_key"] == "verify")
    assert verify_ev["amount_cents"] == 7000 and verify_ev["gst_cents"] == 700 and verify_ev["total_cents"] == 7700
    s = client.get(f"{C}/billing/summary", headers=h).json()
    assert s["tenant_status"] == "trialing" and s["base_plan_inc_gst_cents"] == 10890 and s["next_charge_at"] == out["session"]["tenant"]["trial_ends_at"]
    assert {l["module_key"] for l in s["lines"]} == {"crm", "documents", "verify"}
    # staff cannot see billing
    staff = _invite_staff(client, h)
    assert client.get(f"{C}/billing/summary", headers=auth(staff["tokens"])).status_code == 403
    from app.core.database import SessionLocal
    from app.services import billing_service
    with SessionLocal() as db:
        assert billing_service.verify_chain(db)["ok"] is True


# ------------------------------------------------------------------ lifecycle job
def test_trial_reminders_sent_once_then_trial_converts_with_simulated_charge(client):
    out = signup(client)
    h = auth(out["tokens"])
    # 4 days left → day-10 reminder
    client.post(f"{C}/dev/time-travel", headers=h, json={"trial_ends_in_days": 4})
    r1 = client.post(f"{C}/dev/run-lifecycle", headers=h).json()["stats"]
    r2 = client.post(f"{C}/dev/run-lifecycle", headers=h).json()["stats"]
    assert r1["reminders"] == 1 and r2["reminders"] == 0  # idempotent
    assert any(m["template"] == "trial_day10" for m in client.get(f"{C}/dev/outbound", headers=h).json())
    # 12 hours left → day-14 reminder
    client.post(f"{C}/dev/time-travel", headers=h, json={"trial_ends_in_days": 0.5})
    assert client.post(f"{C}/dev/run-lifecycle", headers=h).json()["stats"]["reminders"] == 1
    # trial over → active, 30-day period, simulated charge, base bundle rows active, owner emailed + notified
    client.post(f"{C}/dev/time-travel", headers=h, json={"trial_ends_in_days": -0.1})
    res = client.post(f"{C}/dev/run-lifecycle", headers=h).json()
    assert res["stats"]["activated"] == 1
    sess = res["session"]
    assert sess["tenant"]["status"] == "active" and sess["tenant"]["current_period_end"]
    assert all(s["status"] == "active" for s in sess["subscriptions"])
    ev = client.get(f"{C}/billing/events", headers=h).json()
    charge = next(e for e in ev if e["kind"] == "charge.simulated")
    assert charge["amount_cents"] == 9900 and charge["total_cents"] == 10890 and charge["status"] == "simulated"
    assert any(m["template"] == "trial_ended" for m in client.get(f"{C}/dev/outbound", headers=h).json())
    assert any(n["kind"] == "tenant.active" for n in client.get(f"{C}/notifications", headers=h).json())
    assert client.get(f"{C}/me", headers=h).json()["entitlements"]["crm"] is True


def test_dunning_past_due_to_suspended_to_cancelled_to_retained(client):
    out = signup(client)
    h = auth(out["tokens"])
    client.post(f"{C}/dev/lifecycle", headers=h, json={"status": "past_due"})
    client.post(f"{C}/dev/time-travel", headers=h, json={"status_changed_days_ago": 8})
    res = client.post(f"{C}/dev/run-lifecycle", headers=h).json()
    assert res["stats"]["suspended"] == 1 and res["session"]["tenant"]["status"] == "suspended" and res["session"]["read_only"] is True
    assert client.post(f"{C}/crm/clients", headers=h, json={"name": "X"}).status_code == 423
    client.post(f"{C}/dev/time-travel", headers=h, json={"status_changed_days_ago": 31})
    res = client.post(f"{C}/dev/run-lifecycle", headers=h).json()
    assert res["stats"]["cancelled"] == 1 and res["session"]["tenant"]["status"] == "cancelled"
    assert all(s["status"] == "cancelled" for s in res["session"]["subscriptions"])
    assert client.get(f"{C}/crm/clients", headers=h).status_code == 403  # no access
    client.post(f"{C}/dev/time-travel", headers=h, json={"status_changed_days_ago": 31})
    res = client.post(f"{C}/dev/run-lifecycle", headers=h).json()
    assert res["stats"]["retained"] == 1 and res["session"]["tenant"]["status"] == "retained"
    # records are still there — the owner's /me still works, nothing was deleted
    assert client.get(f"{C}/me", headers=h).status_code == 200
    templates = {m["template"] for m in client.get(f"{C}/dev/outbound", headers=h).json()}
    assert {"suspended", "cancelled"} <= templates
