"""EnTIQ Advisory — module 10."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.models.crm import Client
from app.modules.advisory import schemas as S
from app.modules.advisory import service as svc
from app.modules.advisory.models import Action, Alert, Meeting, Snapshot
from app.services.crm_service import client_name_map, member_names

router = APIRouter(prefix="/advisory", tags=["advisory"])
view = require_module("advisory")
edit = require_module("advisory", write=True)


def _client(db: Session, client_id: uuid.UUID) -> Client:
    c = db.get(Client, client_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "client_not_found"})
    return c


def _err(e: svc.AdvisoryError) -> HTTPException:
    return HTTPException({"client_not_found": 404, "workpaper_not_found": 404, "wrong_state": 409, "already_held": 409, "not_held": 409}.get(e.error, 400), detail={"error": e.error, "message": e.message})


@router.get("/overview", response_model=S.OverviewOut)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.overview(db)


@router.get("/clients/{client_id}", response_model=S.ClientAdvisoryOut)
def client_view(client_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.client_view(db, _client(db, client_id))


# ------------------------------------------------------------------ snapshots
@router.post("/snapshots", response_model=S.SnapshotOut, status_code=status.HTTP_201_CREATED)
def create_snapshot(body: S.SnapshotIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("advisory:forecast")), db: Session = Depends(get_db)):
    try:
        s = svc.create_snapshot(db, p.tenant, body, p.membership.id, p.user.full_name)
    except svc.AdvisoryError as e:
        raise _err(e)
    db.commit()
    return svc.snapshot_out(s, member_names(db, {s.created_by_membership_id}), client_name_map(db, {s.client_id}))


@router.get("/snapshots", response_model=list[S.SnapshotOut])
def list_snapshots(client_id: uuid.UUID | None = None, limit: int = Query(50, ge=1, le=500), p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Snapshot).order_by(Snapshot.as_at.desc())
    if client_id:
        stmt = stmt.where(Snapshot.client_id == client_id)
    rows = db.execute(stmt.limit(limit)).scalars().all()
    return [svc.snapshot_out(s, member_names(db, {x.created_by_membership_id for x in rows}), client_name_map(db, {x.client_id for x in rows})) for s in rows]


# ------------------------------------------------------------------ alerts
@router.get("/alerts", response_model=list[S.AlertOut])
def list_alerts(status_: str | None = Query("open", alias="status"), severity: str | None = None, client_id: uuid.UUID | None = None, p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Alert).order_by(Alert.severity.desc(), Alert.created_at.desc())
    if status_ and status_ != "all":
        stmt = stmt.where(Alert.status == status_)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if client_id:
        stmt = stmt.where(Alert.client_id == client_id)
    rows = db.execute(stmt).scalars().all()
    return [svc.alert_out(a, client_name_map(db, {x.client_id for x in rows})) for a in rows]


@router.post("/alerts", response_model=S.AlertOut, status_code=status.HTTP_201_CREATED)
def raise_alert(body: S.AlertIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("advisory:forecast")), db: Session = Depends(get_db)):
    c = _client(db, body.client_id)
    a = Alert(tenant_id=p.tenant.id, client_id=c.id, code="manual", title=body.title, detail=body.detail, severity=body.severity, recommendation=body.recommendation, auto=False)
    db.add(a)
    db.commit()
    return svc.alert_out(a, {c.id: c.name})


@router.post("/alerts/{alert_id}/dismiss", response_model=S.AlertOut)
def dismiss_alert(alert_id: uuid.UUID, body: S.DismissIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("advisory:forecast")), db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "alert_not_found"})
    from app.core.security import utcnow
    a.status, a.dismissed_reason, a.resolved_at = "dismissed", body.reason, utcnow()
    db.commit()
    return svc.alert_out(a, client_name_map(db, {a.client_id}))


# ------------------------------------------------------------------ actions
@router.get("/actions", response_model=list[S.ActionOut])
def list_actions(status_: str | None = Query(None, alias="status"), client_id: uuid.UUID | None = None, mine: bool = False, p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Action).order_by(Action.status, Action.due_on.is_(None), Action.due_on)
    if status_:
        stmt = stmt.where(Action.status == status_)
    if client_id:
        stmt = stmt.where(Action.client_id == client_id)
    if mine:
        stmt = stmt.where(Action.owner_membership_id == p.membership.id)
    rows = db.execute(stmt).scalars().all()
    return [svc.action_out(a, member_names(db, {x.owner_membership_id for x in rows}), client_name_map(db, {x.client_id for x in rows})) for a in rows]


@router.post("/actions", response_model=S.ActionOut, status_code=status.HTTP_201_CREATED)
def create_action(body: S.ActionIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("advisory:meet")), db: Session = Depends(get_db)):
    try:
        a = svc.create_action(db, p.tenant, body, p.membership.id, p.user.full_name)
    except svc.AdvisoryError as e:
        raise _err(e)
    db.commit()
    return svc.action_out(a, member_names(db, {a.owner_membership_id}), client_name_map(db, {a.client_id}))


@router.patch("/actions/{action_id}", response_model=S.ActionOut)
def patch_action(action_id: uuid.UUID, body: S.ActionPatch, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("advisory:meet")), db: Session = Depends(get_db)):
    a = db.get(Action, action_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "action_not_found"})
    svc.patch_action(db, a, body, p.membership.id, p.user.full_name)
    db.commit()
    return svc.action_out(a, member_names(db, {a.owner_membership_id}), client_name_map(db, {a.client_id}))


# ------------------------------------------------------------------ meetings
@router.get("/meetings", response_model=list[S.MeetingOut])
def list_meetings(status_: str | None = Query(None, alias="status"), client_id: uuid.UUID | None = None, p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Meeting).order_by(Meeting.scheduled_for.desc())
    if status_:
        stmt = stmt.where(Meeting.status == status_)
    if client_id:
        stmt = stmt.where(Meeting.client_id == client_id)
    rows = db.execute(stmt).scalars().all()
    names = member_names(db, {m.prepared_by_membership_id for m in rows})
    cn = client_name_map(db, {m.client_id for m in rows})
    return [svc.meeting_out(db, m, names, cn) for m in rows]


def _meeting(db: Session, meeting_id: uuid.UUID) -> Meeting:
    m = db.get(Meeting, meeting_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "meeting_not_found"})
    return m


def _detail(db: Session, m: Meeting) -> S.MeetingDetail:
    names = member_names(db, {m.prepared_by_membership_id})
    cn = client_name_map(db, {m.client_id})
    snap = db.get(Snapshot, m.snapshot_id) if m.snapshot_id else None
    alerts = db.execute(select(Alert).where(Alert.client_id == m.client_id, Alert.status == "open").order_by(Alert.severity.desc())).scalars().all()
    actions = db.execute(select(Action).where(Action.meeting_id == m.id).order_by(Action.created_at)).scalars().all()
    return S.MeetingDetail(**svc.meeting_out(db, m, names, cn).model_dump(),
                           snapshot=svc.snapshot_out(snap, member_names(db, {snap.created_by_membership_id}), cn) if snap else None,
                           alerts=[svc.alert_out(a, cn) for a in alerts], actions=[svc.action_out(a, member_names(db, {x.owner_membership_id for x in actions}), cn) for a in actions])


@router.post("/meetings", response_model=S.MeetingDetail, status_code=status.HTTP_201_CREATED)
def create_meeting(body: S.MeetingIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("advisory:meet")), db: Session = Depends(get_db)):
    try:
        m = svc.create_meeting(db, p.tenant, body, p.membership.id, p.user.full_name)
    except svc.AdvisoryError as e:
        raise _err(e)
    db.commit()
    return _detail(db, m)


@router.get("/meetings/{meeting_id}", response_model=S.MeetingDetail)
def get_meeting(meeting_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    return _detail(db, _meeting(db, meeting_id))


@router.patch("/meetings/{meeting_id}", response_model=S.MeetingDetail)
def patch_meeting(meeting_id: uuid.UUID, body: S.MeetingPatch, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("advisory:meet")), db: Session = Depends(get_db)):
    m = _meeting(db, meeting_id)
    data = body.model_dump(exclude_unset=True)
    if "agenda" in data and data["agenda"] is not None:
        m.agenda = [a if isinstance(a, dict) else a.model_dump() for a in data.pop("agenda")]
    for k, v in data.items():
        setattr(m, k, v)
    db.commit()
    return _detail(db, m)


@router.post("/meetings/{meeting_id}/prepare", response_model=S.MeetingDetail)
def prepare(meeting_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("advisory:meet")), db: Session = Depends(get_db)):
    m = _meeting(db, meeting_id)
    try:
        svc.prepare_meeting(db, m, p.membership.id, p.user.full_name)
    except svc.AdvisoryError as e:
        raise _err(e)
    db.commit()
    return _detail(db, m)


@router.post("/meetings/{meeting_id}/hold", response_model=S.MeetingDetail)
def hold(meeting_id: uuid.UUID, body: S.HoldIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("advisory:meet")), db: Session = Depends(get_db)):
    m = _meeting(db, meeting_id)
    try:
        svc.hold_meeting(db, p.tenant, m, body, p.membership.id, p.user.full_name)
    except svc.AdvisoryError as e:
        raise _err(e)
    db.commit()
    return _detail(db, m)


@router.post("/meetings/{meeting_id}/publish", response_model=S.MeetingDetail)
def publish(meeting_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("advisory:publish")), db: Session = Depends(get_db)):
    m = _meeting(db, meeting_id)
    try:
        svc.publish_meeting(db, p.tenant, m, p.membership.id, p.user.full_name)
    except svc.AdvisoryError as e:
        raise _err(e)
    db.commit()
    return _detail(db, m)
