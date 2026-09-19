"""EnTIQ Requests — module 06. Staff routes behind require_module('requests'); the client surface is public and tokened (and also reachable from the Client portal)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.core.limiter import limiter
from app.core.storage import get_storage
from app.models.platform import Document
from app.modules.requests import schemas as S
from app.modules.requests import service as svc
from app.modules.requests.models import RequestItem, RequestPack
from app.services import document_service
from app.services.crm_service import client_name_map, member_names

router = APIRouter(prefix="/requests", tags=["requests"])
public = APIRouter(prefix="/requests/public", tags=["requests-public"])
view = require_module("requests")
edit = require_module("requests", write=True)


def _pack(db: Session, pack_id: uuid.UUID) -> RequestPack:
    p = db.get(RequestPack, pack_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "request_not_found"})
    return p


def _item(p: RequestPack, item_id: uuid.UUID) -> RequestItem:
    i = next((x for x in p.items if x.id == item_id), None)
    if i is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "item_not_found"})
    return i


def _err(e: svc.RequestError) -> HTTPException:
    return HTTPException({"client_not_found": 404, "closed": 409, "already_accepted": 409, "unknown_question": 404}.get(e.error, 400), detail={"error": e.error, "message": e.message})


@router.get("/overview", response_model=S.OverviewOut)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.overview(db)


@router.get("/templates", response_model=list[S.TemplateOut])
def list_templates(p: Principal = Depends(view)):
    return svc.templates_out()


@router.get("/packs", response_model=list[S.PackOut])
def list_packs(status_: str | None = Query(None, alias="status"), client_id: uuid.UUID | None = None, open_only: bool = Query(False, alias="open"), limit: int = Query(200, ge=1, le=1000), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(RequestPack)
    if status_:
        stmt = stmt.where(RequestPack.status == status_)
    if open_only:
        stmt = stmt.where(RequestPack.status.notin_(["complete", "cancelled"]))
    if client_id:
        stmt = stmt.where(RequestPack.client_id == client_id)
    rows = db.execute(stmt.order_by(RequestPack.updated_at.desc()).limit(limit)).scalars().all()
    names = member_names(db, {r.created_by_membership_id for r in rows})
    cn = client_name_map(db, {r.client_id for r in rows})
    return [svc.pack_out(db, r, names, cn) for r in rows]


@router.post("/packs", response_model=S.PackDetail, status_code=status.HTTP_201_CREATED)
def create_pack(body: S.PackIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("requests:create")), db: Session = Depends(get_db)):
    try:
        pack, url = svc.create(db, p.tenant, body, p.membership.id, p.user.full_name)
    except svc.RequestError as e:
        raise _err(e)
    db.commit()
    db.refresh(pack)
    return svc.pack_detail(db, pack, url)


@router.get("/packs/{pack_id}", response_model=S.PackDetail)
def get_pack(pack_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.pack_detail(db, _pack(db, pack_id))


@router.post("/packs/{pack_id}/send", response_model=S.PackDetail)
def send_pack(pack_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("requests:create")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    try:
        url = svc.send(db, p.tenant, pack, p.membership.id, p.user.full_name)
    except svc.RequestError as e:
        raise _err(e)
    db.commit()
    return svc.pack_detail(db, pack, url)


@router.post("/packs/{pack_id}/remind", response_model=S.PackDetail)
def remind(pack_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("requests:create")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    try:
        url = svc.send(db, p.tenant, pack, p.membership.id, p.user.full_name, reminder=True)
    except svc.RequestError as e:
        raise _err(e)
    db.commit()
    return svc.pack_detail(db, pack, url)


@router.post("/packs/{pack_id}/items", response_model=S.PackDetail)
def add_items(pack_id: uuid.UUID, body: S.AddItemsIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("requests:create")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    try:
        svc.add_items(db, p.tenant, pack, body, p.membership.id, p.user.full_name)
    except svc.RequestError as e:
        raise _err(e)
    db.commit()
    return svc.pack_detail(db, pack)


@router.post("/packs/{pack_id}/items/{item_id}/review", response_model=S.PackDetail)
def review_item(pack_id: uuid.UUID, item_id: uuid.UUID, body: S.ReviewIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("requests:review")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    try:
        svc.review(db, p.tenant, pack, _item(pack, item_id), body, p.membership.id, p.user.full_name)
    except svc.RequestError as e:
        raise _err(e)
    db.commit()
    return svc.pack_detail(db, pack)


@router.post("/packs/{pack_id}/complete", response_model=S.PackDetail)
def complete_pack(pack_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("requests:approve")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    svc.complete(db, p.tenant, pack, p.membership.id, p.user.full_name)
    db.commit()
    return svc.pack_detail(db, pack)


@router.post("/packs/{pack_id}/cancel", response_model=S.PackDetail)
def cancel_pack(pack_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("requests:create")), db: Session = Depends(get_db)):
    pack = _pack(db, pack_id)
    try:
        svc.cancel(db, pack, p.membership.id, p.user.full_name)
    except svc.RequestError as e:
        raise _err(e)
    db.commit()
    return svc.pack_detail(db, pack)


# ------------------------------------------------------------------ client surface (tokened)
def _load(db: Session, token: str):
    try:
        return svc.load_by_token(db, token)
    except svc.TokenError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND if str(e) == "invalid_link" else status.HTTP_410_GONE, detail={"error": str(e)})


@public.get("/{token}", response_model=S.PublicPack)
@limiter.limit("60/minute")
def public_view(request: Request, token: str, db: Session = Depends(get_db)):
    p, t = _load(db, token)
    return svc.public_pack(db, p, t)


@public.post("/{token}/questions", response_model=S.PublicPack)
@limiter.limit("30/minute")
def public_answer(request: Request, token: str, body: S.AnswerIn, db: Session = Depends(get_db)):
    p, t = _load(db, token)
    try:
        svc.answer_question(db, p, body.key, body.answer, "Client")
    except svc.RequestError as e:
        raise _err(e)
    db.commit()
    return svc.public_pack(db, p, t)


@public.post("/{token}/items/{item_id}/upload", response_model=S.PublicPack)
@limiter.limit("30/minute")
async def public_upload(request: Request, token: str, item_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
    p, t = _load(db, token)
    item = _item(p, item_id)
    data = await file.read()
    try:
        d = document_service.store(db, tenant_id=p.tenant_id, data=data, filename=file.filename or "upload", content_type=file.content_type, client_id=p.client_id, module_key="requests", kind=item.category,
                                   uploaded_by_membership_id=None, actor_label="Client")
        svc.attach(db, p, item, d, "Client")
    except document_service.UploadRefused as e:
        raise HTTPException({"malware_detected": 422, "file_too_large": 413, "scan_unavailable": 503}.get(e.error, 400), detail={"error": e.error, **e.extra})
    except svc.RequestError as e:
        raise _err(e)
    db.commit()
    return svc.public_pack(db, p, t)


@public.post("/{token}/items/{item_id}/not-applicable", response_model=S.PublicPack)
@limiter.limit("30/minute")
def public_na(request: Request, token: str, item_id: uuid.UUID, body: S.NotApplicableIn, db: Session = Depends(get_db)):
    p, t = _load(db, token)
    try:
        svc.mark_not_applicable(db, p, _item(p, item_id), body.note, "Client")
    except svc.RequestError as e:
        raise _err(e)
    db.commit()
    return svc.public_pack(db, p, t)


@public.get("/{token}/items/{item_id}/file")
@limiter.limit("30/minute")
def public_file(request: Request, token: str, item_id: uuid.UUID, db: Session = Depends(get_db)):
    p, t = _load(db, token)
    item = _item(p, item_id)
    d = db.get(Document, item.document_id) if item.document_id else None
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "no_file"})
    return Response(content=get_storage().get(d.storage_key), media_type=d.content_type, headers={"Content-Disposition": f'inline; filename="{d.filename.replace(chr(34), "")}"', "Cache-Control": "private, no-store"})


@public.post("/{token}/submit", response_model=S.PublicPack)
@limiter.limit("10/minute")
def public_submit(request: Request, token: str, db: Session = Depends(get_db)):
    p, t = _load(db, token)
    try:
        svc.submit(db, p, "Client")
    except svc.RequestError as e:
        raise _err(e)
    db.commit()
    return svc.public_pack(db, p, t)
