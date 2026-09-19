import io

from tests.conftest import auth, signup

C = "/api/v1/crm"

XERO_CSV = """*ContactName,AccountNumber,EmailAddress,FirstName,LastName,POAttentionTo,POAddressLine1,POAddressLine2,POAddressLine3,POAddressLine4,POCity,PORegion,POPostalCode,POCountry,PhoneNumber,MobileNumber,TaxNumber,Website,LegalName,CompanyNumber
Marlow Constructions Pty Ltd,MAR001,gavin@marlowcon.example,Gavin,Marlow,,12 Builder St,,,,Parramatta,NSW,2150,Australia,02 9000 1111,0401 220 556,48 902 337 115,https://marlowcon.example,Marlow Constructions Pty Limited,902337115
Ashfield Family Trust,ASH001,margaret@ashfield.example,Margaret,Ashfield,,4 Trust Ave,,,,Ashfield,NSW,2131,Australia,,0412 338 902,62114887302,,,
Elena Reyes,REY001,elena.reyes@example.com,Elena,Reyes,,9 Sole Trader Rd,,,,Newtown,NSW,2042,Australia,,0422 909 313,,,,
Northcote Super Fund,NOR001,,Ian,Northcote,,,,,,,,,Australia,,,19 663 004 972,,,
Marlow Constructions Pty Ltd,MAR001-DUP,dup@marlowcon.example,,,,,,,,,,,,,,48 902 337 115,,,
Bad ABN Co,BAD001,,,,,,,,,,,,,,,1234,,,
"""

MYOB_CSV = """Co./Last Name,First Name,Card ID,Card Status,Addr 1 - Line 1,Addr 1 - City,Addr 1 - State,Addr 1 - Postcode,Addr 1 - Country,Addr 1 - Phone # 1,Addr 1 - Email,Addr 1 - Contact Name,A.B.N.
Haven Medical Group,,HAV001,Active,1 Health St,Bondi,NSW,2026,Australia,02 9300 0000,anika@havenmedical.example,Dr Anika Rao,71 455 210 883
Tanaka,Kenji,TAN001,Active,,,,,,,kenji@tanakabell.example,,
"""


def _upload(client, h, name, text):
    return client.post(f"{C}/import/preview", headers=h, files={"file": (name, io.BytesIO(text.encode("utf-8")), "text/csv")})


def test_xero_preview_detects_and_maps(client):
    h = auth(signup(client)["tokens"])
    r = _upload(client, h, "Contacts.csv", XERO_CSV)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["source"] == "xero" and p["row_count"] == 6
    m = p["proposed_mapping"]
    assert m["name"] == "*ContactName" and m["abn"] == "TaxNumber" and m["email"] == "EmailAddress" and m["suburb"] == "POCity" and m["acn"] == "CompanyNumber"
    assert len(p["sample"]) == 6 and p["warnings"] == []


def test_xero_commit_creates_dedupes_types_and_contacts(client):
    h = auth(signup(client)["tokens"])
    job = _upload(client, h, "Contacts.csv", XERO_CSV).json()["job_id"]
    r = client.post(f"{C}/import/{job}/commit", headers=h, json={"default_stage": "Active"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["status"] == "committed"
    assert res["created_count"] == 5          # Marlow, Ashfield, Reyes, Northcote, Bad ABN Co
    assert res["skipped_count"] == 1          # in-file duplicate of Marlow (same ABN)
    assert any("Line 7" in e and "ABN" in e for e in res["errors"])  # bad ABN reported, row still imported
    page = client.get(f"{C}/clients", headers=h, params={"size": 50}).json()
    by = {c["name"]: c for c in page["items"]}
    assert by["Marlow Constructions Pty Ltd"]["client_type"] == "Company" and by["Marlow Constructions Pty Ltd"]["abn"] == "48902337115" and by["Marlow Constructions Pty Ltd"]["acn"] == "902337115"
    assert by["Marlow Constructions Pty Ltd"]["legal_name"] == "Marlow Constructions Pty Limited" and by["Marlow Constructions Pty Ltd"]["source"] == "import:xero"
    assert by["Ashfield Family Trust"]["client_type"] == "Trust"
    assert by["Elena Reyes"]["client_type"] == "Individual"
    assert by["Northcote Super Fund"]["client_type"] == "SMSF"
    assert by["Bad ABN Co"]["abn"] is None
    assert all(c["stage"] == "Active" and c["since"] for c in page["items"])
    assert by["Marlow Constructions Pty Ltd"]["primary_contact"]["full_name"] == "Gavin Marlow"
    assert by["Marlow Constructions Pty Ltd"]["primary_contact"]["email"] == "gavin@marlowcon.example"
    # the import is on the practice timeline
    home = client.get(f"{C}/home", headers=h).json()
    assert any(e["kind"] == "import.completed" for e in home["recent"])
    # re-running the same file updates/skips, never duplicates
    job2 = _upload(client, h, "Contacts.csv", XERO_CSV).json()["job_id"]
    res2 = client.post(f"{C}/import/{job2}/commit", headers=h, json={}).json()
    assert res2["created_count"] == 0
    assert client.get(f"{C}/clients", headers=h).json()["total"] == 5


def test_myob_detected_and_committed(client):
    h = auth(signup(client)["tokens"])
    p = _upload(client, h, "Cards.txt", MYOB_CSV).json()
    assert p["source"] == "myob" and p["proposed_mapping"]["name"] == "Co./Last Name" and p["proposed_mapping"]["abn"] == "A.B.N."
    res = client.post(f"{C}/import/{p['job_id']}/commit", headers=h, json={"default_stage": "Lead"}).json()
    assert res["created_count"] == 2
    by = {c["name"]: c for c in client.get(f"{C}/clients", headers=h).json()["items"]}
    assert by["Haven Medical Group"]["abn"] == "71455210883" and by["Haven Medical Group"]["primary_contact"]["full_name"] == "Dr Anika Rao"
    assert by["Tanaka"]["client_type"] == "Individual" and by["Tanaka"]["stage"] == "Lead"


def test_generic_csv_needs_name_mapping(client):
    h = auth(signup(client)["tokens"])
    p = _upload(client, h, "x.csv", "Org,Contact Email\nZeta Pty Ltd,z@zeta.example\n").json()
    assert p["source"] == "csv" and p["proposed_mapping"]["name"] is None and p["warnings"]
    assert client.post(f"{C}/import/{p['job_id']}/commit", headers=h, json={}).status_code == 400
    res = client.post(f"{C}/import/{p['job_id']}/commit", headers=h, json={"mapping": {"name": "Org", "email": "Contact Email"}}).json()
    assert res["created_count"] == 1
    assert client.get(f"{C}/clients", headers=h).json()["items"][0]["email"] == "z@zeta.example"


def test_unreadable_file_400(client):
    h = auth(signup(client)["tokens"])
    r = client.post(f"{C}/import/preview", headers=h, files={"file": ("x.csv", io.BytesIO(b""), "text/csv")})
    assert r.status_code == 400
