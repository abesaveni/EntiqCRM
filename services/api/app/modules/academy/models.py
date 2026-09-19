"""
EnTIQ Academy (module 15) — prove staff competency, compliance training and annual refreshers with
regulator-ready evidence. Ported from EntiqTraining (courses → lessons → quiz → enrolment →
certificate), re-keyed from its own user table to EnTIQ memberships, and extended with the piece the
blueprint needs: per-role compliance requirements with due dates and an evidence register.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Timestamps, UTCDateTime, UuidPk

CATEGORIES = ("AML/CTF", "Tax", "Audit", "Privacy", "Cyber", "Professional", "Software", "Induction")
ENROLMENT_STATUSES = ("not_started", "in_progress", "completed", "expired")


class Course(Base, UuidPk, Timestamps):
    __tablename__ = "academy_courses"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True)  # NULL = EnTIQ catalogue course, shared
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(20), default="All staff", nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    pass_mark: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    certificate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    valid_months: Mapped[int | None] = mapped_column(Integer)          # certificate expiry; None = never expires
    status: Mapped[str] = mapped_column(String(16), default="published", nullable=False, index=True)
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))

    lessons: Mapped[list["Lesson"]] = relationship(back_populates="course", cascade="all, delete-orphan", order_by="Lesson.order")


class Lesson(Base, UuidPk, Timestamps):
    __tablename__ = "academy_lessons"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("academy_courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), default="reading", nullable=False)   # reading · video · quiz
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(String(600))
    questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)   # quiz lessons: [{id,text,options,correct:[...],points}]

    course: Mapped[Course] = relationship(back_populates="lessons")


class Enrolment(Base, UuidPk, Timestamps):
    __tablename__ = "academy_enrolments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("academy_courses.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("academy_requirements.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="not_started", nullable=False, index=True)
    due_on: Mapped[date | None] = mapped_column(Date, index=True)
    completed_lessons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_score: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    assigned_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))

    __table_args__ = (Index("ix_academy_enrolments_member_course", "membership_id", "course_id", "requirement_id"),)


class Attempt(Base, UuidPk):
    __tablename__ = "academy_attempts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    enrolment_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("academy_enrolments.id", ondelete="CASCADE"), nullable=False, index=True)
    lesson_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("academy_lessons.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answers: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class Certificate(Base, UuidPk):
    __tablename__ = "academy_certificates"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("academy_courses.id", ondelete="SET NULL"), index=True)
    enrolment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("academy_enrolments.id", ondelete="SET NULL"))
    serial: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    course_title: Mapped[str] = mapped_column(String(220), nullable=False)
    member_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_on: Mapped[date] = mapped_column(Date, nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date, index=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)   # over serial+member+course+score+issued, for verification
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class Requirement(Base, UuidPk, Timestamps):
    """A compliance obligation: this course, for these roles, every N months."""
    __tablename__ = "academy_requirements"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("academy_courses.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(220), nullable=False)
    roles: Mapped[list] = mapped_column(JSON, default=list, nullable=False)     # [] = everyone; else owner/admin/staff
    frequency_months: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    grace_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200))     # e.g. "AML/CTF Act s.207 — ongoing training"
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
