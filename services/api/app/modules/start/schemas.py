from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

EntityType = Literal["Company", "Trust", "Individual", "Partnership", "SMSF", "Other"]


# ------------------------------------------------------------------ catalogue
class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=2, max_length=40)
    description: str | None = None
    basis: Literal["fixed", "monthly", "quarterly", "annual", "hourly"] = "annual"
    amount_cents: int = Field(ge=0)
    gst: bool = True
    entity_types: list[EntityType] = []
    is_active: bool = True
    sort: int = 0


class ServiceOut(ServiceIn):
    id: uuid.UUID


# ------------------------------------------------------------------ stage payloads (what the prospect submits)
class EntityDetailsIn(BaseModel):
    legal_name: str = Field(min_length=1, max_length=300)
    trading_name: str | None = Field(default=None, max_length=300)
    entity_type: EntityType
    abn: str | None = Field(default=None, max_length=20)
    acn: str | None = Field(default=None, max_length=20)
    tax_residency: Literal["australia", "foreign", "dual"] = "australia"
    gst_registered: bool | None = None
    industry: str | None = Field(default=None, max_length=120)
    address_line1: str | None = None
    suburb: str | None = None
    state: str | None = Field(default=None, max_length=10)
    postcode: str | None = Field(default=None, max_length=10)
    contact_name: str = Field(min_length=1, max_length=200)
    contact_email: EmailStr
    contact_phone: str | None = Field(default=None, max_length=40)


QUESTIONNAIRE: list[dict[str, Any]] = [
    {"key": "business_description", "label": "What does the business do?", "type": "text", "required": True},
    {"key": "turnover_band", "label": "Annual turnover", "type": "select", "options": ["Under $75k", "$75k–$250k", "$250k–$1m", "$1m–$5m", "$5m–$20m", "Over $20m"], "required": True},
    {"key": "employees_band", "label": "Employees", "type": "select", "options": ["None", "1–4", "5–19", "20–49", "50+"], "required": True},
    {"key": "gst_registered", "label": "Registered for GST?", "type": "bool", "required": True},
    {"key": "payroll", "label": "Do you run payroll?", "type": "bool", "required": True},
    {"key": "software", "label": "Accounting software", "type": "select", "options": ["Xero", "MYOB", "QuickBooks", "Reckon", "Spreadsheets", "None", "Other"], "required": True},
    {"key": "current_accountant", "label": "Current accountant (if any)", "type": "text", "required": False},
    {"key": "reason_for_change", "label": "Why are you looking to change or engage now?", "type": "text", "required": False},
    {"key": "lodgements_outstanding", "label": "Any overdue lodgements (BAS, tax returns)?", "type": "bool", "required": True},
    {"key": "goals", "label": "What would a great first year with us look like?", "type": "text", "required": False},
]


class QuestionnaireIn(BaseModel):
    answers: dict[str, Any]


DOCUMENT_REQUESTS: dict[str, list[tuple[str, str, bool]]] = {
    # entity type → (key, label, required)
    "Company": [("prior_financials", "Last financial statements", True), ("prior_tax_return", "Last company tax return", True), ("asic_extract", "ASIC current company extract", True), ("bank_statements", "Recent bank statements (3 months)", False)],
    "Trust": [("trust_deed", "Trust deed (incl. variations)", True), ("prior_financials", "Last financial statements", True), ("prior_tax_return", "Last trust tax return", True)],
    "SMSF": [("trust_deed", "SMSF trust deed", True), ("prior_financials", "Last financial statements", True), ("investment_strategy", "Investment strategy", True), ("prior_tax_return", "Last SMSF annual return", False)],
    "Partnership": [("partnership_agreement", "Partnership agreement", True), ("prior_tax_return", "Last partnership tax return", True), ("prior_financials", "Last financial statements", False)],
    "Individual": [("prior_tax_return", "Last individual tax return", True), ("income_statements", "Income statements / PAYG summaries", False)],
    "Other": [("prior_financials", "Last financial statements", True), ("prior_tax_return", "Last tax return", True)],
}


class PartyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: Literal["Director", "Secretary", "Shareholder", "Trustee", "Beneficiary", "Appointor", "Partner", "Member", "Owner", "Other"]
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    ownership_pct: int | None = Field(default=None, ge=0, le=100)
    is_beneficial_owner: bool = False


class RelatedPartiesIn(BaseModel):
    parties: list[PartyIn] = Field(min_length=1, max_length=30)
    ownership_complete: bool = Field(default=True, description="Prospect confirms all owners ≥25% are listed")


class ServiceSelectionIn(BaseModel):
    service_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)


class ProposalLine(BaseModel):
    service_id: uuid.UUID | None = None
    name: str
    basis: str
    amount_cents: int = Field(ge=0)
    gst: bool = True


class ProposalIssueIn(BaseModel):
    lines: list[ProposalLine] = Field(min_length=1)
    terms: str | None = Field(default=None, max_length=8000)
    valid_days: int = Field(default=30, ge=1, le=180)


class ProposalAcceptIn(BaseModel):
    accepted_by_name: str = Field(min_length=1, max_length=200)
    accept: bool


class EngagementPrepIn(BaseModel):
    document_id: uuid.UUID
    title: str | None = Field(default=None, max_length=300)
    message: str | None = Field(default=None, max_length=2000)
    require_identity: bool = False


class MandateIn(BaseModel):
    method: Literal["direct_debit", "card", "invoice"]
    reference: str | None = Field(default=None, max_length=120)
    account_name: str | None = Field(default=None, max_length=200)
    accepted_terms: bool


class AcceptanceIn(BaseModel):
    partner_signoff: bool
    margin_ok: bool
    risk_signoff: bool
    notes: str | None = Field(default=None, max_length=2000)


class WithdrawIn(BaseModel):
    reason: str = Field(min_length=2, max_length=300)


# ------------------------------------------------------------------ orchestration
class OnboardingIn(BaseModel):
    client_id: uuid.UUID | None = None
    # or create the prospect on the spot:
    prospect_name: str | None = Field(default=None, max_length=300)
    entity_type: EntityType = "Company"
    contact_first_name: str | None = Field(default=None, max_length=100)
    contact_last_name: str | None = Field(default=None, max_length=100)
    contact_email: EmailStr | None = None
    owner_membership_id: uuid.UUID | None = None
    send_invitation: bool = True
    invite_valid_days: int = Field(default=30, ge=1, le=120)
    notes: str | None = None


class StageOut(BaseModel):
    number: int
    key: str
    name: str
    actor: str
    description: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    completed_by: str | None
    meta: dict[str, Any]


class GateOut(BaseModel):
    gate: str
    label: str
    status: str            # Passed · Pending · Failed · Error · Not run
    simulated: bool
    detail: str | None
    checked_at: datetime | None


class OnboardingOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    client_type: str
    client_stage: str
    primary_contact_name: str | None
    primary_contact_email: str | None
    owner_name: str | None
    status: str
    current_stage: int
    progress_pct: int
    channel: str
    invited_at: datetime | None
    opened_at: datetime | None
    activated_at: datetime | None
    withdrawn_at: datetime | None
    withdraw_reason: str | None
    token_expires_at: datetime | None
    proposal_total_cents: int | None
    sign_agreement_id: uuid.UUID | None
    risk_rating: str | None
    created_at: datetime
    updated_at: datetime


class OnboardingDetail(OnboardingOut):
    stages: list[StageOut]
    gates: list[GateOut]
    data: dict[str, Any]
    invite_url: str | None = None      # only present right after (re)issuing an invitation
    notes: str | None


class OverviewOut(BaseModel):
    active: int
    awaiting_prospect: int
    awaiting_practice: int
    activated_30d: int
    withdrawn_30d: int
    by_stage: dict[str, int]
    median_days_to_activate: float | None


# ------------------------------------------------------------------ public (prospect)
class PublicView(BaseModel):
    practice_name: str
    prospect_name: str
    contact_name: str | None
    status: str
    current_stage: int
    stages: list[StageOut]
    data: dict[str, Any]
    questionnaire: list[dict[str, Any]]
    document_requests: list[dict[str, Any]]
    services: list[ServiceOut]
    proposal: dict[str, Any] | None
    expires_at: datetime | None
