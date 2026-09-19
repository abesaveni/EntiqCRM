"""EnTIQ Documents — module 07. The base plan always stores files; this module adds filing, search and retention."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.models.platform import Document
from app.modules.documents import schemas as S
from app.modules.documents import service as svc
from app.modules.documents.models import DocumentIndex, Folder, RetentionPolicy

router = APIRouter(prefix="/documents-module", tags=["documents"])
view = require_module("documents")
edit = require_module("documents", write=True)


def _doc(db: Session, document_id: uuid.UUID) -> Document:
    d = db.get(Document, document_id)
    if d is None or d.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "document_not_found"})
    return d


def _err(e: svc.DocumentsError) -> HTTPException:
    return HTTPException({"folder_not_found": 404, "folder_exists": 409, "wrong_client": 400}.get(e.error, 400), detail={"error": e.error, "message": e.message})


@router.get("/overview", response_model=S.OverviewOut)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.overview(db)


# ------------------------------------------------------------------ folders
@router.get("/folders", response_model=list[S.FolderOut])
def folders(client_id: uuid.UUID | None = None, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.folder_tree(db, client_id)


@router.post("/folders", response_model=S.FolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(body: S.FolderIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("documents:upload")), db: Session = Depends(get_db)):
    try:
        f = svc.create_folder(db, p.tenant.id, body, p.membership.id)
    except svc.DocumentsError as e:
        raise _err(e)
    db.commit()
    return S.FolderOut(id=f.id, client_id=f.client_id, parent_id=f.parent_id, name=f.name, path=f.path, kind=f.kind, depth=f.path.count("/"), document_count=0)


@router.post("/folders/standard", response_model=list[S.FolderOut])
def standard_folders(client_id: uuid.UUID | None = None, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("documents:upload")), db: Session = Depends(get_db)):
    """Create the practice's standard folder set for a client (or practice-wide when no client is given)."""
    svc.ensure_standard_folders(db, p.tenant.id, client_id, p.membership.id)
    db.commit()
    return svc.folder_tree(db, client_id)


# ------------------------------------------------------------------ search and filing
@router.post("/search", response_model=list[S.DocumentRow])
def search(body: S.SearchIn, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.search(db, p.tenant, body)


@router.post("/{document_id}/file", response_model=S.DocumentRow)
def file_document(document_id: uuid.UUID, body: S.FileIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("documents:upload")), db: Session = Depends(get_db)):
    d = _doc(db, document_id)
    try:
        svc.file_document(db, p.tenant, d, body, p.membership.id, p.user.full_name)
    except svc.DocumentsError as e:
        raise _err(e)
    db.commit()
    rows = svc.search(db, p.tenant, S.SearchIn(limit=500, client_id=d.client_id))
    return next(r for r in rows if r.id == d.id)


@router.post("/reindex")
def reindex(p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("documents:retain")), db: Session = Depends(get_db)):
    n = svc.reindex_all(db, p.tenant)
    db.commit()
    return {"indexed": n}


# ------------------------------------------------------------------ retention
@router.get("/policies", response_model=list[S.PolicyOut])
def policies(p: Principal = Depends(view), db: Session = Depends(get_db)):
    rows = db.execute(select(RetentionPolicy).order_by(RetentionPolicy.name)).scalars().all()
    counts = {}
    for r in rows:
        counts[r.id] = db.execute(select(__import__("sqlalchemy").func.count()).select_from(DocumentIndex).where(DocumentIndex.policy_id == r.id)).scalar_one()
    return [S.PolicyOut(id=r.id, name=r.name, kinds=r.kinds or [], years=r.years, trigger=r.trigger, action=r.action, reference=r.reference, is_active=r.is_active, documents=int(counts.get(r.id, 0))) for r in rows]


@router.post("/policies", response_model=S.PolicyOut, status_code=status.HTTP_201_CREATED)
def create_policy(body: S.PolicyIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("documents:retain")), db: Session = Depends(get_db)):
    r = RetentionPolicy(tenant_id=p.tenant.id, created_by_membership_id=p.membership.id, **body.model_dump())
    db.add(r)
    db.commit()
    return S.PolicyOut(id=r.id, name=r.name, kinds=r.kinds or [], years=r.years, trigger=r.trigger, action=r.action, reference=r.reference, is_active=r.is_active, documents=0)


@router.post("/policies/defaults", response_model=list[S.PolicyOut])
def seed_policies(p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("documents:retain")), db: Session = Depends(get_db)):
    svc.seed_policies(db, p.tenant.id, p.membership.id)
    db.commit()
    return policies(p, db)


@router.post("/policies/apply")
def apply_policies(p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("documents:retain")), db: Session = Depends(get_db)):
    stats = svc.apply_policies(db, p.tenant)
    db.commit()
    return stats


@router.get("/retention", response_model=list[S.RetentionRow])
def retention(days: int = Query(90, ge=0, le=3650), p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.retention_review(db, days)
