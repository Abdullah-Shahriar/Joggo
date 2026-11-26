from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Final
import uuid

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Response
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
import jwt

from app.config import Settings, get_settings
from app.errors import AppError, ErrorCode

ACCESS_TOKEN_TTL_MINUTES: Final[int] = 15
REFRESH_TOKEN_TTL_DAYS: Final[int] = 7
JWT_ALGORITHM: Final[str] = "HS256"

ACCESS_COOKIE_NAME: Final[str] = "access_token"
REFRESH_COOKIE_NAME: Final[str] = "refresh_token"

_password_hasher: Final[PasswordHasher] = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# Precomputed valid argon2id hash used to equalize timing on unknown-email logins (rules.md S8).
DUMMY_PASSWORD_HASH: Final[str] = _password_hasher.hash("DummyPasswordForTiming123")


@dataclass(frozen=True)
class AccessTokenClaims:
    sub: uuid.UUID
    sid: uuid.UUID
    tv: int


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    full_name: str


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def validate_password_strength(password: str) -> bool:
    """Rules.md S1: min length 10, at least one letter and one digit."""
    if len(password) < 10:
        return False
    has_letter = any(ch.isalpha() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    return has_letter and has_digit


def generate_refresh_token() -> str:
    """Rules.md S2: random 256-bit value."""
    return secrets.token_urlsafe(32)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_access_token(
    *,
    user_id: uuid.UUID,
    session_family_id: uuid.UUID,
    token_version: int,
    settings: Settings | None = None,
) -> str:
    cfg = settings or get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "sid": str(session_family_id),
        "tv": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, cfg.JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings | None = None) -> AccessTokenClaims:
    cfg = settings or get_settings()
    try:
        decoded = jwt.decode(token, cfg.JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AppError(ErrorCode.TOKEN_EXPIRED, 401, "Your session has expired. Please sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise AppError(ErrorCode.UNAUTHENTICATED, 401, "Authentication required.") from exc

    try:
        sub = uuid.UUID(str(decoded["sub"]))
        sid = uuid.UUID(str(decoded["sid"]))
        tv = int(decoded["tv"])
    except (KeyError, ValueError, TypeError) as exc:
        raise AppError(ErrorCode.UNAUTHENTICATED, 401, "Authentication required.") from exc

    return AccessTokenClaims(sub=sub, sid=sid, tv=tv)


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    secure = cfg.ENV == "prod"
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=ACCESS_TOKEN_TTL_MINUTES * 60,
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/auth",
        max_age=REFRESH_TOKEN_TTL_DAYS * 24 * 60 * 60,
    )


def clear_auth_cookies(response: Response, settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    secure = cfg.ENV == "prod"
    response.delete_cookie(
        key=ACCESS_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def verify_google_credential(credential: str, settings: Settings | None = None) -> GoogleIdentity:
    cfg = settings or get_settings()
    if not cfg.GOOGLE_CLIENT_ID:
        raise AppError(ErrorCode.GOOGLE_TOKEN_INVALID, 401, "Google sign-in is not configured.")
    try:
        info = google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            cfg.GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        raise AppError(ErrorCode.GOOGLE_TOKEN_INVALID, 401, "Invalid Google sign-in token.") from exc

    if not info.get("email_verified"):
        raise AppError(ErrorCode.GOOGLE_TOKEN_INVALID, 401, "Google account email must be verified.")

    sub = str(info.get("sub") or "").strip()
    email = str(info.get("email") or "").strip().lower()
    full_name = str(info.get("name") or email.split("@")[0]).strip()[:80]
    if not sub or not email:
        raise AppError(ErrorCode.GOOGLE_TOKEN_INVALID, 401, "Invalid Google sign-in token.")

    return GoogleIdentity(sub=sub, email=email, full_name=full_name or "Clinician")
