import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import auth, signup

C = "/api/v1/crm"


def _client(client, h, name="Ashfield Family Trust", **kw):
    body = {"name": name, "client_type": "Trust", "abn": "62 114 887 302", "stage": "Active", **kw}
    r = client.post(f"{C}/clients", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_list_get_client_with_normalised_abn(client):
    h = auth(signup(client)["tokens"])
    c = _client(client, h)
    assert c["abn"] == "62114887302" and c["abn_formatted"] == "62 114 887 302" and c["stage"] == "Active"
    page = client.get(f"{C}/clients", headers=h).json()
    assert page["total"] == 1 and page["items"][0]["name"] == "Ashfield Family Trust"
    assert client.get(f"{C}/clients/{c['id']}", headers=h).json()["client_type"] == "Trust"
    tl = client.get(f"{C}/clients/{c['id']}/timeline", headers=h).json()
    assert tl[0]["kind"] == "client.created" and tl[0]["module_key"] == "crm"


def test_invalid_abn_rejected(client):
    h = auth(signup(client)["tokens"])
    r = client.post(f"{C}/clients", headers=h, json={"name": "X", "abn": "123"})
    assert r.status_code == 422


def test_search_filters_and_sort(client):
    h = auth(signup(client)["tokens"])
    _client(client, h, "Marlow Constructions Pty Ltd", client_type="Company", abn="48 902 337 115", stage="Active")
    _client(client, h, "Greenline Logistics Pty Ltd", client_type="Company", abn="55 120 998 431", stage="Proposal")
    _client(client, h, "Elena Reyes", client_type="Individual", abn=None, stage="Lead")
    assert client.get(f"{C}/clients", headers=h, params={"q": "marlow"}).json()["total"] == 1
    assert client.get(f"{C}/clients", headers=h, params={"q": "48902337115"}).json()["total"] == 1   # by ABN digits
    assert client.get(f"{C}/clients", headers=h, params={"stage": "Lead"}).json()["total"] == 1
    assert client.get(f"{C}/clients", headers=h, params={"client_type": "Company"}).json()["total"] == 2
    names = [x["name"] for x in client.get(f"{C}/clients", headers=h, params={"sort": "-name"}).json()["items"]]
    assert names == sorted(names, reverse=True)
    hits = client.get(f"{C}/search", headers=h, params={"q": "green"}).json()
    assert hits and hits[0]["type"] == "client"


def test_stage_change_writes_timeline_and_sets_since(client):
    h = auth(signup(client)["tokens"])
    c = _client(client, h, "O'Connor Holdings", client_type="Company", abn="80 345 667 120", stage="Lead")
    assert c["since"] is None
    r = client.post(f"{C}/clients/{c['id']}/stage", headers=h, json={"stage": "Active", "reason": "engagement signed"})
    assert r.status_code == 200 and r.json()["stage"] == "Active" and r.json()["since"] is not None
    kinds = [e["kind"] for e in client.get(f"{C}/clients/{c['id']}/timeline", headers=h).json()]
    assert kinds[0] == "stage.changed"


def test_contacts_primary_uniqueness_and_relationships(client):
    h = auth(signup(client)["tokens"])
    c = _client(client, h)
    p1 = client.post(f"{C}/clients/{c['id']}/contacts", headers=h, json={"first_name": "Margaret", "last_name": "Ashfield", "role": "Trustee", "is_primary": True, "email": "m@ashfield.example"}).json()
    p2 = client.post(f"{C}/clients/{c['id']}/contacts", headers=h, json={"first_name": "Tom", "last_name": "Ashfield", "role": "Beneficiary", "is_primary": True}).json()
    contacts = client.get(f"{C}/clients/{c['id']}/contacts", headers=h).json()
    assert [x["is_primary"] for x in contacts] == [True, False] and contacts[0]["id"] == p2["id"]
    got = client.get(f"{C}/clients/{c['id']}", headers=h).json()
    assert got["contact_count"] == 2 and got["primary_contact"]["first_name"] == "Tom"
    r = client.post(f"{C}/relationships", headers=h, json={"from_type": "contact", "from_id": p1["id"], "to_type": "client", "to_id": c["id"], "kind": "trustee_of"})
    assert r.status_code == 201 and r.json()["from_label"] == "Margaret Ashfield" and r.json()["to_label"] == "Ashfield Family Trust"
    rels = client.get(f"{C}/clients/{c['id']}/relationships", headers=h).json()
    assert len(rels) == 1
    assert client.delete(f"{C}/relationships/{rels[0]['id']}", headers=h).status_code == 204
    assert client.get(f"{C}/clients/{c['id']}/relationships", headers=h).json() == []
    # contact directory search
    assert any(x["email"] == "m@ashfield.example" for x in client.get(f"{C}/contacts", headers=h, params={"q": "margaret"}).json())


def test_tasks_notes_and_home_aggregates(client):
    out = signup(client)
    h = auth(out["tokens"])
    c = _client(client, h)
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    soon = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    t1 = client.post(f"{C}/tasks", headers=h, json={"title": "Obtain signed distribution minute", "client_id": c["id"], "due_at": past, "priority": "High"}).json()
    client.post(f"{C}/tasks", headers=h, json={"title": "Confirm TFN", "client_id": c["id"], "due_at": soon})
    assert t1["overdue"] is True and t1["client_name"] == "Ashfield Family Trust"
    home = client.get(f"{C}/home", headers=h).json()
    assert home["overdue_tasks"] == 1 and home["due_this_week"] == 1 and home["total_clients"] == 1
    done = client.post(f"{C}/tasks/{t1['id']}/complete", headers=h).json()
    assert done["status"] == "done" and done["done_at"]
    assert client.get(f"{C}/home", headers=h).json()["overdue_tasks"] == 0
    n = client.post(f"{C}/clients/{c['id']}/notes", headers=h, json={"body": "Called Margaret re: distribution minute.\nWill sign this week.", "pinned": True}).json()
    assert n["author_name"] == "Priya Nair" and n["pinned"]
    kinds = [e["kind"] for e in client.get(f"{C}/clients/{c['id']}/timeline", headers=h).json()]
    assert {"task.created", "task.completed", "note.added", "client.created"} <= set(kinds)
    assert client.get(f"{C}/clients/{c['id']}", headers=h).json()["open_task_count"] == 1


def test_pipeline_segments_duplicates(client):
    h = auth(signup(client)["tokens"])
    _client(client, h, "Marlow Constructions Pty Ltd", client_type="Company", abn="48 902 337 115", stage="Active", tags=["Building"])
    _client(client, h, "Marlow Constructions", client_type="Company", abn="48 902 337 115", stage="Lead")   # same ABN → duplicate
    _client(client, h, "Greenline Logistics", client_type="Company", abn=None, stage="Proposal")
    cols = {c["stage"]: c["count"] for c in client.get(f"{C}/pipeline", headers=h).json()}
    assert cols["Active"] == 1 and cols["Lead"] == 1 and cols["Proposal"] == 1
    seg = client.post(f"{C}/segments", headers=h, json={"name": "Active companies", "filters": {"stage": "Active", "client_type": "Company"}}).json()
    assert seg["member_count"] == 1
    assert client.get(f"{C}/segments/{seg['id']}/members", headers=h).json()["total"] == 1
    dups = client.get(f"{C}/duplicates", headers=h).json()
    assert len(dups) == 1 and dups[0]["reason"] == "abn" and len(dups[0]["clients"]) == 2


def test_archive_hides_but_keeps(client):
    h = auth(signup(client)["tokens"])
    c = _client(client, h)
    assert client.delete(f"{C}/clients/{c['id']}", headers=h).json()["archived_at"]
    assert client.get(f"{C}/clients", headers=h).json()["total"] == 0
    assert client.get(f"{C}/clients", headers=h, params={"include_archived": True}).json()["total"] == 1
    assert client.get(f"{C}/clients/{c['id']}", headers=h).status_code == 200  # record and history remain


def test_crm_is_tenant_isolated_and_gated(client):
    a = signup(client, practice="A Co", email="a@a.example")
    b = signup(client, practice="B Co", email="b@b.example")
    c = _client(client, auth(a["tokens"]))
    assert client.get(f"{C}/clients/{c['id']}", headers=auth(b["tokens"])).status_code == 404
    assert client.get(f"{C}/clients", headers=auth(b["tokens"])).json()["total"] == 0
    # staff member without grants still reaches CRM (base plan) and can edit
    inv = client.post("/api/v1/users/invite", headers=auth(a["tokens"]), json={"email": "sam@a.example", "role": "staff", "modules": []}).json()
    acc = client.post("/api/v1/auth/accept-invite", json={"token": inv["accept_url"].split("token=")[1], "full_name": "Sam W", "password": "Correct-Horse-Battery-9!"}).json()
    hs = auth(acc["tokens"])
    assert client.get(f"{C}/clients", headers=hs).json()["total"] == 1
    assert client.post(f"{C}/tasks", headers=hs, json={"title": "Follow up"}).status_code == 201
    # suspended → read-only
    client.post("/api/v1/dev/lifecycle", headers=auth(a["tokens"]), json={"status": "suspended"})
    assert client.get(f"{C}/clients", headers=auth(a["tokens"])).status_code == 200
    assert client.post(f"{C}/clients", headers=auth(a["tokens"]), json={"name": "New"}).status_code == 423
