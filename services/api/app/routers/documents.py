"""
Documents — the platform file service. Base-plan attachments on client records live here;
the Documents module (07) layers folders, OCR and storage tiers on the same table.
"""
from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas_platform as S
from app.core import audit, av, events
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission, require_role
from app.core.security import utcnow
from app.core.storage import get_storage, make_key
from app.models.crm import Client
from app.models.platform import Document
from app.services.crm_service import member_names

router = APIRouter(prefix="/documents", tags=["documents"])
view = require_module("crm")
edit = require_module("crm", write=True)


def _out(d: Document, names: dict) -> S.DocumentOut:
    return S.DocumentOut(id=d.id, client_id=d.client_id, module_key=d.module_key, kind=d.kind, filename=d.filename, content_type=d.content_type, size_bytes=d.size_bytes,
                         sha256=d.sha256, description=d.description, uploaded_by_name=names.get(d.uploaded_by_membership_id) if d.uploaded_by_membership_id else None,
                         scan_status=d.scan_status, retention_hold=d.retention_hold, retention_until=d.retention_until, created_at=d.created_at)


@router.get("", response_model=list[S.DocumentOut])
def list_documents(client_id: uuid.UUID | None = None, kind: str | None = None, limit: int = Query(100, ge=1, le=500), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Document).where(Document.deleted_at.is_(None))
    if client_id:
        stmt = stmt.where(Document.client_id == client_id)
    if kind:
        stmt = stmt.where(Document.kind == kind)
    rows = db.execute(stmt.order_by(Document.created_at.desc()).limit(limit)).scalars().all()
    return [_out(d, member_names(db, {d.uploaded_by_membership_id for d in rows})) for d in rows]


@router.post("", response_model=S.DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile = File(...), client_id: uuid.UUID | None = Form(None), kind: str = Form("general"), description: str | None = Form(None),
                 p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "empty_file"})
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail={"error": "file_too_large", "max_mb": settings.MAX_UPLOAD_MB})
    if client_id and db.get(Client, client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "client_not_found"})

    scan_status, signature = av.scan(data)
    if scan_status == av.INFECTED:
        audit.record(db, action="document.rejected_infected", actor_user_id=p.user.id, tenant_id=p.tenant.id, target_type="upload", detail={"filename": file.filename, "signature": signature})
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"error": "malware_detected", "signature": signature})
    if scan_status == av.UNAVAILABLE and settings.is_production:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error": "scan_unavailable", "message": "Uploads are refused until the anti-virus scanner is reachable."})

    doc_id = uuid.uuid4()
    key = make_key(p.tenant.id, doc_id, file.filename or "file")
    get_storage().put(key, data, file.content_type or "application/octet-stream")
    d = Document(id=doc_id, tenant_id=p.tenant.id, client_id=client_id, module_key="crm", kind=kind[:40], filename=(file.filename or "file")[:255],
                 content_type=(file.content_type or "application/octet-stream")[:120], size_bytes=len(data), storage_key=key, sha256=hashlib.sha256(data).hexdigest(),
                 description=(description or None), uploaded_by_membership_id=p.membership.id, scan_status=scan_status)
    db.add(d)
    db.flush()
    if client_id:
        events.emit(db, tenant_id=p.tenant.id, client_id=client_id, module_key="crm", kind="document.uploaded", summary=f"Uploaded {d.filename} ({kind})",
                    detail={"size_bytes": d.size_bytes, "scan": scan_status}, actor_membership_id=p.membership.id, actor_label=p.user.full_name, ref_type="document", ref_id=d.id)
    db.commit()
    return _out(d, {p.membership.id: p.user.full_name})


@router.get("/{document_id}/download")
def download(document_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if d is None or d.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    data = get_storage().get(d.storage_key)
    safe = d.filename.replace('"', "")
    return Response(content=data, media_type=d.content_type, headers={"Content-Disposition": f'attachment; filename="{safe}"', "X-Content-SHA256": d.sha256, "Cache-Control": "private, no-store"})


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete(document_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("crm:edit")), db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if d is None or d.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if d.retention_hold:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"error": "retention_hold", "message": "This document is under a retention hold and cannot be deleted."})
    d.deleted_at = utcnow()  # bytes stay in storage; purge is a separate, audited job
    audit.record(db, action="document.deleted", actor_user_id=p.user.id, tenant_id=p.tenant.id, target_type="document", target_id=str(d.id), detail={"filename": d.filename})
    if d.client_id:
        events.emit(db, tenant_id=p.tenant.id, client_id=d.client_id, module_key="crm", kind="document.deleted", summary=f"Removed {d.filename}", actor_membership_id=p.membership.id, actor_label=p.user.full_name, ref_type="document", ref_id=d.id)
    db.commit()


@router.post("/{document_id}/hold", response_model=S.DocumentOut)
def set_hold(document_id: uuid.UUID, body: S.HoldIn, p: Principal = Depends(edit), db: Session = Depends(get_db)):
    """Anyone with edit rights may PLACE a hold; only owners/admins may LIFT one."""
    d = db.get(Document, document_id)
    if d is None or d.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not body.hold and p.role not in ("owner", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "hold_release_requires_admin"})
    d.retention_hold, d.retention_until = body.hold, body.until
    audit.record(db, action="document.hold_set" if body.hold else "document.hold_released", actor_user_id=p.user.id, tenant_id=p.tenant.id, target_type="document", target_id=str(d.id), detail={"until": str(body.until) if body.until else None, "reason": body.reason})
    db.commit()
    return _out(d, member_names(db, {d.uploaded_by_membership_id}))
