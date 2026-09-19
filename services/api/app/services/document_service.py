"""
One way to put bytes on a client record. Every module that receives files (Start intake, Requests,
Client portal uploads, staff uploads) goes through `store()` so scanning, hashing, storage keys and
the timeline entry are identical regardless of who uploaded.
"""
from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.orm import Session

from app.core import audit, av, events
from app.core.config import settings
from app.core.storage import get_storage, make_key
from app.models.platform import Document


class UploadRefused(Exception):
    def __init__(self, error: str, **extra):
        super().__init__(error)
        self.error, self.extra = error, extra


def store(db: Session, *, tenant_id: uuid.UUID, data: bytes, filename: str, content_type: str | None, client_id: uuid.UUID | None, module_key: str, kind: str,
          uploaded_by_membership_id: uuid.UUID | None, actor_label: str, description: str | None = None) -> Document:
    if not data:
        raise UploadRefused("empty_file")
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise UploadRefused("file_too_large", max_mb=settings.MAX_UPLOAD_MB)
    scan_status, signature = av.scan(data)
    if scan_status == av.INFECTED:
        audit.record(db, action="document.rejected_infected", actor_user_id=None, tenant_id=tenant_id, target_type="upload", detail={"filename": filename, "signature": signature, "via": module_key})
        raise UploadRefused("malware_detected", signature=signature)
    if scan_status == av.UNAVAILABLE and settings.is_production:
        raise UploadRefused("scan_unavailable")
    doc_id = uuid.uuid4()
    key = make_key(tenant_id, doc_id, filename or "file")
    ct = (content_type or "application/octet-stream")[:120]
    get_storage().put(key, data, ct)
    d = Document(id=doc_id, tenant_id=tenant_id, client_id=client_id, module_key=module_key, kind=kind[:40], filename=(filename or "file")[:255], content_type=ct, size_bytes=len(data),
                 storage_key=key, sha256=hashlib.sha256(data).hexdigest(), description=description, uploaded_by_membership_id=uploaded_by_membership_id, scan_status=scan_status)
    db.add(d)
    db.flush()
    if client_id:
        events.emit(db, tenant_id=tenant_id, client_id=client_id, module_key=module_key, kind="document.uploaded", summary=f"Uploaded {d.filename} ({kind})",
                    detail={"size_bytes": d.size_bytes, "scan": scan_status}, actor_membership_id=uploaded_by_membership_id, actor_label=actor_label, ref_type="document", ref_id=d.id)
    return d
