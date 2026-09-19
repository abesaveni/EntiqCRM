"""EnTIQ Client portal — module 14. Staff side under /client (require_module); the client's own surface under /portal with its own passwordless auth."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.core.limiter import limiter
from app.core.storage import get_storage
from app.models.crm import Client, Contact
from app.models.platform import Document
from app.modules.client import schemas as S
from app.modules.client import service as svc
from app.modules.requests import schemas as RS
from app.modules.requests import service as req_svc
from app.modules.requests.models import RequestPack
from app.services import document_service

router = APIRouter(prefix="/client", tags=["client-portal-staff"])
portal = APIRouter(prefix="/portal", tags=["portal"])
view = require_module("client")
edit = require_module("client", write=True)


def _err(e: svc.PortalError) -> HTTPException:
    code = {"unauthenticated": 401, "invalid_link": 401, "access_revoked": 403, "portal_unavailable": 403, "not_found": 404, "not_a_signer": 403, "no_email": 400}.get(e.error, 400)
    return HTTPException(code, detail={"error": e.error, "message": e.message})


# ------------------------------------------------------------------ staff
@router.get("/overview", response_model=S.StaffOverview)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.staff_overview(db, p.tenant.id)


@router.get("/contacts", response_model=list[S.PortalContactOut])
def contacts(client_id: uuid.UUID | None = None, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.portal_contacts(db, client_id)


@router.post("/contacts/{contact_id}/invite", response_model=S.PortalContactOut)
def invite(contact_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("client:invite")), db: Session = Depends(get_db)):
    ct = db.get(Contact, contact_id)
    if ct is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "contact_not_found"})
    try:
        svc.invite(db, p.tenant, ct, p.membership.id, p.user.full_name)
    except svc.PortalError as e:
        raise _err(e)
    db.commit()
    return next(x for x in svc.portal_contacts(db, ct.client_id) if x.contact_id == ct.id)


@router.post("/contacts/{contact_id}/revoke", response_model=S.PortalContactOut)
def revoke(contact_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("client:manage")), db: Session = Depends(get_db)):
    ct = db.get(Contact, contact_id)
    if ct is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "contact_not_found"})
    svc.revoke(db, ct, p.membership.id, p.user.full_name)
    db.commit()
    return next(x for x in svc.portal_contacts(db, ct.client_id) if x.contact_id == ct.id)


@router.get("/clients/{client_id}/messages", response_model=list[S.ThreadMessage])
def staff_thread(client_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    if db.get(Client, client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "client_not_found"})
    svc.mark_read(db, client_id, by_client=False)
    db.commit()
    return svc.thread(db, client_id, for_client=False)


@router.post("/clients/{client_id}/messages", response_model=list[S.ThreadMessage], status_code=status.HTTP_201_CREATED)
def staff_post(client_id: uuid.UUID, body: S.MessageIn, p: Principal = Depends(edit), db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "client_not_found"})
    svc.post_from_staff(db, p.tenant, c, body.body, p.membership.id, p.user.full_name)
    db.commit()
    return svc.thread(db, client_id, for_client=False)


# ------------------------------------------------------------------ portal auth (public)
@portal.post("/auth/request-link", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
def request_link(request: Request, body: S.RequestLinkIn, db: Session = Depends(get_db)):
    svc.request_login_link(db, body.email)
    db.commit()
    return {"sent": True}   # never reveals whether the email exists


@portal.post("/auth/exchange", response_model=S.PortalTokenOut)
@limiter.limit("10/minute")
def exchange(request: Request, body: S.ExchangeIn, db: Session = Depends(get_db)):
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else None)
    try:
        token, sess, t, c, ct = svc.exchange(db, body.token, ip, request.headers.get("user-agent"))
    except svc.PortalError as e:
        raise _err(e)
    db.commit()
    return S.PortalTokenOut(access_token=token, expires_at=sess.expires_at, practice_name=t.name, client_name=c.name)


# ------------------------------------------------------------------ portal (authenticated as a contact)
class PortalPrincipal:
    def __init__(self, tenant, client, contact, session):
        self.tenant, self.client, self.contact, self.session = tenant, client, contact, session


def portal_principal(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> PortalPrincipal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"error": "unauthenticated"})
    try:
        t, c, ct, sess = svc.authenticate(db, authorization.split(" ", 1)[1].strip())
    except svc.PortalError as e:
        raise _err(e)
    return PortalPrincipal(t, c, ct, sess)


@portal.get("/me", response_model=S.PortalMe)
def portal_me(pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    return svc.me(db, pp.tenant, pp.client, pp.contact)


@portal.get("/home", response_model=S.PortalHome)
def portal_home(pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    out = svc.home(db, pp.tenant, pp.client, pp.contact)
    db.commit()
    return out


@portal.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def portal_logout(pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    pp.session.revoked = True
    db.commit()
    return Response(status_code=204)


@portal.get("/documents", response_model=list[S.PortalDocument])
def portal_documents(pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    return svc.documents(db, pp.client)


@portal.get("/documents/{document_id}/download")
def portal_download(document_id: uuid.UUID, pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    try:
        d = svc.portal_document(db, pp.client, document_id)
    except svc.PortalError as e:
        raise _err(e)
    return Response(content=get_storage().get(d.storage_key), media_type=d.content_type, headers={"Content-Disposition": f'attachment; filename="{d.filename.replace(chr(34), "")}"', "Cache-Control": "private, no-store"})


@portal.post("/documents", response_model=S.PortalDocument, status_code=status.HTTP_201_CREATED)
async def portal_upload(file: UploadFile = File(...), pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    data = await file.read()
    try:
        d = document_service.store(db, tenant_id=pp.tenant.id, data=data, filename=file.filename or "upload", content_type=file.content_type, client_id=pp.client.id, module_key="client", kind="from_client", uploaded_by_membership_id=None, actor_label=pp.contact.full_name)
    except document_service.UploadRefused as e:
        raise HTTPException({"malware_detected": 422, "file_too_large": 413, "scan_unavailable": 503}.get(e.error, 400), detail={"error": e.error, **e.extra})
    d.visible_to_client = True
    db.commit()
    return S.PortalDocument(id=d.id, filename=d.filename, kind=d.kind, size_bytes=d.size_bytes, content_type=d.content_type, uploaded_by="You", created_at=d.created_at)


@portal.get("/messages", response_model=list[S.ThreadMessage])
def portal_messages(pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    svc.mark_read(db, pp.client.id, by_client=True)
    db.commit()
    return svc.thread(db, pp.client.id, for_client=True)


@portal.post("/messages", response_model=list[S.ThreadMessage], status_code=status.HTTP_201_CREATED)
def portal_post(body: S.MessageIn, pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    svc.post_from_client(db, pp.tenant, pp.contact, body.body)
    db.commit()
    return svc.thread(db, pp.client.id, for_client=True)


@portal.post("/agreements/{agreement_id}/resend", status_code=status.HTTP_202_ACCEPTED)
def portal_resend(agreement_id: uuid.UUID, pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    try:
        n = svc.resend_signing_link(db, pp.tenant, pp.client, pp.contact, agreement_id)
    except svc.PortalError as e:
        raise _err(e)
    db.commit()
    return {"sent": n}


# Requests, worked from inside the portal (same service as the tokened surface; the session is the credential)
def _pack_for(db: Session, pp: PortalPrincipal, pack_id: uuid.UUID) -> RequestPack:
    p = db.get(RequestPack, pack_id)
    if p is None or p.client_id != pp.client.id or p.status == "cancelled":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "request_not_found"})
    return p


@portal.get("/requests/{pack_id}", response_model=RS.PublicPack)
def portal_request(pack_id: uuid.UUID, pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    return req_svc.public_pack(db, _pack_for(db, pp, pack_id), pp.tenant)


@portal.post("/requests/{pack_id}/questions", response_model=RS.PublicPack)
def portal_request_answer(pack_id: uuid.UUID, body: RS.AnswerIn, pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    p = _pack_for(db, pp, pack_id)
    try:
        req_svc.answer_question(db, p, body.key, body.answer, pp.contact.full_name)
    except req_svc.RequestError as e:
        raise HTTPException(400, detail={"error": e.error, "message": e.message})
    db.commit()
    return req_svc.public_pack(db, p, pp.tenant)


@portal.post("/requests/{pack_id}/items/{item_id}/upload", response_model=RS.PublicPack)
async def portal_request_upload(pack_id: uuid.UUID, item_id: uuid.UUID, file: UploadFile = File(...), pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    p = _pack_for(db, pp, pack_id)
    item = next((x for x in p.items if x.id == item_id), None)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "item_not_found"})
    data = await file.read()
    try:
        d = document_service.store(db, tenant_id=p.tenant_id, data=data, filename=file.filename or "upload", content_type=file.content_type, client_id=p.client_id, module_key="requests", kind=item.category, uploaded_by_membership_id=None, actor_label=pp.contact.full_name)
        req_svc.attach(db, p, item, d, pp.contact.full_name)
    except document_service.UploadRefused as e:
        raise HTTPException({"malware_detected": 422, "file_too_large": 413, "scan_unavailable": 503}.get(e.error, 400), detail={"error": e.error, **e.extra})
    except req_svc.RequestError as e:
        raise HTTPException(409, detail={"error": e.error, "message": e.message})
    db.commit()
    return req_svc.public_pack(db, p, pp.tenant)


@portal.post("/requests/{pack_id}/items/{item_id}/not-applicable", response_model=RS.PublicPack)
def portal_request_na(pack_id: uuid.UUID, item_id: uuid.UUID, body: RS.NotApplicableIn, pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    p = _pack_for(db, pp, pack_id)
    item = next((x for x in p.items if x.id == item_id), None)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "item_not_found"})
    try:
        req_svc.mark_not_applicable(db, p, item, body.note, pp.contact.full_name)
    except req_svc.RequestError as e:
        raise HTTPException(409, detail={"error": e.error, "message": e.message})
    db.commit()
    return req_svc.public_pack(db, p, pp.tenant)


@portal.post("/requests/{pack_id}/submit", response_model=RS.PublicPack)
def portal_request_submit(pack_id: uuid.UUID, pp: PortalPrincipal = Depends(portal_principal), db: Session = Depends(get_db)):
    p = _pack_for(db, pp, pack_id)
    try:
        req_svc.submit(db, p, pp.contact.full_name)
    except req_svc.RequestError as e:
        raise HTTPException(400, detail={"error": e.error, "message": e.message})
    db.commit()
    return req_svc.public_pack(db, p, pp.tenant)
