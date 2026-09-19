"""Testing switches: a $0 base plan and a skippable card, and the guard that keeps both out of production."""
from datetime import timedelta

from tests.conftest import STRONG_PW, auth

C = "/api/v1"


def _signup(client, *, card=True, email="priya@ashfield.example"):
    body = {"practice_name": "Ashfield Partners", "full_name": "Priya Nair", "email": email, "password": STRONG_PW}
    if card:
        body["payment_method"] = {"last4": "4242", "brand": "visa"}
    return client.post(f"{C}/auth/signup", json=body)


def test_card_is_required_by_default(client):
    r = _signup(client, card=False)
    assert r.status_code == 422 and r.json()["detail"]["error"] == "card_required"
    assert _signup(client).status_code == 201


def test_public_pricing_tells_the_signup_page_what_to_do(client):
    p = client.get(f"{C}/pricing")
    assert p.status_code == 200
    p = p.json()
    assert p["base_plan_cents"] == 9900 and p["base_plan_inc_gst_cents"] == 10890 and p["trial_days"] == 15
    assert p["require_card"] is True and p["free_mode"] is False and p["currency"] == "AUD"


def test_card_can_be_skipped_when_configured(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "REQUIRE_CARD_AT_SIGNUP", False)
    p = client.get(f"{C}/pricing").json()
    assert p["require_card"] is False
    r = _signup(client, card=False)
    assert r.status_code == 201, r.text
    h = auth(r.json()["tokens"])
    sess = client.get(f"{C}/me", headers=h).json()
    assert sess["tenant"]["status"] == "trialing" and sess["tenant"]["card_on_file"] is False and sess["tenant"]["card_last4"] is None
    assert sess["pricing"]["require_card"] is False
    # the practice works exactly as it would with a card on file
    assert client.post(f"{C}/crm/clients", headers=h, json={"name": "Marlow Constructions"}).status_code == 201
    assert client.post(f"{C}/subscriptions", headers=h, json={"module_key": "verify"}).status_code == 201


def test_free_mode_converts_the_trial_without_charging(client, monkeypatch):
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.core.security import utcnow
    from app.jobs import lifecycle
    monkeypatch.setattr(settings, "BASE_PLAN_PRICE_CENTS", 0)
    monkeypatch.setattr(settings, "REQUIRE_CARD_AT_SIGNUP", False)

    p = client.get(f"{C}/pricing").json()
    assert p["free_mode"] is True and p["base_plan_cents"] == 0 and p["base_plan_inc_gst_cents"] == 0

    r = _signup(client, card=False)
    assert r.status_code == 201
    h = auth(r.json()["tokens"])
    assert client.get(f"{C}/me", headers=h).json()["pricing"]["free_mode"] is True

    with SessionLocal() as db:
        stats = lifecycle.run(db, now=utcnow() + timedelta(days=16))
    assert stats["activated"] == 1 and stats["charge_failed"] == 0

    sess = client.get(f"{C}/me", headers=h).json()
    assert sess["tenant"]["status"] == "active"
    ev = [e for e in client.get(f"{C}/billing/events", headers=h).json() if e["kind"].startswith("charge.")]
    assert len(ev) == 1 and ev[0]["kind"] == "charge.waived" and ev[0]["status"] == "waived"
    assert ev[0]["amount_cents"] == 0 and ev[0]["total_cents"] == 0
    assert "nothing to charge" in ev[0]["detail"]["note"].lower()
    # the ledger is still a verifiable chain
    from app.services import billing_service
    with SessionLocal() as db:
        assert billing_service.verify_chain(db)["ok"] is True


def test_production_refuses_the_testing_switches(monkeypatch):
    from app.core.config import settings, verify_production_safety
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "BASE_PLAN_PRICE_CENTS", 0)
    monkeypatch.setattr(settings, "REQUIRE_CARD_AT_SIGNUP", False)
    problems = verify_production_safety()
    assert any("BASE_PLAN_PRICE_CENTS is 0" in p for p in problems)
    assert any("REQUIRE_CARD_AT_SIGNUP is false" in p for p in problems)
