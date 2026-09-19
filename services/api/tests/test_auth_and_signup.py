from tests.conftest import STRONG_PW, auth, signup


def test_signup_creates_trialing_tenant_with_base_bundle(client):
    out = signup(client)
    s = out["session"]
    assert s["tenant"]["status"] == "trialing"
    assert s["tenant"]["card_on_file"] is True and s["tenant"]["card_last4"] == "4242"
    assert s["role"] == "owner"
    keys = {x["module_key"] for x in s["subscriptions"]}
    assert keys == {"hq", "crm"}          # the base bundle; billing is now a purchasable module (19)
    assert all(x["status"] == "trialing" for x in s["subscriptions"])
    assert s["entitlements"]["crm"] is True and s["entitlements"]["hq"] is True
    assert s["entitlements"]["verify"] is False
    assert s["pricing"]["base_plan_cents"] == 9900 and s["pricing"]["base_plan_inc_gst_cents"] == 10890
    assert s["pricing"]["trial_days"] == 15


def test_signup_rejects_weak_password(client):
    r = client.post("/api/v1/auth/signup", json={"practice_name": "X Co", "full_name": "A B", "email": "a@b.example", "password": "short", "payment_method": {"last4": "1111"}})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "weak_password"


def test_duplicate_email_conflicts(client):
    signup(client)
    r = client.post("/api/v1/auth/signup", json={"practice_name": "Other", "full_name": "P N", "email": "priya@ashfield.example", "password": STRONG_PW, "payment_method": {"last4": "4242"}})
    assert r.status_code == 409


def test_login_single_tenant_issues_tokens_and_me_works(client):
    signup(client)
    r = client.post("/api/v1/auth/login", json={"email": "priya@ashfield.example", "password": STRONG_PW})
    assert r.status_code == 200
    body = r.json()
    assert body["requires_tenant_selection"] is False and body["tokens"]
    me = client.get("/api/v1/me", headers=auth(body["tokens"]))
    assert me.status_code == 200 and me.json()["tenant"]["name"] == "Ashfield Partners"


def test_login_wrong_password_generic_401_and_lockout(client):
    signup(client)
    for _ in range(8):
        r = client.post("/api/v1/auth/login", json={"email": "priya@ashfield.example", "password": "Wrong-Password-1!"})
    assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "priya@ashfield.example", "password": STRONG_PW})
    assert r.status_code == 423 and r.json()["detail"]["error"] == "account_locked"


def test_refresh_rotates_and_old_token_dies(client):
    out = signup(client)
    rt = out["tokens"]["refresh_token"]
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert r1.status_code == 200
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert r2.status_code == 401
    assert client.get("/api/v1/me", headers=auth(r1.json())).status_code == 200


def test_logout_revokes_access_token(client):
    out = signup(client)
    h = auth(out["tokens"])
    assert client.post("/api/v1/auth/logout", headers=h, json={"refresh_token": out["tokens"]["refresh_token"]}).status_code == 204
    assert client.get("/api/v1/me", headers=h).status_code == 401


def test_one_person_many_practices(client):
    """The identity fix: a user can belong to two tenants; login asks which one."""
    a = signup(client, practice="Ashfield Partners", email="owner@ashfield.example")
    b = signup(client, practice="Bellbird Advisory", email="owner@bellbird.example")
    inv = client.post("/api/v1/users/invite", headers=auth(b["tokens"]), json={"email": "owner@ashfield.example", "role": "admin", "modules": []})
    assert inv.status_code == 201
    token = inv.json()["accept_url"].split("token=")[1]
    acc = client.post("/api/v1/auth/accept-invite", json={"token": token, "full_name": "Owner A", "password": STRONG_PW})
    assert acc.status_code == 201 and acc.json()["session"]["tenant"]["name"] == "Bellbird Advisory"

    r = client.post("/api/v1/auth/login", json={"email": "owner@ashfield.example", "password": STRONG_PW})
    assert r.status_code == 200 and r.json()["requires_tenant_selection"] is True
    assert {t["name"] for t in r.json()["tenants"]} == {"Ashfield Partners", "Bellbird Advisory"}

    r2 = client.post("/api/v1/auth/login", json={"email": "owner@ashfield.example", "password": STRONG_PW, "tenant_id": a["session"]["tenant"]["id"]})
    assert r2.status_code == 200 and r2.json()["session"]["tenant"]["name"] == "Ashfield Partners"
    sw = client.post("/api/v1/auth/switch-tenant", headers=auth(r2.json()["tokens"]), json={"tenant_id": b["session"]["tenant"]["id"]})
    assert sw.status_code == 200 and sw.json()["session"]["tenant"]["name"] == "Bellbird Advisory" and sw.json()["session"]["role"] == "admin"
