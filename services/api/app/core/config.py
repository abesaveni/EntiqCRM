"""
Settings for the EnTIQ platform spine.

Loaded from the environment, then from the repo-root `.env.local` (git-ignored).
Production refuses to boot on any dev-only configuration — a platform that starts
and then quietly runs with a placeholder secret or SQLite is worse than one that
does not start. (Same posture as GrowKyc and EntiqTraining.)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]  # services/api/app/core/config.py -> repo root
_INSECURE_SECRETS = {"", "changeme", "change_me", "secret", "your-secret-key-change-in-production", "dev"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env.local", REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    ENV: Literal["development", "test", "staging", "production"] = "development"
    APP_NAME: str = "EnTIQ API"
    APP_PUBLIC_URL: str = "http://localhost:5180"
    ALLOWED_ORIGINS: str = "http://localhost:5180,http://127.0.0.1:5180"

    # Data
    DATABASE_URL: str = f"sqlite:///{(REPO_ROOT / 'services' / 'api' / 'entiq_dev.db').as_posix()}"
    SQL_ECHO: bool = False
    REDIS_URL: str = "redis://localhost:56379/0"

    # Identity
    SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    LOGIN_MAX_FAILURES: int = 8
    LOGIN_LOCKOUT_MINUTES: int = 15
    MIN_PASSWORD_LENGTH: int = 12

    # Commercial (decided 19 Sep 2026)
    TRIAL_DAYS: int = 15
    # Testing: with the base price at 0 the trial converts free, and the card can be skipped at signup.
    # Both are refused in production by verify_production_safety().
    REQUIRE_CARD_AT_SIGNUP: bool = True
    BASE_PLAN_PRICE_CENTS: int = 9900          # $99.00 ex GST
    GST_RATE_BPS: int = 1000                   # 10%
    PAST_DUE_GRACE_DAYS: int = 7
    SUSPENDED_TO_CANCELLED_DAYS: int = 30
    EXPORT_WINDOW_DAYS: int = 30

    # Module registry — shared with the frontend
    MANIFESTS_PATH: str = str(REPO_ROOT / "packages" / "modules" / "manifests.json")

    # Documents
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    STORAGE_DIR: str = str(REPO_ROOT / "services" / "api" / "storage")
    AWS_REGION: str = "ap-southeast-2"
    AWS_S3_BUCKET: str = ""
    MAX_UPLOAD_MB: int = 25
    CLAMAV_HOST: str = ""            # clamd TCP host; REQUIRED in production (uploads are refused without a scan)
    CLAMAV_PORT: int = 3310

    # Billing
    BILLING_MODE: Literal["simulate", "stripe"] = "simulate"   # simulate: trial converts to active with a recorded, uncharged event

    # Integrations (optional; features degrade when absent)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_BASE_MONTHLY: str = ""
    STRIPE_TIMEOUT: str = "30"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "no-reply@entiq.com.au"
    SMTP_USE_TLS: bool = True
    # Real delivery is opt-in outside production so a dev box holding live SMTP creds never emails anyone by accident.
    EMAIL_DELIVERY_ENABLED: bool = False
    OPENAI_API_KEY: str = ""

    # Verify providers (live when set; simulation drivers otherwise)
    # Ledger providers (Workpapers): "auto" uses Xero when credentials exist, "simulate" forces the simulation driver.
    LEDGER_PROVIDER_MODE: str = "auto"
    XERO_CLIENT_ID: str = ""
    XERO_CLIENT_SECRET: str = ""
    XERO_REDIRECT_URI: str = "http://localhost:5180/hq/integrations/xero/callback"
    XERO_TIMEOUT: str = "30"
    # Verify providers: "auto" uses live drivers when keys are present, "simulate" forces the simulation drivers (tests, demos).
    VERIFY_PROVIDER_MODE: str = "auto"
    DIDIT_API_KEY: str = ""
    DIDIT_BASE_URL: str = "https://verification.didit.me"
    DIDIT_WEBHOOK_SECRET: str = ""
    DIDIT_WORKFLOW_INDIVIDUAL: str = ""
    DIDIT_WORKFLOW_KYB: str = ""
    OPENSANCTIONS_API_KEY: str = ""
    OPENSANCTIONS_BASE_URL: str = "https://api.opensanctions.org"
    OPENSANCTIONS_DATASET: str = "default"
    OPENSANCTIONS_THRESHOLD: str = "0.7"
    OPENSANCTIONS_TIMEOUT: str = "20"

    RATE_LIMIT_DEFAULT: str = "300/minute"
    RATE_LIMIT_AUTH: str = "20/minute"

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def _strip(cls, v: str) -> str:
        return ",".join(o.strip() for o in v.split(",") if o.strip())

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def is_test(self) -> bool:
        return self.ENV == "test"

    @property
    def origins(self) -> list[str]:
        return self.ALLOWED_ORIGINS.split(",") if self.ALLOWED_ORIGINS else []

    @property
    def free_mode(self) -> bool:
        """Nothing to charge: the base plan is $0, so the trial converts without a payment."""
        return self.BASE_PLAN_PRICE_CENTS <= 0

    @property
    def stripe_enabled(self) -> bool:
        return bool(self.STRIPE_SECRET_KEY)

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USERNAME)

    @property
    def email_delivery_active(self) -> bool:
        return self.smtp_enabled and (self.EMAIL_DELIVERY_ENABLED or self.is_production)


settings = Settings()


def verify_production_safety() -> list[str]:
    """Return the list of fatal misconfigurations. In production, any entry aborts boot."""
    problems: list[str] = []
    if settings.SECRET_KEY.strip().lower() in _INSECURE_SECRETS:
        problems.append("SECRET_KEY is unset or a known placeholder")
    elif len(settings.SECRET_KEY) < 32:
        problems.append("SECRET_KEY is shorter than 32 characters")
    if settings.is_production:
        if "*" in settings.origins or any(o.startswith("http://") for o in settings.origins):
            problems.append("ALLOWED_ORIGINS contains '*' or an http:// origin")
        if settings.DATABASE_URL.startswith("sqlite"):
            problems.append("DATABASE_URL is SQLite")
        if settings.SQL_ECHO:
            problems.append("SQL_ECHO is enabled")
        if not settings.APP_PUBLIC_URL.startswith("https://"):
            problems.append("APP_PUBLIC_URL is not https")
        if not settings.CLAMAV_HOST:
            problems.append("CLAMAV_HOST is not set — anti-virus scanning is required for uploads in production")
        if settings.LEDGER_PROVIDER_MODE == "simulate":
            problems.append("LEDGER_PROVIDER_MODE is 'simulate' — production workpapers must read a real ledger")
        if settings.VERIFY_PROVIDER_MODE == "simulate":
            problems.append("VERIFY_PROVIDER_MODE is 'simulate' — production must use live identity/screening providers")
        if settings.DIDIT_API_KEY and not settings.DIDIT_WEBHOOK_SECRET:
            problems.append("DIDIT_WEBHOOK_SECRET is unset while DIDIT_API_KEY is set — the Verify webhook would accept unsigned callbacks")
        if settings.BASE_PLAN_PRICE_CENTS <= 0:
            problems.append("BASE_PLAN_PRICE_CENTS is 0 — production must charge for the base plan")
        if not settings.REQUIRE_CARD_AT_SIGNUP:
            problems.append("REQUIRE_CARD_AT_SIGNUP is false — production must capture a card at signup")
        if settings.BILLING_MODE == "simulate":
            problems.append("BILLING_MODE is 'simulate' — production must charge through Stripe")
    return problems


def enforce_production_safety() -> None:
    problems = verify_production_safety()
    if settings.is_production and problems:
        for p in problems:
            print(f"FATAL: {p}", file=sys.stderr)
        sys.exit(1)
    if not settings.is_production and not settings.SECRET_KEY:
        # Dev convenience: a per-process random key. Tokens do not survive a restart.
        import secrets as _s
        settings.SECRET_KEY = _s.token_hex(32)
        print("WARNING: SECRET_KEY not set — using a random key for this process only.", file=sys.stderr)
