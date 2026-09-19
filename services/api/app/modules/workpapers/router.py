"""EnTIQ Workpapers — module 08."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.modules.workpapers import schemas as S
from app.modules.workpapers import service as svc
from app.modules.workpapers.models import LedgerConnection, Workpaper, WorkpaperIssue, WorkpaperItem
from app.services.crm_service import client_name_map, member_names

router = APIRouter(prefix="/workpapers", tags=["workpapers"])
view = require_module("workpapers")
edit = require_module("workpapers", write=True)


def _pack(db: Session, pack_id: uuid.UUID) -> Workpaper:
    p = db.get(Workpaper, pack_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "workpaper_not_found"})
    return p


def _err(e: svc.WorkpaperError) -> HTTPException:
    return HTTPException({"client_not_found": 404, "document_not_found": 404, "locked": 409, "already_signed_off": 409, "already_closed": 409, "wrong_state": 409, "lodged": 409, "blocking_issues": 409, "open_queries": 409, "not_prepared": 400, "not_signed_off": 409, "ledger_unavailable": 503}.get(e.error, 400),
                         detail={"error": e.error, "message": e.message})


@router.get("/overview", response_model=S.OverviewOut)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.overview(db)


@router.get("/templates")
def templates(p: Principal = Depends(view)):
    return {k: [{"section": s, "key": key, "label": label} for s, key, label in v] for k, v in svc.TEMPLATES.items()}


@router.get("/packs", response_model=list[S.PackOut])
def list_packs(status_: str | None = Query(None, alias="status"), client_id: uuid.UUID | None = None, mine: bool = False, open_only: bool = Query(False, alias="open"), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Workpaper)
    if status_:
        stmt = stmt.where(Workpaper.status == status_)
    if open_only:
        stmt = stmt.where(Workpaper.status.in_(["draft", "in_progress", "in_review"]))
    if client_id:
        stmt = stmt.where(Workpaper.client_id == client_id)
    if mine:
        stmt = stmt.where((Workpaper.preparer_membership_id == p.membership.id) | (Workpaper.reviewer_membership_id == p.membership.id))
    rows = db.execute(stmt.order_by(Workpaper.updated_at.desc())).scalars().all()
    names = member_names(db, {x.preparer_membership_id for x in rows} | {x.reviewer_membership_id for x in rows} | {x.signed_off_by_membership_id for x in rows})
    cn = client_name_map(db, {x.client_id for x in rows})
    return [svc.pack_out(db, x, names, cn) for x in rows]


@router.post("/packs", response_model=S.PackDetail, status_code=status.HTTP_201_CREATED)
def create_pack(body: S.PackIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("wp:prepare")), db: Session = Depends(get_db)):
    try:
        pack = svc.create(db, p.tenant, body, p.membership.id, p.user.full_name)
    except svc.WorkpaperError as e:
        raise _err(e)
    db.commit()
    db.refresh(pack)
    return svc.pack_detail(db, pack)


@router.get("/packs/{pack_id}", response_model=S.PackDetail)
def get_pack(pack_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.pack_detail(db, _pack(db, pack_id))


@router.post("/packs/{pack_id}/items", response_model=S.PackDetail, status_code=status.HTTP_201_CREATED)
def add_item(pack_id: uuid.UUID, body: S.ItemIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("wp:prepare")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    svc.add_item(db, pack, body)
    db.commit()
    return svc.pack_detail(db, pack)


@router.patch("/packs/{pack_id}/items/{item_id}", response_model=S.PackDetail)
def patch_item(pack_id: uuid.UUID, item_id: uuid.UUID, body: S.ItemPatch, p: Principal = Depends(edit), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    it = next((i for i in pack.items if i.id == item_id), None)
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "item_not_found"})
    needed = "wp:review" if body.status in ("reviewed", "signed_off") else "wp:prepare"
    if not p.can(needed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "permission_denied", "permission": needed})
    try:
        svc.patch_item(db, pack, it, body, p.membership.id, p.user.full_name)
    except svc.WorkpaperError as e:
        raise _err(e)
    db.commit()
    return svc.pack_detail(db, pack)


@router.post("/packs/{pack_id}/checks", response_model=S.PackDetail)
def run_checks(pack_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("wp:prepare")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    svc.run_checks(db, pack)
    db.commit()
    return svc.pack_detail(db, pack)


@router.post("/packs/{pack_id}/issues", response_model=S.PackDetail, status_code=status.HTTP_201_CREATED)
def raise_issue(pack_id: uuid.UUID, body: S.IssueIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("wp:review")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    svc.raise_issue(db, pack, body, p.membership.id, p.user.full_name)
    db.commit()
    return svc.pack_detail(db, pack)


@router.post("/packs/{pack_id}/issues/{issue_id}/resolve", response_model=S.PackDetail)
def resolve_issue(pack_id: uuid.UUID, issue_id: uuid.UUID, body: S.IssueResolveIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("wp:prepare")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    x = next((i for i in pack.issues if i.id == issue_id), None)
    if x is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "issue_not_found"})
    if body.waive and not p.can("wp:signoff"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": "permission_denied", "permission": "wp:signoff"})
    try:
        svc.resolve_issue(db, pack, x, body, p.membership.id, p.user.full_name)
    except svc.WorkpaperError as e:
        raise _err(e)
    db.commit()
    return svc.pack_detail(db, pack)


@router.post("/packs/{pack_id}/submit", response_model=S.PackDetail)
def submit(pack_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("wp:prepare")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    try:
        svc.submit_for_review(db, pack, p.membership.id, p.user.full_name)
    except svc.WorkpaperError as e:
        raise _err(e)
    db.commit()
    return svc.pack_detail(db, pack)


@router.post("/packs/{pack_id}/sign-off", response_model=S.PackDetail)
def sign_off(pack_id: uuid.UUID, body: S.SignOffIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("wp:signoff")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    try:
        svc.sign_off(db, p.tenant, pack, body, p.membership.id, p.user.full_name)
    except svc.WorkpaperError as e:
        raise _err(e)
    db.commit()
    return svc.pack_detail(db, pack)


@router.post("/packs/{pack_id}/reopen", response_model=S.PackDetail)
def reopen(pack_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("wp:signoff")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    try:
        svc.reopen(db, pack, p.membership.id, p.user.full_name)
    except svc.WorkpaperError as e:
        raise _err(e)
    db.commit()
    return svc.pack_detail(db, pack)


@router.post("/packs/{pack_id}/lodge", response_model=S.PackDetail)
def lodge(pack_id: uuid.UUID, body: S.LodgeIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("wp:lodge")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    try:
        svc.lodge(db, pack, body, p.membership.id, p.user.full_name)
    except svc.WorkpaperError as e:
        raise _err(e)
    db.commit()
    return svc.pack_detail(db, pack)


# ------------------------------------------------------------------ ledger
@router.get("/ledger/connections", response_model=list[S.LedgerConnectionOut])
def connections(p: Principal = Depends(view), db: Session = Depends(get_db)):
    rows = db.execute(select(LedgerConnection).order_by(LedgerConnection.created_at.desc())).scalars().all()
    names = member_names(db, {c.connected_by_membership_id for c in rows})
    cn = client_name_map(db, {c.client_id for c in rows})
    return [svc.connection_out(db, c, names, cn) for c in rows]


@router.post("/ledger/connect", response_model=dict)
def connect(body: S.ConnectIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("wp:prepare")), db: Session = Depends(get_db)):
    try:
        conn, url = svc.connect(db, p.tenant, body, p.membership.id, p.user.full_name)
    except svc.WorkpaperError as e:
        raise _err(e)
    db.commit()
    return {"connection": svc.connection_out(db, conn).model_dump(mode="json"), "authorize_url": url,
            "message": "Connected in simulation — figures are generated until Xero credentials are configured." if conn.simulated else "Open the authorisation URL to finish connecting Xero."}


@router.post("/packs/{pack_id}/sync", response_model=S.SyncOut)
def sync(pack_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("wp:prepare")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    try:
        n, simulated, source, note = svc.sync(db, pack, p.membership.id, p.user.full_name)
    except svc.WorkpaperError as e:
        raise _err(e)
    db.commit()
    return S.SyncOut(pack=svc.pack_detail(db, pack), synced=n, simulated=simulated, source=source, message=note or f"{n} accounts synced from {source}.")
