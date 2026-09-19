"""
Client-list import: Xero contacts export, MYOB card file, or any CSV with a header row.

Flow: upload → detect source → parse (capped) → propose a column mapping → preview
→ commit with the (possibly edited) mapping. Commit de-duplicates on ABN, then on
normalised name, and either updates the existing client (filling blanks only) or creates.
This is the first screen after signup, so it has to be forgiving: bad rows are reported,
never fatal.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas_crm as S
from app.core import events
from app.core.security import utcnow
from app.models.crm import Client, Contact, ImportJob
from app.services.crm_service import normalise_name

MAX_ROWS = 5000

# Canonical fields the importer can fill, and header aliases seen in the wild.
FIELDS: dict[str, list[str]] = {
    "name":        ["*ContactName", "ContactName", "Co./Last Name", "Company", "Company Name", "Name", "Client", "Client Name", "Organisation", "Business Name"],
    "legal_name":  ["LegalName", "Legal Name", "Trading Name"],
    "first_name":  ["FirstName", "First Name", "Contact First Name", "Given Name"],
    "last_name":   ["LastName", "Last Name", "Surname", "Contact Last Name"],
    "email":       ["EmailAddress", "Email", "E-mail", "Addr 1 - Email", "Email Address"],
    "phone":       ["PhoneNumber", "Phone", "Addr 1 - Phone No. 1", "Addr 1 - Phone # 1", "Phone Number", "Telephone"],
    "mobile":      ["MobileNumber", "Mobile", "Addr 1 - Phone No. 2", "Addr 1 - Phone # 2", "Mobile Number"],
    "abn":         ["TaxNumber", "ABN", "A.B.N.", "A.B.N", "Tax Number", "ABN Number"],
    "acn":         ["CompanyNumber", "ACN", "A.C.N.", "Company Number"],
    "website":     ["Website", "Addr 1 - WWW", "Web", "URL"],
    "address_line1": ["POAddressLine1", "Addr 1 - Line 1", "Address", "Address 1", "Street", "Address Line 1"],
    "address_line2": ["POAddressLine2", "Addr 1 - Line 2", "Address 2", "Address Line 2"],
    "suburb":      ["POCity", "Addr 1 - City", "City", "Suburb", "Town"],
    "state":       ["PORegion", "Addr 1 - State", "State", "Region"],
    "postcode":    ["POPostalCode", "Addr 1 - Postcode", "Postcode", "Postal Code", "Zip"],
    "country":     ["POCountry", "Addr 1 - Country", "Country"],
    "external_ref": ["ContactID", "Card ID", "AccountNumber", "Account Number", "Client Code", "ID"],
    "contact_name": ["Addr 1 - Contact Name", "POAttentionTo", "Contact", "Contact Name", "Attention"],
}

XERO_SIGNATURE = {"*ContactName", "EmailAddress", "POAddressLine1"}
MYOB_SIGNATURE = {"Co./Last Name", "Card ID"}


def detect_source(columns: list[str]) -> str:
    cols = set(columns)
    if XERO_SIGNATURE & cols and ("*ContactName" in cols or "ContactName" in cols):
        return "xero"
    if MYOB_SIGNATURE & cols:
        return "myob"
    return "csv"


def propose_mapping(columns: list[str]) -> dict[str, str | None]:
    lower = {c.strip().lower(): c for c in columns}
    mapping: dict[str, str | None] = {}
    for field, aliases in FIELDS.items():
        hit = None
        for a in aliases:
            if a.strip().lower() in lower:
                hit = lower[a.strip().lower()]
                break
        mapping[field] = hit
    return mapping


def parse_csv(data: bytes) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Could not decode file as text")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    columns = [c.strip() for c in (reader.fieldnames or []) if c is not None]
    rows: list[dict[str, Any]] = []
    for i, raw in enumerate(reader):
        if i >= MAX_ROWS:
            warnings.append(f"File has more than {MAX_ROWS} rows; only the first {MAX_ROWS} were read.")
            break
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k is not None}
        if any(row.values()):
            rows.append(row)
    if not columns:
        raise ValueError("No header row found")
    return columns, rows, warnings


_digits = lambda s: "".join(ch for ch in (s or "") if ch.isdigit())  # noqa: E731


def infer_type(name: str, abn: str | None, first: str | None, last: str | None) -> str:
    n = name.lower()
    if re.search(r"\b(super|smsf|superannuation)\b", n):
        return "SMSF"
    if re.search(r"\b(trust|atf|as trustee)\b", n):
        return "Trust"
    if re.search(r"\b(pty|ltd|limited|inc|co\.?|corporation|holdings|group|enterprises|services|solutions|consulting)\b", n) or re.search(r"\b(pty|ltd)\b", n):
        return "Company"
    if re.search(r"\bpartners(hip)?\b|&|\band\b", n) and not first:
        return "Partnership"
    if (first or last) and len(n.split()) <= 3:
        return "Individual"
    return "Company" if abn else "Individual"


def start_job(db: Session, tenant_id: uuid.UUID, filename: str, data: bytes, actor_mid: uuid.UUID | None) -> tuple[ImportJob, S.ImportPreview]:
    columns, rows, warnings = parse_csv(data)
    source = detect_source(columns)
    mapping = propose_mapping(columns)
    if not mapping.get("name"):
        warnings.append("No name column recognised — choose one in the mapping before committing.")
    job = ImportJob(tenant_id=tenant_id, source=source, filename=filename[:255], status="preview", columns=columns, mapping=mapping, rows=rows,
                    row_count=len(rows), created_by_membership_id=actor_mid)
    db.add(job)
    db.flush()
    return job, S.ImportPreview(job_id=job.id, source=source, filename=job.filename, columns=columns, proposed_mapping=mapping, row_count=len(rows),
                                sample=rows[:8], warnings=warnings)


def _val(row: dict[str, Any], mapping: dict[str, str | None], field: str) -> str | None:
    col = mapping.get(field)
    if not col:
        return None
    v = (row.get(col) or "").strip()
    return v or None


def commit_job(db: Session, job: ImportJob, body: S.ImportCommitIn, actor_mid: uuid.UUID | None, actor_label: str) -> S.ImportResult:
    if job.status == "committed":
        return S.ImportResult(job_id=job.id, status=job.status, row_count=job.row_count, created_count=job.created_count, updated_count=job.updated_count,
                              skipped_count=job.skipped_count, errors=job.errors)
    mapping = {**job.mapping, **{k: v for k, v in body.mapping.items()}}
    if not mapping.get("name"):
        raise ValueError("A name column is required")
    job.mapping = mapping

    existing_by_abn: dict[str, Client] = {}
    existing_by_name: dict[str, Client] = {}
    for c in db.execute(select(Client).where(Client.archived_at.is_(None))).scalars():
        if c.abn:
            existing_by_abn.setdefault(c.abn, c)
        existing_by_name.setdefault(c.name_normalised, c)

    created = updated = skipped = 0
    errors: list[str] = []
    seen_in_file: set[str] = set()

    for i, row in enumerate(job.rows, start=2):  # header is line 1
        try:
            name = _val(row, mapping, "name")
            first, last = _val(row, mapping, "first_name"), _val(row, mapping, "last_name")
            if not name:
                if first or last:
                    name = f"{first or ''} {last or ''}".strip()
                else:
                    skipped += 1
                    errors.append(f"Line {i}: no name — skipped")
                    continue
            abn = _digits(_val(row, mapping, "abn")) or None
            if abn and len(abn) != 11:
                errors.append(f"Line {i}: ABN '{abn}' is not 11 digits — imported without ABN")
                abn = None
            acn = _digits(_val(row, mapping, "acn")) or None
            if acn and len(acn) != 9:
                acn = None
            nn = normalise_name(name)
            dedupe_key = abn or f"name:{nn}"
            if dedupe_key in seen_in_file:
                skipped += 1
                errors.append(f"Line {i}: duplicate of an earlier row — skipped")
                continue
            seen_in_file.add(dedupe_key)

            fields = {
                "legal_name": _val(row, mapping, "legal_name"), "email": _val(row, mapping, "email"),
                "phone": _val(row, mapping, "phone") or _val(row, mapping, "mobile"), "website": _val(row, mapping, "website"),
                "address_line1": _val(row, mapping, "address_line1"), "address_line2": _val(row, mapping, "address_line2"),
                "suburb": _val(row, mapping, "suburb"), "state": (_val(row, mapping, "state") or "")[:10] or None,
                "postcode": (_val(row, mapping, "postcode") or "")[:10] or None, "external_ref": _val(row, mapping, "external_ref"),
            }
            country = (_val(row, mapping, "country") or "AU")
            country = {"australia": "AU", "au": "AU", "new zealand": "NZ", "nz": "NZ"}.get(country.lower(), country[:2].upper())

            target = existing_by_abn.get(abn) if abn else None
            if target is None:
                target = existing_by_name.get(nn)
            if target is not None:
                if not body.update_existing:
                    skipped += 1
                    continue
                changed = []
                for k, v in fields.items():
                    if v and not getattr(target, k):
                        setattr(target, k, v)
                        changed.append(k)
                if abn and not target.abn:
                    target.abn, _ = abn, changed.append("abn")
                if acn and not target.acn:
                    target.acn, _ = acn, changed.append("acn")
                if changed:
                    updated += 1
                else:
                    skipped += 1
                client = target
            else:
                client = Client(tenant_id=job.tenant_id, name=name, name_normalised=nn, client_type=infer_type(name, abn, first, last), abn=abn, acn=acn,
                                stage=body.default_stage, since=utcnow().date() if body.default_stage == "Active" else None, country=country,
                                source=f"import:{job.source}", tags=["Imported"], **fields)
                db.add(client)
                db.flush()
                existing_by_name[nn] = client
                if abn:
                    existing_by_abn[abn] = client
                created += 1

            # Primary contact from the row's person fields, if there is one and the client has none.
            cname = _val(row, mapping, "contact_name")
            if (first or last or cname) and not db.execute(select(Contact.id).where(Contact.client_id == client.id).limit(1)).first():
                if not (first or last) and cname:
                    parts = cname.split(None, 1)
                    first, last = parts[0], (parts[1] if len(parts) > 1 else None)
                db.add(Contact(tenant_id=job.tenant_id, client_id=client.id, first_name=first or name, last_name=last, email=fields["email"], phone=fields["phone"],
                               role="Owner" if client.client_type == "Individual" else "Primary contact", is_primary=True))
        except Exception as e:  # a bad row must never abort the import
            skipped += 1
            errors.append(f"Line {i}: {type(e).__name__}: {e}")

    job.status, job.committed_at = "committed", utcnow()
    job.created_count, job.updated_count, job.skipped_count, job.errors = created, updated, skipped, errors[:200]
    job.rows = []  # do not keep the raw file around after commit
    events.emit(db, tenant_id=job.tenant_id, module_key="crm", kind="import.completed", summary=f"Imported {created} clients from {job.source.upper()} ({updated} updated, {skipped} skipped)",
                detail={"source": job.source, "filename": job.filename, "created": created, "updated": updated, "skipped": skipped},
                actor_membership_id=actor_mid, actor_label=actor_label, ref_type="import", ref_id=job.id)
    db.flush()
    return S.ImportResult(job_id=job.id, status=job.status, row_count=job.row_count, created_count=created, updated_count=updated, skipped_count=skipped, errors=job.errors)
