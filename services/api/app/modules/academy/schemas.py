from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class QuestionIn(BaseModel):
    id: str | None = None
    text: str = Field(min_length=1, max_length=600)
    options: list[str] = Field(min_length=2, max_length=8)
    correct: list[str] = Field(min_length=1)
    points: int = Field(default=1, ge=1, le=10)


class LessonIn(BaseModel):
    title: str = Field(min_length=1, max_length=220)
    kind: Literal["reading", "video", "quiz"] = "reading"
    minutes: int = Field(default=5, ge=1, le=600)
    body: str | None = None
    video_url: str | None = Field(default=None, max_length=600)
    questions: list[QuestionIn] = []


class CourseIn(BaseModel):
    title: str = Field(min_length=1, max_length=220)
    summary: str | None = None
    category: str = Field(max_length=40)
    level: str = Field(default="All staff", max_length=20)
    pass_mark: int = Field(default=80, ge=1, le=100)
    certificate: bool = True
    valid_months: int | None = Field(default=12, ge=1, le=120)
    lessons: list[LessonIn] = []


class QuestionOut(BaseModel):
    id: str
    text: str
    options: list[str]
    points: int
    correct: list[str] | None = None     # only for authors


class LessonOut(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    order: int
    minutes: int
    body: str | None
    video_url: str | None
    questions: list[QuestionOut]
    completed: bool = False


class CourseOut(BaseModel):
    id: uuid.UUID
    title: str
    summary: str | None
    category: str
    level: str
    minutes: int
    pass_mark: int
    certificate: bool
    valid_months: int | None
    status: str
    lesson_count: int
    is_catalogue: bool
    enrolled: bool = False
    my_status: str | None = None
    my_progress: int = 0
    created_at: datetime


class CourseDetail(CourseOut):
    lessons: list[LessonOut]
    enrolment: "EnrolmentOut | None" = None


class EnrolmentOut(BaseModel):
    id: uuid.UUID
    membership_id: uuid.UUID
    member_name: str | None
    course_id: uuid.UUID
    course_title: str
    category: str
    status: str
    due_on: date | None
    overdue: bool
    progress: int
    best_score: int | None
    attempts: int
    started_at: datetime | None
    completed_at: datetime | None
    requirement_id: uuid.UUID | None


class AssignIn(BaseModel):
    course_id: uuid.UUID
    membership_ids: list[uuid.UUID] = Field(default=[], max_length=200)
    all_staff: bool = False
    due_in_days: int = Field(default=30, ge=1, le=365)


class AttemptIn(BaseModel):
    answers: dict[str, list[str]]        # question id → selected options


class AttemptOut(BaseModel):
    score: int
    passed: bool
    pass_mark: int
    correct: int
    total: int
    enrolment: EnrolmentOut
    certificate_serial: str | None = None
    feedback: list[dict[str, Any]]


class CertificateOut(BaseModel):
    id: uuid.UUID
    serial: str
    member_name: str
    course_title: str
    category: str
    score: int
    issued_on: date
    expires_on: date | None
    expired: bool
    revoked: bool
    sha256: str


class RequirementIn(BaseModel):
    course_id: uuid.UUID
    name: str | None = Field(default=None, max_length=220)
    roles: list[Literal["owner", "admin", "staff"]] = []
    frequency_months: int = Field(default=12, ge=1, le=120)
    grace_days: int = Field(default=30, ge=0, le=365)
    reference: str | None = Field(default=None, max_length=200)


class RequirementOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    course_title: str
    name: str
    roles: list[str]
    frequency_months: int
    grace_days: int
    is_active: bool
    reference: str | None
    covered: int
    due_soon: int
    overdue: int


class ComplianceRow(BaseModel):
    membership_id: uuid.UUID
    member_name: str
    role: str
    requirement_id: uuid.UUID
    requirement_name: str
    course_id: uuid.UUID
    course_title: str
    state: str                 # covered · due_soon · overdue · never
    last_completed_on: date | None
    expires_on: date | None
    certificate_serial: str | None


class OverviewOut(BaseModel):
    courses: int
    enrolments_open: int
    overdue: int
    completed_30d: int
    certificates_valid: int
    certificates_expiring_60d: int
    compliance_pct: int
    by_category: dict[str, int]


class MyLearning(BaseModel):
    enrolments: list[EnrolmentOut]
    certificates: list[CertificateOut]
    compliance: list[ComplianceRow]
