from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import events
from app.core.security import utcnow
from app.core.storage import get_storage
from app.models.crm import Client
from app.models.platform import Document
from app.models.tenant import Tenant
from app.modules.documents import schemas as S
from app.modules.documents.models import DocumentIndex, Folder, RetentionPolicy
from app.services.crm_service import client_name_map, member_names

# The folder set a practice actually uses, created per client on demand.
STANDARD_FOLDERS = ["Permanent", "Permanent/Constitution & deeds", "Permanent/Registrations", "Identity & AML", "Tax", "Financials", "Activity statements", "Correspondence", "Agreements", "Payroll", "Lending"]

TEXT_TYPES = ("text/plain", "text/csv", "text/markdown", "application/json", "application/xml", "text/xml")
MAX_INDEX_BYTES = 2 * 1024 * 1024


class DocumentsError(Exception):
    def __init__(self, error: str, message: str | None = None):
        super().__init__(message or error)
        self.error, self.message = error, message or error


# ------------------------------------------------------------------ text extraction
def extract_text(data: bytes, content_type: str, filename: str) -> tuple[str | None, str, int | None]:
    """
    Pull what text we can without a paid OCR service: plain files directly, PDFs through pdf stream
    decoding. Scanned images return nothing and are marked so the UI can say why they are not searchable.
    """
    if len(data) > MAX_INDEX_BYTES:
        data = data[:MAX_INDEX_BYTES]
    ct = (content_type or "").lower()
    if ct.startswith("text/") or ct in TEXT_TYPES:
        try:
            return data.decode("utf-8", errors="ignore").lower()[:200_000], "plain", None
        except Exception:  # noqa: BLE001
            return None, "none", None
    if ct == "application/pdf" or filename.lower().endswith(".pdf"):
        try:
            text, pages = _pdf_text(data)
            if text.strip():
                return text.lower()[:200_000], "pdf", pages
            return None, "ocr", pages          # a PDF with no text layer needs OCR we do not run here
        except Exception:  # noqa: BLE001
            return None, "none", None
    return None, "none", None


def _pdf_text(data: bytes) -> tuple[str, int]:
    """Minimal PDF text extraction: inflate the content streams and read the text-showing operators."""
    import zlib
    pages = len(re.findall(rb"/Type\s*/Page\b", data))
    out: list[str] = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        chunk = m.group(1)
        try:
            chunk = zlib.decompress(chunk)
        except zlib.error:
            pass
        for t in re.findall(rb"\((?:\\.|[^\\()])*\)", chunk):
            s = t[1:-1].replace(rb"\(", b"(").replace(rb"\)", b")").replace(rb"\\", b"\\")
            try:
                out.append(s.decode("utf-8", errors="ignore"))
            except Exception:  # noqa: BLE001
                continue
    return " ".join(out), max(pages, 1)


# ------------------------------------------------------------------ folders
def ensure_standard_folders(db: Session, tenant_id: uuid.UUID, client_id: uuid.UUID | None, actor_mid: uuid.UUID | None) -> int:
    existing = {f.path for f in db.execute(select(Folder).where(Folder.client_id == client_id)).scalars()}
    by_path: dict[str, Folder] = {}
    created = 0
    for i, path in enumerate(STANDARD_FOLDERS):
        if path in existing:
            continue
        parent_path, _, name = path.rpartition("/")
        parent = by_path.get(parent_path) or (db.execute(select(Folder).where(Folder.client_id == client_id, Folder.path == parent_path)).scalars().first() if parent_path else None)
        f = Folder(tenant_id=tenant_id, client_id=client_id, parent_id=parent.id if parent else None, name=name, path=path, kind="standard", order=i, created_by_membership_id=actor_mid)
        db.add(f)
        db.flush()
        by_path[path] = f
        created += 1
    return created


def create_folder(db: Session, tenant_id: uuid.UUID, body: S.FolderIn, actor_mid: uuid.UUID) -> Folder:
    parent = db.get(Folder, body.parent_id) if body.parent_id else None
    if body.parent_id and parent is None:
        raise DocumentsError("folder_not_found")
    client_id = parent.client_id if parent else body.client_id
    path = f"{parent.path}/{body.name}" if parent else body.name
    if db.execute(select(Folder).where(Folder.client_id == client_id, Folder.path == path)).scalars().first():
        raise DocumentsError("folder_exists", f"“{path}” already exists")
    f = Folder(tenant_id=tenant_id, client_id=client_id, parent_id=parent.id if parent else None, name=body.name, path=path, created_by_membership_id=actor_mid)
    db.add(f)
    db.flush()
    return f


def folder_tree(db: Session, client_id: uuid.UUID | None) -> list[S.FolderOut]:
    folders = db.execute(select(Folder).where(Folder.client_id == client_id).order_by(Folder.order, Folder.path)).scalars().all()
    counts = dict(db.execute(select(DocumentIndex.folder_id, func.count()).where(DocumentIndex.folder_id.in_([f.id for f in folders])).group_by(DocumentIndex.folder_id)).all()) if folders else {}
    return [S.FolderOut(id=f.id, client_id=f.client_id, parent_id=f.parent_id, name=f.name, path=f.path, kind=f.kind, depth=f.path.count("/"), document_count=int(counts.get(f.id, 0))) for f in folders]


# ------------------------------------------------------------------ indexing
def index_document(db: Session, tenant: Tenant, doc: Document, *, folder_id: uuid.UUID | None = None, tags: list[str] | None = None, read_bytes: bool = True) -> DocumentIndex:
    row = db.execute(select(DocumentIndex).where(DocumentIndex.document_id == doc.id)).scalars().first()
    text, source, pages = (None, "none", None)
    if read_bytes:
        try:
            text, source, pages = extract_text(get_storage().get(doc.storage_key), doc.content_type, doc.filename)
        except Exception:  # noqa: BLE001 — a missing blob must not break the index
            text, source, pages = None, "none", None
    policy, retain_until = _policy_for(db, doc)
    if row is None:
        row = DocumentIndex(tenant_id=tenant.id, document_id=doc.id, folder_id=folder_id, tags=tags or [], text=text, text_source=source, pages=pages,
                            policy_id=policy.id if policy else None, retain_until=retain_until, indexed_at=utcnow())
        db.add(row)
    else:
        if folder_id is not None:
            row.folder_id = folder_id
        if tags is not None:
            row.tags = tags
        if read_bytes:
            row.text, row.text_source, row.pages = text, source, pages
        row.policy_id, row.retain_until, row.indexed_at = (policy.id if policy else None), retain_until, utcnow()
    db.flush()
    return row


def _policy_for(db: Session, doc: Document) -> tuple[RetentionPolicy | None, date | None]:
    policies = db.execute(select(RetentionPolicy).where(RetentionPolicy.is_active.is_(True))).scalars().all()
    match = next((p for p in policies if p.kinds and doc.kind in p.kinds), None) or next((p for p in policies if not p.kinds), None)
    if match is None:
        return None, None
    start = doc.created_at.date()
    return match, date(start.year + match.years, start.month, min(start.day, 28))


def reindex_all(db: Session, tenant: Tenant) -> int:
    n = 0
    for doc in db.execute(select(Document).where(Document.deleted_at.is_(None))).scalars():
        index_document(db, tenant, doc)
        n += 1
    return n


# ------------------------------------------------------------------ search
def search(db: Session, tenant: Tenant, q: S.SearchIn) -> list[S.DocumentRow]:
    stmt = select(Document, DocumentIndex).join(DocumentIndex, DocumentIndex.document_id == Document.id, isouter=True).where(Document.deleted_at.is_(None))
    if q.client_id:
        stmt = stmt.where(Document.client_id == q.client_id)
    if q.kind:
        stmt = stmt.where(Document.kind == q.kind)
    if q.module_key:
        stmt = stmt.where(Document.module_key == q.module_key)
    if q.folder_id:
        stmt = stmt.where(DocumentIndex.folder_id == q.folder_id)
    if q.visible_to_client is not None:
        stmt = stmt.where(Document.visible_to_client.is_(q.visible_to_client))
    if q.retention_hold is not None:
        stmt = stmt.where(Document.retention_hold.is_(q.retention_hold))
    if q.q:
        needle = f"%{q.q.lower()}%"
        stmt = stmt.where(or_(func.lower(Document.filename).like(needle), func.lower(Document.description).like(needle), DocumentIndex.text.like(needle)))
    rows = db.execute(stmt.order_by(Document.created_at.desc()).limit(q.limit)).all()
    names = member_names(db, {d.uploaded_by_membership_id for d, _ in rows})
    clients = client_name_map(db, {d.client_id for d, _ in rows})
    folders = {f.id: f.path for f in db.execute(select(Folder)).scalars()} if rows else {}
    out: list[S.DocumentRow] = []
    for d, idx in rows:
        snippet = None
        if q.q and idx is not None and idx.text:
            pos = idx.text.find(q.q.lower())
            if pos >= 0:
                snippet = ("…" if pos > 40 else "") + idx.text[max(0, pos - 40): pos + 120].strip() + "…"
        out.append(S.DocumentRow(id=d.id, client_id=d.client_id, client_name=clients.get(d.client_id) if d.client_id else None, module_key=d.module_key, kind=d.kind, filename=d.filename,
                                 content_type=d.content_type, size_bytes=d.size_bytes, sha256=d.sha256, description=d.description, uploaded_by_name=names.get(d.uploaded_by_membership_id) if d.uploaded_by_membership_id else "Client",
                                 scan_status=d.scan_status, retention_hold=d.retention_hold, visible_to_client=d.visible_to_client, created_at=d.created_at,
                                 folder_id=idx.folder_id if idx else None, folder_path=folders.get(idx.folder_id) if idx and idx.folder_id else None, tags=(idx.tags if idx else []) or [],
                                 text_source=idx.text_source if idx else "none", pages=idx.pages if idx else None, retain_until=idx.retain_until if idx else None, snippet=snippet))
    return out


def file_document(db: Session, tenant: Tenant, doc: Document, body: S.FileIn, actor_mid: uuid.UUID, actor_label: str) -> DocumentIndex:
    folder = db.get(Folder, body.folder_id) if body.folder_id else None
    if body.folder_id and folder is None:
        raise DocumentsError("folder_not_found")
    if folder and folder.client_id and doc.client_id and folder.client_id != doc.client_id:
        raise DocumentsError("wrong_client", "That folder belongs to a different client")
    row = index_document(db, tenant, doc, folder_id=folder.id if folder else None, tags=body.tags, read_bytes=body.reindex)
    if body.kind:
        doc.kind = body.kind[:40]
    if doc.client_id:
        events.emit(db, tenant_id=tenant.id, client_id=doc.client_id, module_key="documents", kind="document.filed", summary=f"{doc.filename} filed to {folder.path if folder else 'no folder'}",
                    detail={"tags": row.tags}, actor_membership_id=actor_mid, actor_label=actor_label, ref_type="document", ref_id=doc.id)
    return row


# ------------------------------------------------------------------ retention
def retention_review(db: Session, days_ahead: int = 90) -> list[S.RetentionRow]:
    cutoff = date.today() + timedelta(days=days_ahead)
    rows = db.execute(select(DocumentIndex, Document).join(Document, Document.id == DocumentIndex.document_id).where(DocumentIndex.retain_until.is_not(None), DocumentIndex.retain_until <= cutoff, Document.deleted_at.is_(None))).all()
    policies = {p.id: p for p in db.execute(select(RetentionPolicy)).scalars()}
    clients = client_name_map(db, {d.client_id for _, d in rows})
    today = date.today()
    return sorted([S.RetentionRow(document_id=d.id, filename=d.filename, client_id=d.client_id, client_name=clients.get(d.client_id) if d.client_id else None, kind=d.kind,
                                  policy_name=policies[idx.policy_id].name if idx.policy_id in policies else None, action=policies[idx.policy_id].action if idx.policy_id in policies else "review",
                                  retain_until=idx.retain_until, due=idx.retain_until <= today, retention_hold=d.retention_hold, created_at=d.created_at) for idx, d in rows], key=lambda r: r.retain_until)


def apply_policies(db: Session, tenant: Tenant) -> dict[str, int]:
    """Re-stamp retain_until from the current policies, and place holds where a policy says hold."""
    stats = {"indexed": 0, "held": 0}
    for doc in db.execute(select(Document).where(Document.deleted_at.is_(None))).scalars():
        row = index_document(db, tenant, doc, read_bytes=False)
        stats["indexed"] += 1
        if row.policy_id:
            p = db.get(RetentionPolicy, row.policy_id)
            if p and p.action == "hold" and not doc.retention_hold:
                doc.retention_hold, doc.retention_until = True, row.retain_until
                stats["held"] += 1
    db.flush()
    return stats


# ------------------------------------------------------------------ overview
def overview(db: Session) -> S.OverviewOut:
    docs = db.execute(select(Document).where(Document.deleted_at.is_(None))).scalars().all()
    idx = {i.document_id: i for i in db.execute(select(DocumentIndex)).scalars()}
    by_module: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for d in docs:
        by_module[d.module_key] = by_module.get(d.module_key, 0) + 1
        by_kind[d.kind] = by_kind.get(d.kind, 0) + 1
    unfiled = sum(1 for d in docs if d.id not in idx or idx[d.id].folder_id is None)
    searchable = sum(1 for d in docs if d.id in idx and idx[d.id].text_source in ("plain", "pdf"))
    needs_ocr = sum(1 for d in docs if d.id in idx and idx[d.id].text_source == "ocr")
    today = date.today()
    return S.OverviewOut(documents=len(docs), bytes_total=sum(d.size_bytes for d in docs), unfiled=unfiled, searchable=searchable, needs_ocr=needs_ocr,
                         on_hold=sum(1 for d in docs if d.retention_hold), shared_with_clients=sum(1 for d in docs if d.visible_to_client),
                         retention_due=sum(1 for i in idx.values() if i.retain_until and i.retain_until <= today),
                         by_module=dict(sorted(by_module.items(), key=lambda kv: -kv[1])), by_kind=dict(sorted(by_kind.items(), key=lambda kv: -kv[1])[:10]),
                         policies=db.execute(select(func.count()).select_from(RetentionPolicy).where(RetentionPolicy.is_active.is_(True))).scalar_one())


DEFAULT_POLICIES = [
    {"name": "AML/CTF records", "kinds": ["identity", "verification", "screening"], "years": 7, "action": "hold", "reference": "AML/CTF Act s.107 — 7 years from the end of the relationship"},
    {"name": "Signed agreements", "kinds": ["agreement"], "years": 7, "action": "hold", "reference": "Executed documents — 7 years"},
    {"name": "Tax and financial records", "kinds": ["tax", "financial", "workpaper", "bank", "payroll"], "years": 5, "action": "review", "reference": "TAA 1953 sch 1 s.382-5 — 5 years"},
    {"name": "General correspondence", "kinds": [], "years": 7, "action": "review", "reference": "Practice policy"},
]


def seed_policies(db: Session, tenant_id: uuid.UUID, actor_mid: uuid.UUID | None) -> int:
    if db.execute(select(func.count()).select_from(RetentionPolicy)).scalar_one():
        return 0
    for spec in DEFAULT_POLICIES:
        db.add(RetentionPolicy(tenant_id=tenant_id, trigger="created", created_by_membership_id=actor_mid, **spec))
    db.flush()
    return len(DEFAULT_POLICIES)
