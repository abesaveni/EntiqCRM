from tests.conftest import auth, signup


def test_gate_403_with_upsell_then_200_after_subscribe(client):
    out = signup(client)
    h = auth(out["tokens"])
    r = client.get("/api/v1/dev/probe/verify", headers=h)
    assert r.status_code == 403
    d = r.json()["detail"]
    assert d["error"] == "module_not_subscribed" and d["module"] == "verify"
    assert d["upsell"]["shortName"] == "Verify" and d["upsell"]["addPath"] == "/hq/modules/verify"

    s = client.post("/api/v1/subscriptions", headers=h, json={"module_key": "verify"})
    assert s.status_code == 201
    assert "verify" in s.json()["added"] and "documents" in s.json()["added"]  # verify requires documents
    assert s.json()["entitlements"]["verify"] is True
    assert client.get("/api/v1/dev/probe/verify", headers=h).status_code == 200


def test_base_bundle_always_entitled(client):
    h = auth(signup(client)["tokens"])
    assert client.get("/api/v1/dev/probe/crm", headers=h).status_code == 200
    assert client.get("/api/v1/dev/probe/hq", headers=h).status_code == 200


def test_dependency_closure_and_cascade_cancel(client):
    h = auth(signup(client)["tokens"])
    s = client.post("/api/v1/subscriptions", headers=h, json={"module_key": "advisory"})
    assert s.status_code == 201
    assert set(s.json()["added"]) == {"documents", "workpapers", "advisory"}  # advisory→workpapers→documents
    d = client.delete("/api/v1/subscriptions/advisory", headers=h)
    assert d.status_code == 200
    st = {x["module_key"]: x["status"] for x in d.json()["subscriptions"]}
    assert st["advisory"] == "cancelled" and st["workpapers"] == "cancelled" and st["documents"] == "cancelled"
    assert st["crm"] == "trialing"  # base untouched


def test_cannot_buy_planned_or_internal_or_base(client):
    h = auth(signup(client)["tokens"])
    assert client.post("/api/v1/subscriptions", headers=h, json={"module_key": "capital"}).status_code == 400
    assert client.post("/api/v1/subscriptions", headers=h, json={"module_key": "control"}).status_code == 400
    assert client.post("/api/v1/subscriptions", headers=h, json={"module_key": "crm"}).status_code == 400
    assert client.delete("/api/v1/subscriptions/crm", headers=h).status_code == 400


def test_catalogue_excludes_internal_and_flags_state(client):
    h = auth(signup(client)["tokens"])
    items = client.get("/api/v1/modules", headers=h).json()
    keys = {i["manifest"]["key"] for i in items}
    assert "control" not in keys and len(items) == 23
    byk = {i["manifest"]["key"]: i for i in items}
    assert byk["crm"]["base"] and byk["crm"]["entitled"]
    assert not byk["verify"]["entitled"] and byk["verify"]["purchasable"]
    assert not byk["capital"]["purchasable"]


def test_lifecycle_suspended_is_read_only_cancelled_is_locked_out(client):
    h = auth(signup(client)["tokens"])
    r = client.post("/api/v1/dev/lifecycle", headers=h, json={"status": "suspended"})
    assert r.status_code == 200 and r.json()["read_only"] is True
    assert client.get("/api/v1/me", headers=h).status_code == 200                       # reads fine
    assert client.get("/api/v1/dev/probe/crm", headers=h).status_code == 200            # entitled, read
    assert client.post("/api/v1/subscriptions", headers=h, json={"module_key": "verify"}).status_code == 423  # writes locked
    assert client.patch("/api/v1/tenant", headers=h, json={"name": "New"}).status_code == 423

    client.post("/api/v1/dev/lifecycle", headers=h, json={"status": "cancelled"})
    r = client.get("/api/v1/dev/probe/crm", headers=h)
    assert r.status_code == 403 and r.json()["detail"]["error"] == "tenant_cancelled"
    me = client.get("/api/v1/me", headers=h).json()
    assert me["entitlements"]["crm"] is False and me["tenant"]["status"] == "cancelled"


def test_staff_needs_module_grant_owner_does_not(client):
    out = signup(client)
    h = auth(out["tokens"])
    client.post("/api/v1/subscriptions", headers=h, json={"module_key": "sign"})
    inv = client.post("/api/v1/users/invite", headers=h, json={"email": "sam@ashfield.example", "role": "staff", "modules": []}).json()
    acc = client.post("/api/v1/auth/accept-invite", json={"token": inv["accept_url"].split("token=")[1], "full_name": "Sam W", "password": "Correct-Horse-Battery-9!"}).json()
    hs = auth(acc["tokens"])
    assert client.get("/api/v1/dev/probe/crm", headers=hs).status_code == 200   # base: no grant needed
    r = client.get("/api/v1/dev/probe/sign", headers=hs)
    assert r.status_code == 403 and r.json()["detail"]["error"] == "module_not_granted"
    # Owner ticks the box in the access matrix
    members = client.get("/api/v1/users", headers=h).json()
    sam = next(m for m in members if m["email"] == "sam@ashfield.example")
    g = client.patch(f"/api/v1/users/{sam['membership_id']}/grants", headers=h, json={"modules": ["sign"]})
    assert g.status_code == 200 and g.json()["modules"] == ["sign"]
    assert client.get("/api/v1/dev/probe/sign", headers=hs).status_code == 200
    # Staff cannot manage subscriptions
    assert client.post("/api/v1/subscriptions", headers=hs, json={"module_key": "verify"}).status_code == 403
