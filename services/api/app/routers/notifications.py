import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import schemas_platform as S
from app.core.database import get_db
from app.core.deps import Principal, get_principal
from app.core.security import utcnow
from app.models.platform import Notification
from app.services import notify_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _out(n: Notification) -> S.NotificationOut:
    return S.NotificationOut(id=n.id, kind=n.kind, title=n.title, body=n.body, link=n.link, module_key=n.module_key, read_at=n.read_at, created_at=n.created_at)


@router.get("", response_model=list[S.NotificationOut])
def list_mine(unread: bool = False, limit: int = Query(30, ge=1, le=100), p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    stmt = select(Notification).where(Notification.membership_id == p.membership.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    return [_out(n) for n in db.execute(stmt.order_by(Notification.created_at.desc()).limit(limit)).scalars()]


@router.get("/unread-count", response_model=S.UnreadOut)
def unread(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return S.UnreadOut(unread=notify_service.unread_count(db, p.membership.id))


@router.post("/{notification_id}/read", response_model=S.NotificationOut)
def mark_read(notification_id: uuid.UUID, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None or n.membership_id != p.membership.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if n.read_at is None:
        n.read_at = utcnow()
        db.commit()
    return _out(n)


@router.post("/read-all", response_model=S.UnreadOut)
def read_all(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.membership_id == p.membership.id, Notification.read_at.is_(None)).values(read_at=utcnow()))
    db.commit()
    return S.UnreadOut(unread=0)
