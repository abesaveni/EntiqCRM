from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


# ------------------------------------------------------------------ auth
class PaymentMethodIn(BaseModel):
    """Stripe Elements produces a payment_method id; until Stripe is wired, the client sends the display token."""
    payment_method_id: str | None = None
    brand: str | None = Field(default=None, max_length=20)
    last4: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")


class SignUpIn(BaseModel):
    practice_name: str = Field(min_length=2, max_length=200)
    abn: str | None = Field(default=None, max_length=20)
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(max_length=200)  # length/complexity enforced by security.password_problems → structured 422
    payment_method: PaymentMethodIn | None = None   # optional while REQUIRE_CARD_AT_SIGNUP is off

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower().strip()


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    tenant_id: uuid.UUID | None = None

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower().strip()


class RefreshIn(BaseModel):
    refresh_token: str


class SwitchTenantIn(BaseModel):
    tenant_id: uuid.UUID


class AcceptInviteIn(BaseModel):
    token: str
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(max_length=200)  # length/complexity enforced by security.password_problems → structured 422


class TenantChoice(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str
    status: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime


class LoginOut(BaseModel):
    requires_tenant_selection: bool = False
    tenants: list[TenantChoice] = []
    tokens: TokenPair | None = None
    session: SessionOut | None = None


# ------------------------------------------------------------------ session / me
class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_operator: bool
    email_verified: bool


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    abn: str | None
    timezone: str
    status: str
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    card_on_file: bool
    card_brand: str | None
    card_last4: str | None
    created_at: datetime


class SubscriptionOut(BaseModel):
    module_key: str
    status: str
    seats: int | None
    started_at: datetime
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    required_by: str | None


class PricingOut(BaseModel):
    base_plan_cents: int
    gst_rate_bps: int
    base_plan_inc_gst_cents: int
    currency: str = "AUD"
    trial_days: int
    require_card: bool = True        # false while testing: the signup card step can be skipped
    free_mode: bool = False          # true when the base plan is $0, so the trial converts without a charge


class SessionOut(BaseModel):
    user: UserOut
    tenant: TenantOut
    role: str
    granted_modules: list[str]
    permissions: list[str]
    subscriptions: list[SubscriptionOut]
    entitlements: dict[str, bool]
    read_only: bool
    pricing: PricingOut


# ------------------------------------------------------------------ tenant / subscriptions
class TenantPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    abn: str | None = Field(default=None, max_length=20)
    timezone: str | None = Field(default=None, max_length=64)


class SubscribeIn(BaseModel):
    module_key: str = Field(min_length=2, max_length=32)
    seats: int | None = Field(default=None, ge=1, le=10_000)


class SubscribeOut(BaseModel):
    added: list[str]
    subscriptions: list[SubscriptionOut]
    entitlements: dict[str, bool]


class ModuleCatalogueItem(BaseModel):
    manifest: dict[str, Any]
    entitled: bool
    subscription: SubscriptionOut | None
    purchasable: bool
    base: bool


# ------------------------------------------------------------------ users
class MemberOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    status: str
    job_title: str | None
    modules: list[str]
    joined_at: datetime | None
    last_login_at: datetime | None


class InviteIn(BaseModel):
    email: EmailStr
    role: str = Field(default="staff", pattern=r"^(admin|staff)$")
    modules: list[str] = []
    job_title: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower().strip()


class InviteOut(BaseModel):
    invitation_id: uuid.UUID
    email: str
    expires_at: datetime
    accept_url: str | None  # returned in non-production so the flow can be exercised without SMTP


class GrantsPatch(BaseModel):
    modules: list[str]


class MemberPatch(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(owner|admin|staff)$")
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")
    job_title: str | None = Field(default=None, max_length=120)


# ------------------------------------------------------------------ audit / dev
class AuditOut(BaseModel):
    id: int
    action: str
    actor_user_id: uuid.UUID | None
    target_type: str | None
    target_id: str | None
    detail: dict[str, Any] | None
    created_at: datetime
    hash: str


class LifecycleIn(BaseModel):
    status: str = Field(pattern=r"^(trialing|active|past_due|suspended|cancelled|retained)$")
    reason: str | None = Field(default=None, max_length=500)
