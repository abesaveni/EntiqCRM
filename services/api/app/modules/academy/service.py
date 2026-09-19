from __future__ import annotations

import hashlib
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import events, mailer
from app.core.config import settings
from app.core.security import utcnow
from app.models.identity import Membership, User
from app.models.tenant import Tenant
from app.modules.academy import schemas as S
from app.modules.academy.models import Attempt, Certificate, Course, Enrolment, Lesson, Requirement
from app.notify import templates
from app.services import notify_service
from app.services.crm_service import member_names


class AcademyError(Exception):
    def __init__(self, error: str, message: str | None = None):
        super().__init__(message or error)
        self.error, self.message = error, message or error


# ------------------------------------------------------------------ starter catalogue
CATALOGUE: list[dict[str, Any]] = [
    {
        "title": "AML/CTF for accounting practices", "category": "AML/CTF", "valid_months": 12, "pass_mark": 80,
        "summary": "Your obligations under the AML/CTF Act as a reporting entity: customer identification, ongoing due diligence, suspicious matters and record keeping.",
        "lessons": [
            {"title": "Why accountants are captured", "kind": "reading", "minutes": 8, "body": "Tranche 2 reforms bring accounting, legal and real-estate services into the AML/CTF regime. A reporting entity must enrol with AUSTRAC, adopt an AML/CTF program, identify and verify customers before providing a designated service, monitor the relationship, and report suspicious matters within the statutory window.\n\nThe practical effect for a practice: identity evidence on file before work starts, a documented risk rating per client, ongoing screening of the people behind the entity, and records kept for seven years."},
            {"title": "Customer identification and beneficial ownership", "kind": "reading", "minutes": 10, "body": "Identify the customer and, for non-individuals, every beneficial owner who ultimately owns or controls 25% or more. For a trust, that includes the trustee, appointor and named beneficiaries.\n\nIn EnTIQ: the Verify module records the identity check and the screening result; related parties come from the client record; the rating and the next review date are written back onto the client."},
            {"title": "Suspicious matters and tipping off", "kind": "reading", "minutes": 7, "body": "A suspicious matter report is due within 3 business days of forming the suspicion (24 hours where terrorism financing is suspected). Never tell the customer a report has been made — that is the tipping-off offence, and it applies even after the engagement ends."},
            {"title": "Knowledge check", "kind": "quiz", "minutes": 5, "questions": [
                {"id": "q1", "text": "What ownership threshold defines a beneficial owner?", "options": ["10%", "20%", "25%", "50%"], "correct": ["25%"], "points": 1},
                {"id": "q2", "text": "How long must AML/CTF records be kept?", "options": ["2 years", "5 years", "7 years", "Indefinitely"], "correct": ["7 years"], "points": 1},
                {"id": "q3", "text": "A client asks whether you have reported them to AUSTRAC. What do you do?", "options": ["Confirm it", "Deny it", "Neither confirm nor deny — disclosing is the tipping-off offence", "Refer them to AUSTRAC"], "correct": ["Neither confirm nor deny — disclosing is the tipping-off offence"], "points": 2},
                {"id": "q4", "text": "When must customer identification be completed?", "options": ["Before providing the designated service", "Within 30 days of engagement", "At the first tax return", "Only if the client seems risky"], "correct": ["Before providing the designated service"], "points": 2},
            ]},
        ],
    },
    {
        "title": "Privacy and client data handling", "category": "Privacy", "valid_months": 24, "pass_mark": 80,
        "summary": "Australian Privacy Principles in a practice: collection, use, storage, access and the Notifiable Data Breaches scheme.",
        "lessons": [
            {"title": "The APPs in practice", "kind": "reading", "minutes": 8, "body": "Collect only what you need for the service, tell the client why, keep it secure, and give access on request. TFNs carry extra protection under the Privacy (Tax File Number) Rule — never email one in plain text, never store it where it is not needed."},
            {"title": "Notifiable data breaches", "kind": "reading", "minutes": 7, "body": "An eligible data breach — unauthorised access or loss likely to cause serious harm — must be assessed within 30 days and, if confirmed, notified to the OAIC and affected individuals as soon as practicable. Report any suspected breach internally the same day."},
            {"title": "Knowledge check", "kind": "quiz", "minutes": 4, "questions": [
                {"id": "q1", "text": "Within how many days must a suspected eligible data breach be assessed?", "options": ["7", "14", "30", "60"], "correct": ["30"], "points": 2},
                {"id": "q2", "text": "A client emails asking for their TFN to be sent to their bookkeeper. What is safest?", "options": ["Reply with the TFN", "Send it in a separate email", "Share it through the secure client portal with the client's written authority", "Text it"], "correct": ["Share it through the secure client portal with the client's written authority"], "points": 2},
            ]},
        ],
    },
    {
        "title": "Cyber security essentials", "category": "Cyber", "valid_months": 12, "pass_mark": 80,
        "summary": "Phishing, business email compromise, MFA and safe file handling — the controls that actually stop practice breaches.",
        "lessons": [
            {"title": "Business email compromise", "kind": "reading", "minutes": 7, "body": "The common attack on a practice is not malware, it is a redirected payment. Any change to bank details — a client's or a supplier's — is verified by phone on a number you already hold, never on a number in the email requesting the change."},
            {"title": "Knowledge check", "kind": "quiz", "minutes": 3, "questions": [
                {"id": "q1", "text": "A long-standing client emails new bank details for their refund. What do you do first?", "options": ["Update the details", "Reply to confirm", "Call the number already on file to verify", "Ask for a bank statement by email"], "correct": ["Call the number already on file to verify"], "points": 2},
                {"id": "q2", "text": "Multi-factor authentication should be enabled on…", "options": ["Email only", "Accounting software only", "Every system holding client data", "Nothing — passwords are enough"], "correct": ["Every system holding client data"], "points": 1},
            ]},
        ],
    },
    {
        "title": "EnTIQ induction", "category": "Induction", "valid_months": None, "pass_mark": 70, "certificate": False,
        "summary": "How the practice runs work in EnTIQ: clients, onboarding, jobs, workpapers, requests and the client portal.",
        "lessons": [
            {"title": "One client record", "kind": "reading", "minutes": 5, "body": "Everything hangs off the client: contacts and relationships, documents, the onboarding case, identity and screening, agreements, requests, jobs and workpapers. If you are about to keep something in a spreadsheet, it probably belongs on the record."},
            {"title": "Working a job", "kind": "reading", "minutes": 5, "body": "Practice holds the job and its checklist; Workpapers holds the evidence and the sign-off; Requests collects what the client owes you; Sign executes the declaration. Time goes on the job as you work, not at the end of the month."},
        ],
    },
]


def seed_catalogue(db: Session, tenant_id: uuid.UUID, actor_mid: uuid.UUID | None) -> int:
    if db.execute(select(func.count()).select_from(Course)).scalar_one():
        return 0
    n = 0
    for spec in CATALOGUE:
        c = Course(tenant_id=tenant_id, title=spec["title"], summary=spec.get("summary"), category=spec["category"], level=spec.get("level", "All staff"), pass_mark=spec.get("pass_mark", 80),
                   certificate=spec.get("certificate", True), valid_months=spec.get("valid_months"), created_by_membership_id=actor_mid,
                   minutes=sum(l.get("minutes", 5) for l in spec["lessons"]))
        db.add(c)
        db.flush()
        for i, l in enumerate(spec["lessons"], 1):
            db.add(Lesson(tenant_id=tenant_id, course_id=c.id, title=l["title"], kind=l["kind"], order=i, minutes=l.get("minutes", 5), body=l.get("body"), video_url=l.get("video_url"), questions=l.get("questions", [])))
        n += 1
    db.flush()
    return n


# ------------------------------------------------------------------ serialisers
def lesson_out(l: Lesson, *, author: bool, completed: set[str] | None = None) -> S.LessonOut:
    qs = [S.QuestionOut(id=str(q.get("id") or f"q{i}"), text=q["text"], options=q["options"], points=q.get("points", 1), correct=q.get("correct") if author else None) for i, q in enumerate(l.questions or [], 1)]
    return S.LessonOut(id=l.id, title=l.title, kind=l.kind, order=l.order, minutes=l.minutes, body=l.body, video_url=l.video_url, questions=qs, completed=str(l.id) in (completed or set()))


def course_out(c: Course, enrolment: Enrolment | None = None) -> S.CourseOut:
    return S.CourseOut(id=c.id, title=c.title, summary=c.summary, category=c.category, level=c.level, minutes=c.minutes, pass_mark=c.pass_mark, certificate=c.certificate, valid_months=c.valid_months,
                       status=c.status, lesson_count=len(c.lessons), is_catalogue=c.tenant_id is None, enrolled=enrolment is not None, my_status=enrolment.status if enrolment else None,
                       my_progress=enrolment.progress if enrolment else 0, created_at=c.created_at)


def enrolment_out(e: Enrolment, course: Course, names: dict) -> S.EnrolmentOut:
    return S.EnrolmentOut(id=e.id, membership_id=e.membership_id, member_name=names.get(e.membership_id), course_id=e.course_id, course_title=course.title, category=course.category, status=e.status,
                          due_on=e.due_on, overdue=bool(e.due_on and e.due_on < date.today() and e.status != "completed"), progress=e.progress, best_score=e.best_score, attempts=e.attempts,
                          started_at=e.started_at, completed_at=e.completed_at, requirement_id=e.requirement_id)


def certificate_out(c: Certificate) -> S.CertificateOut:
    return S.CertificateOut(id=c.id, serial=c.serial, member_name=c.member_name, course_title=c.course_title, category=c.category, score=c.score, issued_on=c.issued_on, expires_on=c.expires_on,
                            expired=bool(c.expires_on and c.expires_on < date.today()), revoked=c.revoked_at is not None, sha256=c.sha256)


# ------------------------------------------------------------------ authoring
def create_course(db: Session, tenant_id: uuid.UUID, body: S.CourseIn, actor_mid: uuid.UUID) -> Course:
    c = Course(tenant_id=tenant_id, title=body.title, summary=body.summary, category=body.category, level=body.level, pass_mark=body.pass_mark, certificate=body.certificate, valid_months=body.valid_months,
               created_by_membership_id=actor_mid, minutes=sum(l.minutes for l in body.lessons) or 30)
    db.add(c)
    db.flush()
    for i, l in enumerate(body.lessons, 1):
        db.add(Lesson(tenant_id=tenant_id, course_id=c.id, title=l.title, kind=l.kind, order=i, minutes=l.minutes, body=l.body, video_url=l.video_url,
                      questions=[{"id": q.id or f"q{j}", "text": q.text, "options": q.options, "correct": q.correct, "points": q.points} for j, q in enumerate(l.questions, 1)]))
    db.flush()
    db.refresh(c)
    return c


# ------------------------------------------------------------------ enrolment + learning
def _enrolment(db: Session, membership_id: uuid.UUID, course_id: uuid.UUID, requirement_id: uuid.UUID | None = None) -> Enrolment | None:
    stmt = select(Enrolment).where(Enrolment.membership_id == membership_id, Enrolment.course_id == course_id)
    if requirement_id:
        stmt = stmt.where(Enrolment.requirement_id == requirement_id)
    return db.execute(stmt.order_by(Enrolment.created_at.desc())).scalars().first()


def assign(db: Session, tenant: Tenant, body: S.AssignIn, actor_mid: uuid.UUID, actor_label: str, *, requirement: Requirement | None = None) -> list[Enrolment]:
    course = db.get(Course, body.course_id)
    if course is None:
        raise AcademyError("course_not_found")
    if body.all_staff:
        members = db.execute(select(Membership).where(Membership.tenant_id == tenant.id, Membership.status == "active")).scalars().all()
        ids = [m.id for m in members]
    else:
        ids = body.membership_ids
    if not ids:
        raise AcademyError("no_members", "Choose at least one member, or assign to everyone")
    due = date.today() + timedelta(days=body.due_in_days)
    out: list[Enrolment] = []
    names = member_names(db, set(ids))
    for mid in ids:
        e = _enrolment(db, mid, course.id, requirement.id if requirement else None)
        if e and e.status != "completed":
            e.due_on = min(e.due_on, due) if e.due_on else due
            out.append(e)
            continue
        if e and e.status == "completed" and requirement is None:
            continue
        e = Enrolment(tenant_id=tenant.id, membership_id=mid, course_id=course.id, requirement_id=requirement.id if requirement else None, due_on=due, assigned_by_membership_id=actor_mid)
        db.add(e)
        out.append(e)
        notify_service.notify(db, tenant_id=tenant.id, membership_id=mid, kind="academy.assigned", title=f"Training assigned: {course.title}", body=f"Due {due:%d %b %Y}", link="/academy/my", module_key="academy")
        u = db.get(User, db.get(Membership, mid).user_id) if db.get(Membership, mid) else None
        if u:
            subject, text, html = templates.academy_assigned(name=u.full_name.split()[0], course=course.title, due=due.strftime("%d %b %Y"), minutes=course.minutes, app_url=settings.APP_PUBLIC_URL.rstrip("/"))
            mailer.queue_email(db, tenant_id=tenant.id, to=u.email, subject=subject, text=text, html=html, template="academy_assigned", ref_type="course", ref_id=course.id)
    db.flush()
    events.emit(db, tenant_id=tenant.id, module_key="academy", kind="academy.assigned", summary=f"{course.title} assigned to {len(out)} member(s)", actor_membership_id=actor_mid, actor_label=actor_label, ref_type="course", ref_id=course.id)
    return out


def start(db: Session, tenant: Tenant, membership_id: uuid.UUID, course: Course) -> Enrolment:
    e = _enrolment(db, membership_id, course.id)
    if e is None:
        e = Enrolment(tenant_id=tenant.id, membership_id=membership_id, course_id=course.id)
        db.add(e)
        db.flush()
    if e.status == "not_started":
        e.status, e.started_at = "in_progress", utcnow()
    return e


def complete_lesson(db: Session, e: Enrolment, course: Course, lesson: Lesson) -> Enrolment:
    done = set(e.completed_lessons or [])
    done.add(str(lesson.id))
    e.completed_lessons = sorted(done)
    total = max(1, len(course.lessons))
    e.progress = round(len(done & {str(l.id) for l in course.lessons}) / total * 100)
    if e.status == "not_started":
        e.status, e.started_at = "in_progress", utcnow()
    db.flush()
    return e


def _grade(lesson: Lesson, answers: dict[str, list[str]]) -> tuple[int, int, int, list[dict[str, Any]]]:
    qs = lesson.questions or []
    total = sum(q.get("points", 1) for q in qs) or 1
    got = 0
    feedback = []
    for i, q in enumerate(qs, 1):
        qid = str(q.get("id") or f"q{i}")
        picked = sorted(answers.get(qid, []))
        correct = sorted(q.get("correct", []))
        ok = picked == correct
        if ok:
            got += q.get("points", 1)
        feedback.append({"id": qid, "text": q["text"], "correct": ok, "expected": correct, "picked": picked})
    return round(got / total * 100), got, total, feedback


def submit_attempt(db: Session, tenant: Tenant, e: Enrolment, course: Course, lesson: Lesson, body: S.AttemptIn, member_name: str) -> tuple[int, bool, list[dict[str, Any]], Certificate | None]:
    if lesson.kind != "quiz":
        raise AcademyError("not_a_quiz")
    score, _, _, feedback = _grade(lesson, body.answers)
    passed = score >= course.pass_mark
    db.add(Attempt(tenant_id=tenant.id, enrolment_id=e.id, lesson_id=lesson.id, score=score, passed=passed, answers=body.answers, at=utcnow()))
    e.attempts += 1
    e.best_score = max(e.best_score or 0, score)
    cert = None
    if passed:
        complete_lesson(db, e, course, lesson)
        if all(str(l.id) in set(e.completed_lessons or []) for l in course.lessons):
            cert = _complete_course(db, tenant, e, course, member_name)
    db.flush()
    return score, passed, feedback, cert


def _complete_course(db: Session, tenant: Tenant, e: Enrolment, course: Course, member_name: str) -> Certificate | None:
    if e.status == "completed":
        return None
    now = utcnow()
    e.status, e.completed_at, e.progress = "completed", now, 100
    events.emit(db, tenant_id=tenant.id, module_key="academy", kind="academy.completed", summary=f"{member_name} completed {course.title}" + (f" ({e.best_score}%)" if e.best_score is not None else ""),
                detail={"course": course.title, "score": e.best_score}, actor_label=member_name, ref_type="course", ref_id=course.id)
    if not course.certificate:
        return None
    issued = now.date()
    expires = _add_months(issued, course.valid_months) if course.valid_months else None
    serial = f"ENT-{issued:%Y}-{uuid.uuid4().hex[:8].upper()}"
    digest = hashlib.sha256(f"{serial}|{member_name}|{course.title}|{e.best_score or 100}|{issued.isoformat()}|{tenant.id}".encode()).hexdigest()
    cert = Certificate(tenant_id=tenant.id, membership_id=e.membership_id, course_id=course.id, enrolment_id=e.id, serial=serial, course_title=course.title, member_name=member_name, category=course.category,
                       score=e.best_score or 100, issued_on=issued, expires_on=expires, sha256=digest, created_at=now)
    db.add(cert)
    db.flush()
    return cert


def _add_months(d: date, months: int) -> date:
    import calendar
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


# ------------------------------------------------------------------ compliance
def requirement_rows(db: Session, tenant_id: uuid.UUID) -> list[S.ComplianceRow]:
    reqs = db.execute(select(Requirement).where(Requirement.is_active.is_(True))).scalars().all()
    if not reqs:
        return []
    members = db.execute(select(Membership).where(Membership.tenant_id == tenant_id, Membership.status == "active")).scalars().all()
    names = member_names(db, {m.id for m in members})
    courses = {c.id: c for c in db.execute(select(Course).where(Course.id.in_({r.course_id for r in reqs}))).scalars()}
    certs = db.execute(select(Certificate).where(Certificate.revoked_at.is_(None)).order_by(Certificate.issued_on.desc())).scalars().all()
    today = date.today()
    rows: list[S.ComplianceRow] = []
    for r in reqs:
        course = courses.get(r.course_id)
        if course is None:
            continue
        for m in members:
            if r.roles and m.role not in r.roles:
                continue
            mine = [c for c in certs if c.membership_id == m.id and c.course_id == r.course_id]
            last = mine[0] if mine else None
            if last is None:
                state, expires = "never", None
            else:
                expires = last.expires_on or _add_months(last.issued_on, r.frequency_months)
                state = "covered" if expires > today + timedelta(days=60) else ("due_soon" if expires >= today - timedelta(days=r.grace_days) else "overdue")
                if expires < today - timedelta(days=r.grace_days):
                    state = "overdue"
                elif expires < today:
                    state = "due_soon"
            rows.append(S.ComplianceRow(membership_id=m.id, member_name=names.get(m.id, "—"), role=m.role, requirement_id=r.id, requirement_name=r.name, course_id=r.course_id, course_title=course.title,
                                        state=state, last_completed_on=last.issued_on if last else None, expires_on=expires, certificate_serial=last.serial if last else None))
    return sorted(rows, key=lambda x: ({"overdue": 0, "never": 1, "due_soon": 2, "covered": 3}[x.state], x.member_name))


def requirement_out(db: Session, r: Requirement, rows: list[S.ComplianceRow], courses: dict) -> S.RequirementOut:
    mine = [x for x in rows if x.requirement_id == r.id]
    return S.RequirementOut(id=r.id, course_id=r.course_id, course_title=courses.get(r.course_id, "—"), name=r.name, roles=r.roles or [], frequency_months=r.frequency_months, grace_days=r.grace_days,
                            is_active=r.is_active, reference=r.reference, covered=sum(1 for x in mine if x.state == "covered"), due_soon=sum(1 for x in mine if x.state == "due_soon"),
                            overdue=sum(1 for x in mine if x.state in ("overdue", "never")))


def enforce_requirements(db: Session, tenant: Tenant, actor_mid: uuid.UUID | None, actor_label: str) -> int:
    """Create enrolments for anyone overdue or never covered by an active requirement. Idempotent."""
    created = 0
    for row in requirement_rows(db, tenant.id):
        if row.state not in ("overdue", "never"):
            continue
        r = db.get(Requirement, row.requirement_id)
        e = _enrolment(db, row.membership_id, row.course_id, r.id)
        if e and e.status != "completed":
            continue
        if e and e.status == "completed" and row.state != "overdue":
            continue
        assign(db, tenant, S.AssignIn(course_id=row.course_id, membership_ids=[row.membership_id], due_in_days=max(1, r.grace_days or 30)), actor_mid, actor_label, requirement=r)
        created += 1
    return created


def overview(db: Session, tenant_id: uuid.UUID) -> S.OverviewOut:
    today = date.today()
    courses = db.execute(select(Course)).scalars().all()
    enrols = db.execute(select(Enrolment)).scalars().all()
    certs = db.execute(select(Certificate).where(Certificate.revoked_at.is_(None))).scalars().all()
    rows = requirement_rows(db, tenant_id)
    by_cat: dict[str, int] = {}
    cmap = {c.id: c for c in courses}
    for e in enrols:
        if e.status != "completed":
            c = cmap.get(e.course_id)
            if c:
                by_cat[c.category] = by_cat.get(c.category, 0) + 1
    covered = sum(1 for r in rows if r.state in ("covered", "due_soon"))
    return S.OverviewOut(courses=len(courses), enrolments_open=sum(1 for e in enrols if e.status != "completed"),
                         overdue=sum(1 for e in enrols if e.due_on and e.due_on < today and e.status != "completed"),
                         completed_30d=sum(1 for e in enrols if e.completed_at and e.completed_at >= utcnow() - timedelta(days=30)),
                         certificates_valid=sum(1 for c in certs if not c.expires_on or c.expires_on >= today),
                         certificates_expiring_60d=sum(1 for c in certs if c.expires_on and today <= c.expires_on <= today + timedelta(days=60)),
                         compliance_pct=round(covered / len(rows) * 100) if rows else 100, by_category=by_cat)
