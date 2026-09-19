"""M7: Documents (folders, search, retention) and Billing (invoices, payments, fee schedules, statements)."""
import io
from datetime import date, timedelta

from tests.conftest import auth, signup

C = "/api/v1"


def _tenant(client, modules=("documents",)):
    out = signup(client)
    h = auth(out["tokens"])
    for m in modules:
        assert client.post(f"{C}/subscriptions", headers=h, json={"module_key": m}).status_code == 201
    c = client.post(f"{C}/crm/clients", headers=h, json={"name": "Marlow Constructions Pty Ltd", "client_type": "Company", "stage": "Active"}).json()
    ct = client.post(f"{C}/crm/clients/{c['id']}/contacts", headers=h, json={"first_name": "Gavin", "last_name": "Marlow", "email": "gavin@marlow.example", "is_primary": True}).json()
    return h, c, ct


def _upload(client, h, cid, name, body=b"", kind="general", ct="application/pdf"):
    return client.post(f"{C}/documents", headers=h, files={"file": (name, io.BytesIO(body or b"%PDF-1.4 " + name.encode() * 20), ct)}, data={"client_id": cid, "kind": kind}).json()


# ------------------------------------------------------------------ Documents
def test_documents_folders_search_and_retention(client):
    h, c, _ = _tenant(client)
    b = signup(client, practice="B Co", email="b@b.example")
    assert client.get(f"{C}/documents-module/overview", headers=auth(b["tokens"])).status_code == 403

    folders = client.post(f"{C}/documents-module/folders/standard", headers=h, params={"client_id": c["id"]}).json()
    paths = {f["path"] for f in folders}
    assert {"Permanent", "Permanent/Constitution & deeds", "Tax", "Identity & AML"} <= paths
    assert next(f for f in folders if f["path"] == "Permanent/Constitution & deeds")["depth"] == 1
    custom = client.post(f"{C}/documents-module/folders", headers=h, json={"name": "FY26", "parent_id": next(f["id"] for f in folders if f["path"] == "Tax")}).json()
    assert custom["path"] == "Tax/FY26"
    assert client.post(f"{C}/documents-module/folders", headers=h, json={"name": "FY26", "parent_id": next(f["id"] for f in folders if f["path"] == "Tax")}).status_code == 409

    # a text upload is indexed and searchable; a PDF with a text layer too
    txt = _upload(client, h, c["id"], "trial balance FY26.csv", b"Account,Debit,Credit\nSales,0,482000\nWages and salaries,96500,0\n", kind="financial", ct="text/csv")
    pdf = _upload(client, h, c["id"], "ASIC extract.pdf", kind="legal")
    rows = client.post(f"{C}/documents-module/search", headers=h, json={"q": "wages"}).json()
    assert len(rows) == 1 and rows[0]["id"] == txt["id"] and rows[0]["text_source"] == "plain" and "wages" in (rows[0]["snippet"] or "")
    assert client.post(f"{C}/documents-module/search", headers=h, json={"q": "nothing here"}).json() == []
    # filename search still works for files with no text layer
    assert [r["id"] for r in client.post(f"{C}/documents-module/search", headers=h, json={"q": "asic"}).json()] == [pdf["id"]]

    # filing
    filed = client.post(f"{C}/documents-module/{txt['id']}/file", headers=h, json={"folder_id": custom["id"], "tags": ["FY26", "ledger"], "kind": "workpaper"}).json()
    assert filed["folder_path"] == "Tax/FY26" and filed["tags"] == ["FY26", "ledger"] and filed["kind"] == "workpaper"
    assert client.post(f"{C}/documents-module/search", headers=h, json={"folder_id": custom["id"]}).json()[0]["id"] == txt["id"]
    tree = client.get(f"{C}/documents-module/folders", headers=h, params={"client_id": c["id"]}).json()
    assert next(f for f in tree if f["path"] == "Tax/FY26")["document_count"] == 1

    # retention policies: seeded, applied, and the AML one places a hold
    pols = client.post(f"{C}/documents-module/policies/defaults", headers=h).json()
    assert {p["name"] for p in pols} >= {"AML/CTF records", "Signed agreements", "Tax and financial records", "General correspondence"}
    ident = _upload(client, h, c["id"], "drivers licence.pdf", kind="identity")
    stats = client.post(f"{C}/documents-module/policies/apply", headers=h).json()
    assert stats["indexed"] >= 3 and stats["held"] >= 1
    docs = {d["filename"]: d for d in client.get(f"{C}/documents", headers=h, params={"client_id": c["id"]}).json()}
    assert docs["drivers licence.pdf"]["retention_hold"] is True
    rows = client.get(f"{C}/documents-module/retention", headers=h, params={"days": 3650}).json()
    identity_row = next(r for r in rows if r["filename"] == "drivers licence.pdf")
    assert identity_row["policy_name"] == "AML/CTF records" and identity_row["action"] == "hold"
    assert identity_row["retain_until"][:4] == str(date.today().year + 7)
    wp_row = next(r for r in rows if r["filename"] == "trial balance FY26.csv")
    assert wp_row["retain_until"][:4] == str(date.today().year + 5)   # tax/financial policy, 5 years

    ov = client.get(f"{C}/documents-module/overview", headers=h).json()
    assert ov["documents"] == 3 and ov["searchable"] >= 1 and ov["on_hold"] >= 1 and ov["unfiled"] == 2 and ov["policies"] == 4
    assert ov["by_kind"]["identity"] == 1


def test_documents_isolation_and_module_gate(client):
    h, c, _ = _tenant(client, modules=())
    # without the module the base attachment API still works, but the module surface is closed
    d = _upload(client, h, c["id"], "note.pdf")
    assert d["id"] and client.post(f"{C}/documents-module/search", headers=h, json={}).status_code == 403
    client.post(f"{C}/subscriptions", headers=h, json={"module_key": "documents"})
    # documents uploaded before the module was added are indexed on demand
    assert client.post(f"{C}/documents-module/search", headers=h, json={}).json()[0]["text_source"] == "none"
    assert client.post(f"{C}/documents-module/reindex", headers=h).json()["indexed"] == 1
    b = signup(client, practice="B Co", email="b@b.example")
    hb = auth(b["tokens"])
    client.post(f"{C}/subscriptions", headers=hb, json={"module_key": "documents"})
    assert client.post(f"{C}/documents-module/search", headers=hb, json={}).json() == []
    assert client.get(f"{C}/documents-module/folders", headers=hb).json() == []


# ------------------------------------------------------------------ Billing
def test_billing_invoice_payment_statement_and_aged(client):
    h, c, ct = _tenant(client, modules=("billing",))
    inv = client.post(f"{C}/practice-billing/invoices", headers=h, json={"client_id": c["id"], "period_label": "Sep 2026", "terms_days": 14,
                                                                          "lines": [{"description": "Quarterly BAS — Q1 FY27", "unit_cents": 55000},
                                                                                    {"description": "Bookkeeping — September", "quantity": 3, "unit_cents": 22000},
                                                                                    {"description": "ASIC fee (no GST)", "unit_cents": 29000, "gst": False}]})
    assert inv.status_code == 201, inv.text
    inv = inv.json()
    assert inv["number"].startswith("INV-") and inv["status"] == "draft"
    assert inv["subtotal_cents"] == 55000 + 66000 + 29000 and inv["gst_cents"] == 12100 and inv["total_cents"] == 162100
    assert inv["balance_cents"] == 162100 and inv["contact_email"] == "gavin@marlow.example"

    sent = client.post(f"{C}/practice-billing/invoices/{inv['id']}/send", headers=h).json()
    assert sent["status"] == "sent" and sent["sent_at"]
    msg = [m for m in client.get(f"{C}/dev/outbound", headers=h).json() if m["template"] == "invoice_sent"][0]
    assert inv["number"] in msg["subject"] and "1,621.00" in msg["body_text"]

    part = client.post(f"{C}/practice-billing/invoices/{inv['id']}/payments", headers=h, json={"amount_cents": 62100, "method": "bank_transfer", "reference": "EFT 8841"}).json()
    assert part["status"] == "part_paid" and part["paid_cents"] == 62100 and part["balance_cents"] == 100000
    assert client.post(f"{C}/practice-billing/invoices/{inv['id']}/payments", headers=h, json={"amount_cents": 200000}).status_code == 400   # overpayment
    paid = client.post(f"{C}/practice-billing/invoices/{inv['id']}/payments", headers=h, json={"amount_cents": 100000}).json()
    assert paid["status"] == "paid" and paid["balance_cents"] == 0 and paid["paid_at"] and len(paid["payments"]) == 2
    assert client.post(f"{C}/practice-billing/invoices/{inv['id']}/void", headers=h, json={"reason": "wrong client"}).status_code == 409   # has payments

    # a second, overdue invoice shows in the statement and the aged summary
    old = (date.today() - timedelta(days=45)).isoformat()
    inv2 = client.post(f"{C}/practice-billing/invoices", headers=h, json={"client_id": c["id"], "issued_on": old, "terms_days": 14, "send_now": True,
                                                                          "lines": [{"description": "Annual financial statements", "unit_cents": 220000}]}).json()
    assert inv2["status"] == "overdue" and inv2["days_overdue"] == 31 and inv2["overdue"] is True
    st = client.get(f"{C}/practice-billing/clients/{c['id']}/statement", headers=h).json()
    assert st["outstanding_cents"] == 242000 and st["overdue_cents"] == 242000 and len(st["invoices"]) == 2
    ov = client.get(f"{C}/practice-billing/overview", headers=h).json()
    assert ov["outstanding_cents"] == 242000 and ov["overdue_count"] == 1 and ov["paid_30d_cents"] == 162100
    aged = ov["aged"][0]
    assert aged["client_name"] == c["name"] and aged["d60_cents"] == 242000 and aged["oldest_days"] == 31

    # chase: manual reminder, then the lifecycle job (once a week, three times max)
    rem = client.post(f"{C}/practice-billing/invoices/{inv2['id']}/remind", headers=h).json()
    assert rem["reminders_sent"] == 1
    assert any(m["template"] == "invoice_reminder" and "Overdue" in m["subject"] for m in client.get(f"{C}/dev/outbound", headers=h).json())
    from app.core.database import SessionLocal
    from app.core.security import utcnow
    from app.jobs import lifecycle
    with SessionLocal() as db:
        stats = lifecycle.run(db, now=utcnow() + timedelta(days=8))
    assert stats["invoice_reminders"] == 1
    assert client.get(f"{C}/practice-billing/invoices/{inv2['id']}", headers=h).json()["reminders_sent"] == 2

    tl = [e["kind"] for e in client.get(f"{C}/crm/clients/{c['id']}/timeline", headers=h).json()]
    assert {"invoice.created", "invoice.sent", "payment.received", "invoice.reminded"} <= set(tl)


def test_billing_fee_schedules_generate_and_start_interlink(client):
    h, c, _ = _tenant(client, modules=("billing", "start", "sign", "verify"))
    s = client.post(f"{C}/practice-billing/schedules", headers=h, json={"client_id": c["id"], "name": "Monthly bookkeeping", "frequency": "monthly", "amount_cents": 66000, "day_of_month": 1,
                                                                        "start_on": (date.today().replace(day=1)).isoformat()}).json()
    assert s["total_cents"] == 72600 and s["annualised_cents"] == 871200 and s["next_issue_on"]
    gen = client.post(f"{C}/practice-billing/schedules/generate", headers=h, params={"as_of": date.today().isoformat()}).json()
    assert gen["created"] == 1 and gen["invoices"][0]["total_cents"] == 72600 and gen["invoices"][0]["fee_schedule_id"] == s["id"]
    assert client.post(f"{C}/practice-billing/schedules/generate", headers=h, params={"as_of": date.today().isoformat()}).json()["created"] == 0   # idempotent per period
    nxt = client.get(f"{C}/practice-billing/schedules", headers=h).json()[0]
    assert nxt["last_invoice_period"] and date.fromisoformat(nxt["next_issue_on"]) > date.today().replace(day=1)
    off = client.post(f"{C}/practice-billing/schedules/{s['id']}/toggle", headers=h).json()
    assert off["is_active"] is False

    # Start → Billing: activating a client creates fee schedules from the accepted proposal
    o = client.post(f"{C}/start/onboardings", headers=h, json={"prospect_name": "Northfield Holdings", "contact_first_name": "Ava", "contact_email": "ava@northfield.example"}).json()
    tok = o["invite_url"].rsplit("/", 1)[1]
    client.get(f"{C}/start/public/{tok}")
    client.post(f"{C}/start/public/{tok}/stages/2", json={"legal_name": "Northfield Holdings Pty Ltd", "entity_type": "Company", "tax_residency": "australia", "contact_name": "Ava North", "contact_email": "ava@northfield.example"})
    client.post(f"{C}/start/public/{tok}/stages/3", json={"answers": {"business_description": "Builders", "turnover_band": "$1m–$5m", "employees_band": "5–19", "gst_registered": True, "payroll": True, "software": "Xero", "lodgements_outstanding": False}})
    pv = client.get(f"{C}/start/public/{tok}").json()
    for r in pv["document_requests"]:
        if r["required"]:
            client.post(f"{C}/start/public/{tok}/documents/{r['key']}", files={"file": (f"{r['key']}.pdf", b"%PDF-1.4 x", "application/pdf")})
    client.post(f"{C}/start/public/{tok}/stages/4")
    client.post(f"{C}/start/onboardings/{o['id']}/stages/4", headers=h)
    client.post(f"{C}/start/public/{tok}/stages/5", json={"parties": [{"name": "Ava North", "role": "Director", "is_beneficial_owner": True}], "ownership_complete": True})
    pv = client.get(f"{C}/start/public/{tok}").json()
    chosen = [x for x in pv["services"] if x["basis"] in ("monthly", "quarterly", "annual")][:2]
    client.post(f"{C}/start/public/{tok}/stages/6", json={"service_ids": [x["id"] for x in chosen]})
    client.post(f"{C}/start/onboardings/{o['id']}/proposal", headers=h, json={"lines": [{"service_id": x["id"], "name": x["name"], "basis": x["basis"], "amount_cents": x["amount_cents"], "gst": True} for x in chosen]})
    client.post(f"{C}/start/public/{tok}/stages/7", json={"accepted_by_name": "Ava North", "accept": True})
    doc = client.post(f"{C}/documents", headers=h, files={"file": ("LoE.pdf", b"%PDF-1.4 loe", "application/pdf")}, data={"client_id": o["client_id"], "kind": "agreement"}).json()
    client.post(f"{C}/start/onboardings/{o['id']}/stages/8", headers=h, json={"document_id": doc["id"]})
    sign_tok = [m for m in client.get(f"{C}/dev/outbound", headers=h).json() if m["template"] == "sign_request"][0]["body_text"].split("Review and sign:\n")[1].split("\n")[0].rsplit("/", 1)[1]
    client.post(f"{C}/sign/public/{sign_tok}/sign", json={"full_name": "Ava North", "signature_kind": "typed", "signature_data": "Ava North", "consent": True})
    contacts = client.get(f"{C}/crm/clients/{o['client_id']}/contacts", headers=h).json()
    client.post(f"{C}/verify/clients/{o['client_id']}/verifications", headers=h, json={"subject_type": "individual", "contact_id": contacts[0]["id"]})
    client.post(f"{C}/verify/clients/{o['client_id']}/screen", headers=h, json={})
    client.post(f"{C}/start/public/{tok}/mandate", json={"method": "direct_debit", "accepted_terms": True})
    client.post(f"{C}/start/onboardings/{o['id']}/gates/run", headers=h)
    client.post(f"{C}/start/onboardings/{o['id']}/stages/10", headers=h, json={"partner_signoff": True, "margin_ok": True, "risk_signoff": True})
    det = client.post(f"{C}/start/onboardings/{o['id']}/stages/11", headers=h).json()
    assert det["status"] == "activated"
    scheds = client.get(f"{C}/practice-billing/schedules", headers=h, params={"client_id": o["client_id"]}).json()
    assert len(scheds) == len(chosen) and all(x["source"] == "start" for x in scheds)
    assert {x["name"] for x in scheds} == {x["name"] for x in chosen}
