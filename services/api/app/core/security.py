"""Password hashing, JWT issue/verify, password policy. bcrypt is used directly (no passlib)."""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ passwords
def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


_POLICY = [
    (re.compile(r"[A-Z]"), "an uppercase letter"),
    (re.compile(r"[a-z]"), "a lowercase letter"),
    (re.compile(r"\d"), "a digit"),
    (re.compile(r"[^A-Za-z0-9]"), "a symbol"),
]


def password_problems(raw: str) -> list[str]:
    problems = []
    if len(raw) < settings.MIN_PASSWORD_LENGTH:
        problems.append(f"at least {settings.MIN_PASSWORD_LENGTH} characters")
    for rx, label in _POLICY:
        if not rx.search(raw):
            problems.append(label)
    return problems


# ------------------------------------------------------------------ tokens
def _b64hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_opaque_token() -> tuple[str, str]:
    """Return (raw, sha256) — store only the hash."""
    raw = secrets.token_urlsafe(48)
    return raw, _b64hash(raw)


def hash_token(raw: str) -> str:
    return _b64hash(raw)


def issue_access_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str, is_operator: bool) -> tuple[str, str, datetime]:
    """Return (token, jti, expires_at). Tenant travels as a claim — the principal decides the tenant."""
    jti = uuid.uuid4().hex
    exp = utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "role": role,
        "op": is_operator,
        "jti": jti,
        "iat": int(utcnow().timestamp()),
        "exp": int(exp.timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM), jti, exp


class TokenError(Exception):
    pass


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], options={"require": ["sub", "tid", "exp", "jti"]})
    except jwt.ExpiredSignatureError as e:
        raise TokenError("expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError("invalid") from e
    if payload.get("typ") != "access":
        raise TokenError("wrong token type")
    return payload
