"""EnTIQ Academy — module 15."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require_module, require_permission
from app.core.security import utcnow
from app.models.identity import Membership
from app.modules.academy import schemas as S
from app.modules.academy import service as svc
from app.modules.academy.models import Certificate, Course, Enrolment, Lesson, Requirement
from app.services.crm_service import member_names

router = APIRouter(prefix="/academy", tags=["academy"])
view = require_module("academy")
edit = require_module("academy", write=True)


def _course(db: Session, course_id: uuid.UUID) -> Course:
    c = db.get(Course, course_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "course_not_found"})
    return c


def _err(e: svc.AcademyError) -> HTTPException:
    return HTTPException({"course_not_found": 404, "not_a_quiz": 400}.get(e.error, 400), detail={"error": e.error, "message": e.message})


@router.get("/overview", response_model=S.OverviewOut)
def overview(p: Principal = Depends(view), db: Session = Depends(get_db)):
    return svc.overview(db, p.tenant.id)


@router.get("/courses", response_model=list[S.CourseOut])
def list_courses(category: str | None = None, p: Principal = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Course).where(Course.status == "published").order_by(Course.category, Course.title)
    if category:
        stmt = stmt.where(Course.category == category)
    rows = db.execute(stmt).scalars().all()
    mine = {e.course_id: e for e in db.execute(select(Enrolment).where(Enrolment.membership_id == p.membership.id)).scalars()}
    return [svc.course_out(c, mine.get(c.id)) for c in rows]


@router.post("/courses/seed", response_model=list[S.CourseOut])
def seed(p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("academy:author")), db: Session = Depends(get_db)):
    svc.seed_catalogue(db, p.tenant.id, p.membership.id)
    db.commit()
    return [svc.course_out(c) for c in db.execute(select(Course).order_by(Course.category)).scalars().all()]


@router.post("/courses", response_model=S.CourseDetail, status_code=status.HTTP_201_CREATED)
def create_course(body: S.CourseIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("academy:author")), db: Session = Depends(get_db)):
    c = svc.create_course(db, p.tenant.id, body, p.membership.id)
    db.commit()
    db.refresh(c)
    return S.CourseDetail(**svc.course_out(c).model_dump(), lessons=[svc.lesson_out(l, author=True) for l in c.lessons], enrolment=None)


@router.get("/courses/{course_id}", response_model=S.CourseDetail)
def get_course(course_id: uuid.UUID, p: Principal = Depends(view), db: Session = Depends(get_db)):
    c = _course(db, course_id)
    e = svc._enrolment(db, p.membership.id, c.id)
    author = p.can("academy:author")
    done = set((e.completed_lessons or [])) if e else set()
    names = member_names(db, {e.membership_id}) if e else {}
    return S.CourseDetail(**svc.course_out(c, e).model_dump(), lessons=[svc.lesson_out(l, author=author, completed=done) for l in c.lessons],
                          enrolment=svc.enrolment_out(e, c, names) if e else None)


@router.post("/courses/{course_id}/start", response_model=S.CourseDetail)
def start(course_id: uuid.UUID, p: Principal = Depends(edit), db: Session = Depends(get_db)):
    c = _course(db, course_id)
    e = svc.start(db, p.tenant, p.membership.id, c)
    db.commit()
    return S.CourseDetail(**svc.course_out(c, e).model_dump(), lessons=[svc.lesson_out(l, author=p.can("academy:author"), completed=set(e.completed_lessons or [])) for l in c.lessons],
                          enrolment=svc.enrolment_out(e, c, member_names(db, {e.membership_id})))


@router.post("/courses/{course_id}/lessons/{lesson_id}/complete", response_model=S.EnrolmentOut)
def complete_lesson(course_id: uuid.UUID, lesson_id: uuid.UUID, p: Principal = Depends(edit), db: Session = Depends(get_db)):
    c = _course(db, course_id)
    l = next((x for x in c.lessons if x.id == lesson_id), None)
    if l is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "lesson_not_found"})
    if l.kind == "quiz":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"error": "quiz_needs_attempt", "message": "Submit answers to complete a quiz lesson"})
    e = svc.start(db, p.tenant, p.membership.id, c)
    svc.complete_lesson(db, e, c, l)
    if all(str(x.id) in set(e.completed_lessons or []) for x in c.lessons):
        svc._complete_course(db, p.tenant, e, c, p.user.full_name)
    db.commit()
    return svc.enrolment_out(e, c, member_names(db, {e.membership_id}))


@router.post("/courses/{course_id}/lessons/{lesson_id}/attempt", response_model=S.AttemptOut)
def attempt(course_id: uuid.UUID, lesson_id: uuid.UUID, body: S.AttemptIn, p: Principal = Depends(edit), db: Session = Depends(get_db)):
    c = _course(db, course_id)
    l = next((x for x in c.lessons if x.id == lesson_id), None)
    if l is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "lesson_not_found"})
    e = svc.start(db, p.tenant, p.membership.id, c)
    try:
        score, passed, feedback, cert = svc.submit_attempt(db, p.tenant, e, c, l, body, p.user.full_name)
    except svc.AcademyError as ex:
        raise _err(ex)
    db.commit()
    return S.AttemptOut(score=score, passed=passed, pass_mark=c.pass_mark, correct=sum(1 for f in feedback if f["correct"]), total=len(feedback),
                        enrolment=svc.enrolment_out(e, c, member_names(db, {e.membership_id})), certificate_serial=cert.serial if cert else None, feedback=feedback)


# ------------------------------------------------------------------ mine
@router.get("/my", response_model=S.MyLearning)
def my_learning(p: Principal = Depends(view), db: Session = Depends(get_db)):
    enrols = db.execute(select(Enrolment).where(Enrolment.membership_id == p.membership.id).order_by(Enrolment.due_on.is_(None), Enrolment.due_on)).scalars().all()
    courses = {c.id: c for c in db.execute(select(Course).where(Course.id.in_({e.course_id for e in enrols}))).scalars()} if enrols else {}
    names = member_names(db, {p.membership.id})
    certs = db.execute(select(Certificate).where(Certificate.membership_id == p.membership.id).order_by(Certificate.issued_on.desc())).scalars().all()
    rows = [r for r in svc.requirement_rows(db, p.tenant.id) if r.membership_id == p.membership.id]
    return S.MyLearning(enrolments=[svc.enrolment_out(e, courses[e.course_id], names) for e in enrols if e.course_id in courses],
                        certificates=[svc.certificate_out(c) for c in certs], compliance=rows)


# ------------------------------------------------------------------ team
@router.get("/enrolments", response_model=list[S.EnrolmentOut])
def enrolments(status_: str | None = Query(None, alias="status"), membership_id: uuid.UUID | None = None, p: Principal = Depends(view), _perm: Principal = Depends(require_permission("academy:report")), db: Session = Depends(get_db)):
    stmt = select(Enrolment)
    if status_:
        stmt = stmt.where(Enrolment.status == status_)
    if membership_id:
        stmt = stmt.where(Enrolment.membership_id == membership_id)
    rows = db.execute(stmt.order_by(Enrolment.due_on.is_(None), Enrolment.due_on)).scalars().all()
    courses = {c.id: c for c in db.execute(select(Course).where(Course.id.in_({e.course_id for e in rows}))).scalars()} if rows else {}
    names = member_names(db, {e.membership_id for e in rows})
    return [svc.enrolment_out(e, courses[e.course_id], names) for e in rows if e.course_id in courses]


@router.post("/enrolments", response_model=list[S.EnrolmentOut], status_code=status.HTTP_201_CREATED)
def assign(body: S.AssignIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("academy:enrol")), db: Session = Depends(get_db)):
    try:
        rows = svc.assign(db, p.tenant, body, p.membership.id, p.user.full_name)
    except svc.AcademyError as e:
        raise _err(e)
    db.commit()
    c = _course(db, body.course_id)
    names = member_names(db, {e.membership_id for e in rows})
    return [svc.enrolment_out(e, c, names) for e in rows]


@router.get("/certificates", response_model=list[S.CertificateOut])
def certificates(membership_id: uuid.UUID | None = None, p: Principal = Depends(view), _perm: Principal = Depends(require_permission("academy:report")), db: Session = Depends(get_db)):
    stmt = select(Certificate).order_by(Certificate.issued_on.desc())
    if membership_id:
        stmt = stmt.where(Certificate.membership_id == membership_id)
    return [svc.certificate_out(c) for c in db.execute(stmt).scalars().all()]


@router.get("/certificates/verify/{serial}")
def verify_certificate(serial: str, p: Principal = Depends(view), db: Session = Depends(get_db)):
    c = db.execute(select(Certificate).where(Certificate.serial == serial)).scalar_one_or_none()
    if c is None:
        return {"found": False}
    import hashlib
    expect = hashlib.sha256(f"{c.serial}|{c.member_name}|{c.course_title}|{c.score}|{c.issued_on.isoformat()}|{c.tenant_id}".encode()).hexdigest()
    return {"found": True, "intact": expect == c.sha256, "certificate": svc.certificate_out(c).model_dump(mode="json")}


# ------------------------------------------------------------------ compliance
@router.get("/requirements", response_model=list[S.RequirementOut])
def requirements(p: Principal = Depends(view), db: Session = Depends(get_db)):
    rows = db.execute(select(Requirement).order_by(Requirement.name)).scalars().all()
    courses = {c.id: c.title for c in db.execute(select(Course)).scalars()}
    compliance = svc.requirement_rows(db, p.tenant.id)
    return [svc.requirement_out(db, r, compliance, courses) for r in rows]


@router.post("/requirements", response_model=S.RequirementOut, status_code=status.HTTP_201_CREATED)
def create_requirement(body: S.RequirementIn, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("academy:author")), db: Session = Depends(get_db)):
    c = _course(db, body.course_id)
    r = Requirement(tenant_id=p.tenant.id, course_id=c.id, name=body.name or f"{c.title} — every {body.frequency_months} months", roles=body.roles, frequency_months=body.frequency_months,
                    grace_days=body.grace_days, reference=body.reference, created_by_membership_id=p.membership.id)
    db.add(r)
    db.commit()
    compliance = svc.requirement_rows(db, p.tenant.id)
    return svc.requirement_out(db, r, compliance, {c.id: c.title})


@router.post("/requirements/{requirement_id}/toggle", response_model=S.RequirementOut)
def toggle_requirement(requirement_id: uuid.UUID, p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("academy:author")), db: Session = Depends(get_db)):
    r = db.get(Requirement, requirement_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"error": "requirement_not_found"})
    r.is_active = not r.is_active
    db.commit()
    courses = {c.id: c.title for c in db.execute(select(Course)).scalars()}
    return svc.requirement_out(db, r, svc.requirement_rows(db, p.tenant.id), courses)


@router.get("/compliance", response_model=list[S.ComplianceRow])
def compliance(p: Principal = Depends(view), _perm: Principal = Depends(require_permission("academy:report")), db: Session = Depends(get_db)):
    return svc.requirement_rows(db, p.tenant.id)


@router.post("/compliance/enforce")
def enforce(p: Principal = Depends(edit), _perm: Principal = Depends(require_permission("academy:enrol")), db: Session = Depends(get_db)):
    n = svc.enforce_requirements(db, p.tenant, p.membership.id, p.user.full_name)
    db.commit()
    return {"enrolled": n}
