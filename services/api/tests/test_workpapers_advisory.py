"""M6c part 1: Workpapers (ledger sync, rules, review, sign-off, lodge) and Advisory (snapshot → KPIs → alerts → meeting → actions)."""
from datetime import date, timedelta

from tests.conftest import auth, signup

C = "/api/v1"


def _tenant(client, modules=("workpapers", "advisory", "practice", "client")):
    out = signup(client)
    h = auth(out["tokens"])
    for m in modules:
        assert client.post(f"{C}/subscriptions", headers=h, json={"module_key": m}).status_code == 201
    c = client.post(f"{C}/crm/clients", headers=h, json={"name": "Marlow Constructions Pty Ltd", "client_type": "Company", "stage": "Active"}).json()
    return h, c


def test_workpapers_sync_rules_review_signoff_and_lodge(client):
    h, c = _tenant(client)
    # not subscribed → upsell
    b = signup(client, practice="B Co", email="b@b.example")
    assert client.get(f"{C}/workpapers/overview", headers=auth(b["tokens"])).status_code == 403

    r = client.post(f"{C}/workpapers/packs", headers=h, json={"client_id": c["id"], "pack_type": "financial_statements", "period_label": "FY26", "period_end": "2026-06-30", "materiality_cents": 500000})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "draft" and p["items_total"] == 16 and p["preparer_name"] == "Priya Nair"
    assert {i["section"] for i in p["items"]} == {"Checklist", "Assets", "Liabilities", "Equity", "Income", "Expenses", "Disclosures"}

    # ledger: connects in simulation (no Xero credentials), sync brings a full trial balance
    conn = client.post(f"{C}/workpapers/ledger/connect", headers=h, json={"client_id": c["id"], "provider": "xero"}).json()
    assert conn["connection"]["simulated"] is True and conn["authorize_url"] is None and "simulation" in conn["message"]
    sy = client.post(f"{C}/workpapers/packs/{p['id']}/sync", headers=h)
    assert sy.status_code == 200, sy.text
    sy = sy.json()
    assert sy["simulated"] is True and sy["source"] == "simulation" and sy["synced"] >= 30
    pk = sy["pack"]
    assert pk["status"] == "in_progress" and pk["ledger_source"] == "simulation" and pk["ledger_synced_at"]
    accounts = [i for i in pk["items"] if i["account_code"]]
    assert len(accounts) >= 30 and all(i["value_cents"] is not None and i["prior_cents"] is not None for i in accounts)
    assert any(i["variance_cents"] for i in accounts)
    # the same sync twice is stable (deterministic per client+period), no duplicate items
    again = client.post(f"{C}/workpapers/packs/{p['id']}/sync", headers=h).json()
    assert again["pack"]["items_total"] == pk["items_total"]
    assert {i["key"]: i["value_cents"] for i in again["pack"]["items"]} == {i["key"]: i["value_cents"] for i in pk["items"]}

    # rules raised issues: missing evidence on material balance-sheet items (blocking)
    det = client.post(f"{C}/workpapers/packs/{p['id']}/checks", headers=h).json()
    assert det["open_issues"] > 0 and det["blocking_issues"] > 0
    kinds = {x["kind"] for x in det["issues"]}
    assert "missing_evidence" in kinds
    auto = [x for x in det["issues"] if x["auto"]]
    assert auto and all(x["status"] == "open" for x in auto)

    # sign-off is refused while blocking issues are open
    r = client.post(f"{C}/workpapers/packs/{p['id']}/sign-off", headers=h, json={})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "blocking_issues"

    # prepare: attach evidence to the blocking items, add workings for variances
    doc = client.post(f"{C}/documents", headers=h, files={"file": ("bank statement jun26.pdf", b"%PDF-1.4 statement", "application/pdf")}, data={"client_id": c["id"], "kind": "bank"}).json()
    det = client.get(f"{C}/workpapers/packs/{p['id']}", headers=h).json()
    for x in [i for i in det["issues"] if i["kind"] == "missing_evidence" and i["status"] == "open"]:
        det = client.patch(f"{C}/workpapers/packs/{p['id']}/items/{x['item_id']}", headers=h, json={"document_id": doc["id"], "status": "prepared"}).json()
    for x in [i for i in det["issues"] if i["kind"] == "variance" and i["status"] == "open"]:
        det = client.patch(f"{C}/workpapers/packs/{p['id']}/items/{x['item_id']}", headers=h, json={"workings": "Movement agreed to the ledger and supporting invoices."}).json()
    det = client.post(f"{C}/workpapers/packs/{p['id']}/checks", headers=h).json()
    assert det["blocking_issues"] == 0
    assert all(i["evidence_state"] == "attached" for i in det["items"] if i["document_id"])

    # submit needs every item started
    r = client.post(f"{C}/workpapers/packs/{p['id']}/submit", headers=h)
    assert r.status_code == 400 and r.json()["detail"]["error"] == "not_prepared"
    for i in det["items"]:
        if i["status"] == "not_started":
            det = client.patch(f"{C}/workpapers/packs/{p['id']}/items/{i['id']}", headers=h, json={"status": "prepared"}).json()
    det = client.post(f"{C}/workpapers/packs/{p['id']}/submit", headers=h).json()
    assert det["status"] == "in_review" and det["prepared_at"]

    # reviewer raises a query, preparer resolves it
    target = next(i for i in det["items"] if i["section"] == "Assets")
    det = client.post(f"{C}/workpapers/packs/{p['id']}/issues", headers=h, json={"item_id": target["id"], "kind": "query", "title": "Agree this to the bank statement page 3", "blocking": True}).json()
    assert next(i for i in det["items"] if i["id"] == target["id"])["status"] == "queried"
    assert client.post(f"{C}/workpapers/packs/{p['id']}/sign-off", headers=h, json={}).status_code == 409
    issue = next(x for x in det["issues"] if x["title"].startswith("Agree this"))
    det = client.post(f"{C}/workpapers/packs/{p['id']}/issues/{issue['id']}/resolve", headers=h, json={"resolution": "Agreed to page 3, no difference."}).json()
    assert next(x for x in det["issues"] if x["id"] == issue["id"])["status"] == "resolved"

    # sign off → sealed, items locked, metered, and further edits refused
    det = client.post(f"{C}/workpapers/packs/{p['id']}/sign-off", headers=h, json={"note": "Reviewed against the ledger and prior year."}).json()
    assert det["status"] == "signed_off" and det["seal_sha256"] and det["signed_off_by_name"] == "Priya Nair"
    assert all(i["status"] in ("signed_off", "n_a", "not_started") for i in det["items"])
    r = client.patch(f"{C}/workpapers/packs/{p['id']}/items/{target['id']}", headers=h, json={"workings": "late change"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "locked"
    assert "workpaper.signed_off" in [e["kind"] for e in client.get(f"{C}/billing/events", headers=h).json()]

    # lodge, then confirm a lodged pack cannot be reopened
    det = client.post(f"{C}/workpapers/packs/{p['id']}/lodge", headers=h, json={"reference": "ATO-2026-884412"}).json()
    assert det["status"] == "lodged" and det["lodgement_ref"] == "ATO-2026-884412"
    assert client.post(f"{C}/workpapers/packs/{p['id']}/reopen", headers=h).status_code == 409
    ov = client.get(f"{C}/workpapers/overview", headers=h).json()
    assert ov["lodged_30d"] == 1 and ov["ledger_connections"] == 1 and ov["ledger_live"] is False
    tl = [e["kind"] for e in client.get(f"{C}/crm/clients/{c['id']}/timeline", headers=h).json()]
    assert {"workpaper.created", "ledger.synced", "workpaper.submitted", "workpaper.signed_off", "workpaper.lodged"} <= set(tl)


def test_workpapers_closes_the_practice_job_on_signoff(client):
    h, c = _tenant(client)
    j = client.post(f"{C}/practice/jobs", headers=h, json={"client_id": c["id"], "title": "FY26 financials", "job_type": "Financial Statements"}).json()
    p = client.post(f"{C}/workpapers/packs", headers=h, json={"client_id": c["id"], "job_id": j["id"], "pack_type": "bas", "period_label": "Q1 FY27"}).json()
    for i in p["items"]:
        client.patch(f"{C}/workpapers/packs/{p['id']}/items/{i['id']}", headers=h, json={"status": "prepared"})
    client.post(f"{C}/workpapers/packs/{p['id']}/submit", headers=h)
    det = client.post(f"{C}/workpapers/packs/{p['id']}/sign-off", headers=h, json={}).json()
    assert det["status"] == "signed_off"
    assert client.get(f"{C}/practice/jobs/{j['id']}", headers=h).json()["status"] == "complete"


def test_advisory_snapshot_kpis_alerts_meeting_actions_and_publish(client):
    h, c = _tenant(client)
    # a manual snapshot with thin margin, slow debtors and short runway triggers the rules
    s = client.post(f"{C}/advisory/snapshots", headers=h, json={
        "client_id": c["id"], "as_at": "2026-06-30", "period_label": "FY26",
        "revenue_cents": 200_000_000, "gross_profit_cents": 60_000_000, "expenses_cents": 196_000_000, "net_profit_cents": 4_000_000,
        "cash_cents": 3_000_000, "receivables_cents": 45_000_000, "payables_cents": 22_000_000, "inventory_cents": 8_000_000,
        "debt_cents": 60_000_000, "equity_cents": 30_000_000, "tax_provision_cents": 200_000})
    assert s.status_code == 201, s.text
    s = s.json()
    k = s["kpis"]
    assert k["net_margin_pct"] == 2.0 and k["gross_margin_pct"] == 30.0 and round(k["debtor_days"]) == 82
    assert k["current_ratio"] < 3 and k["cash_runway_months"] < 1 and k["debt_to_equity"] == 2.0
    assert s["health_band"] in ("watch", "needs_action") and s["source"] == "manual" and s["simulated"] is False

    alerts = client.get(f"{C}/advisory/alerts", headers=h, params={"client_id": c["id"]}).json()
    codes = {a["code"] for a in alerts}
    assert {"low_runway", "slow_debtors", "thin_margin", "high_gearing", "tax_unprovisioned"} <= codes
    runway = next(a for a in alerts if a["code"] == "low_runway")
    assert runway["severity"] == "action" and runway["recommendation"] and runway["auto"] is True
    assert any(n["kind"] == "advisory.alert" for n in client.get(f"{C}/notifications", headers=h).json())

    # a better snapshot clears the alerts that no longer apply
    s2 = client.post(f"{C}/advisory/snapshots", headers=h, json={
        "client_id": c["id"], "as_at": "2026-12-31", "period_label": "H1 FY27",
        "revenue_cents": 240_000_000, "gross_profit_cents": 96_000_000, "expenses_cents": 204_000_000, "net_profit_cents": 36_000_000,
        "cash_cents": 60_000_000, "receivables_cents": 26_000_000, "payables_cents": 18_000_000, "inventory_cents": 8_000_000,
        "debt_cents": 20_000_000, "equity_cents": 66_000_000, "tax_provision_cents": 9_000_000}).json()
    assert s2["health_band"] == "good" and s2["health_score"] >= 70
    open_alerts = {a["code"] for a in client.get(f"{C}/advisory/alerts", headers=h, params={"client_id": c["id"]}).json()}
    assert open_alerts == set() or open_alerts <= {"tight_liquidity"}

    # meeting: prepared from the numbers, held with decisions and actions, published to the portal
    m = client.post(f"{C}/advisory/meetings", headers=h, json={"client_id": c["id"], "kind": "quarterly"}).json()
    assert m["status"] == "scheduled" and m["snapshot_id"] == s2["id"]
    m = client.post(f"{C}/advisory/meetings/{m['id']}/prepare", headers=h).json()
    assert m["status"] == "prepared" and len(m["agenda"]) >= 2
    assert m["agenda"][0]["title"] == "Where the business is" and "net margin" in (m["agenda"][0]["note"] or "")
    staff = client.get(f"{C}/crm/staff", headers=h).json()[0]
    m = client.post(f"{C}/advisory/meetings/{m['id']}/hold", headers=h, json={
        "summary": "Trading has recovered; focus now on holding margin and keeping debtor days under 45.",
        "decisions": {"Where the business is": "Agreed the position; owner comfortable with current facility."},
        "actions": [{"client_id": c["id"], "title": "Send monthly debtor report", "owner_side": "practice", "owner_membership_id": staff["membership_id"], "due_on": "2027-01-15"},
                    {"client_id": c["id"], "title": "Review pricing on maintenance contracts", "owner_side": "client", "owner_label": "Gavin", "due_on": "2027-02-01"}]}).json()
    assert m["status"] == "held" and m["held_at"] and len(m["actions"]) == 2
    assert m["agenda"][0]["decision"].startswith("Agreed the position")
    # the practice-owned action is mirrored into CRM tasks
    tasks = client.get(f"{C}/crm/tasks", headers=h, params={"status": "open"}).json()
    assert any(t["title"] == "Send monthly debtor report" and t["module_key"] == "advisory" and t["assignee_name"] == "Priya Nair" for t in tasks)
    mine = [a for a in client.get(f"{C}/advisory/actions", headers=h, params={"client_id": c["id"]}).json()]
    assert {a["owner_side"] for a in mine} == {"practice", "client"}

    # publishing posts the summary into the client portal thread
    ct = client.post(f"{C}/crm/clients/{c['id']}/contacts", headers=h, json={"first_name": "Gavin", "last_name": "Marlow", "email": "gavin@marlow.example", "is_primary": True}).json()
    client.post(f"{C}/client/contacts/{ct['id']}/invite", headers=h)
    m = client.post(f"{C}/advisory/meetings/{m['id']}/publish", headers=h).json()
    assert m["status"] == "published" and m["published_at"]
    thread = client.get(f"{C}/client/clients/{c['id']}/messages", headers=h).json()
    assert thread and "Trading has recovered" in thread[-1]["body"] and "Send monthly debtor report" in thread[-1]["body"]

    # completing an action closes the mirrored task
    act = next(a for a in mine if a["owner_side"] == "practice")
    done = client.patch(f"{C}/advisory/actions/{act['id']}", headers=h, json={"status": "done"}).json()
    assert done["status"] == "done" and done["completed_at"]
    assert all(t["title"] != "Send monthly debtor report" for t in client.get(f"{C}/crm/tasks", headers=h, params={"status": "open"}).json())

    ov = client.get(f"{C}/advisory/overview", headers=h).json()
    assert ov["clients_with_snapshots"] == 1 and ov["meetings_held_90d"] == 1 and ov["open_actions"] == 1 and ov["avg_health_score"] >= 70


def test_advisory_reads_figures_from_a_synced_workpaper(client):
    h, c = _tenant(client)
    p = client.post(f"{C}/workpapers/packs", headers=h, json={"client_id": c["id"], "pack_type": "financial_statements", "period_label": "FY26", "period_end": "2026-06-30"}).json()
    client.post(f"{C}/workpapers/ledger/connect", headers=h, json={"client_id": c["id"]})
    client.post(f"{C}/workpapers/packs/{p['id']}/sync", headers=h)
    s = client.post(f"{C}/advisory/snapshots", headers=h, json={"client_id": c["id"], "workpaper_id": p["id"], "as_at": "2026-06-30", "period_label": "FY26"})
    assert s.status_code == 201, s.text
    s = s.json()
    assert s["source"] == "workpapers" and s["simulated"] is True and s["workpaper_id"] == p["id"]
    assert s["revenue_cents"] and s["expenses_cents"] and s["cash_cents"] and s["net_profit_cents"] is not None
    assert "net_margin_pct" in s["kpis"] and "current_ratio" in s["kpis"] and s["health_score"] is not None
    view = client.get(f"{C}/advisory/clients/{c['id']}", headers=h).json()
    assert view["latest"]["id"] == s["id"] and view["latest"]["simulated"] is True


def test_advisory_isolation(client):
    h, c = _tenant(client)
    s = client.post(f"{C}/advisory/snapshots", headers=h, json={"client_id": c["id"], "revenue_cents": 100_000_00, "expenses_cents": 80_000_00, "net_profit_cents": 20_000_00}).json()
    b = signup(client, practice="B Co", email="b@b.example")
    hb = auth(b["tokens"])
    client.post(f"{C}/subscriptions", headers=hb, json={"module_key": "advisory"})
    assert client.get(f"{C}/advisory/clients/{c['id']}", headers=hb).status_code == 404
    assert client.get(f"{C}/advisory/snapshots", headers=hb).json() == []
    assert client.get(f"{C}/advisory/alerts", headers=hb).json() == []
