from datetime import datetime, timedelta, timezone
import math
import re
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_client_ip, trigger_session_wipe
from app.errors import AppError, ErrorCode
from app.models.audit import AuditOutcome
from app.models.session import SessionRecord
from app.models.user import User, UserRole, UserStatus
from app.ratelimit import limiter
from app.schemas.auth import (
    AuthSessionResponse,
    AuthUserResponse,
    GoogleAuthRequest,
    LoginRequest,
    MessageResponse,
    SignupRequest,
)
from app.security import (
    ACCESS_COOKIE_NAME,
    DUMMY_PASSWORD_HASH,
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_TTL_DAYS,
    clear_auth_cookies,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    set_auth_cookies,
    sha256_hex,
    validate_password_strength,
    verify_google_credential,
    verify_password,
)
from app.services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


def serialize_user(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        status=user.status.value,
        restricted_reason=user.restricted_reason,
        has_password=user.password_hash is not None,
        has_google=user.google_sub is not None,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def _normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if not EMAIL_REGEX.match(email):
        raise AppError(ErrorCode.VALIDATION_ERROR, 422, "Please enter a valid email address.")
    return email


def _create_session_and_set_cookies(
    *,
    db: Session,
    user: User,
    request: Request,
    response: Response,
    family_id: uuid.UUID | None = None,
) -> SessionRecord:
    now = datetime.now(timezone.utc)
    fam_id = family_id or uuid.uuid4()
    raw_refresh = generate_refresh_token()
    session_row = SessionRecord(
        user_id=user.id,
        family_id=fam_id,
        token_hash=sha256_hex(raw_refresh),
        expires_at=now + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
        ip=get_client_ip(request),
        last_used_at=now,
    )
    db.add(session_row)
    db.flush()

    access_jwt = create_access_token(
        user_id=user.id,
        session_family_id=fam_id,
        token_version=user.token_version,
    )
    set_auth_cookies(response, access_token=access_jwt, refresh_token=raw_refresh)
    return session_row


@router.post("/signup", response_model=AuthSessionResponse, status_code=201)
@limiter.limit("10/minute")
def signup(
    request: Request,
    payload: SignupRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthSessionResponse:
    email = _normalize_email(payload.email)
    full_name = payload.full_name.strip()
    if len(full_name) < 2:
        raise AppError(ErrorCode.VALIDATION_ERROR, 422, "Full name must be at least 2 characters.")

    if not validate_password_strength(payload.password):
        raise AppError(
            ErrorCode.WEAK_PASSWORD,
            422,
            "Password must be at least 10 characters and include a letter and a digit.",
        )

    existing = db.execute(select(User.id).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise AppError(ErrorCode.EMAIL_TAKEN, 409, "An account with this email already exists.")

    now = datetime.now(timezone.utc)
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=full_name,
        role=UserRole.doctor,
        status=UserStatus.active,
        last_login_at=now,
    )
    db.add(user)
    db.flush()

    _create_session_and_set_cookies(db=db, user=user, request=request, response=response)
    audit.record(
        db,
        action="AUTH_SIGNUP",
        outcome=AuditOutcome.allowed,
        actor=user,
        resource_type="user",
        resource_id=str(user.id),
        ip=get_client_ip(request),
    )
    db.commit()
    return AuthSessionResponse(user=serialize_user(user))


@router.post("/login", response_model=AuthSessionResponse)
@limiter.limit("10/minute")
def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthSessionResponse:
    email = payload.email.strip().lower()
    ip = get_client_ip(request)
    now = datetime.now(timezone.utc)

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        verify_password(DUMMY_PASSWORD_HASH, payload.password)
        audit.record(
            db,
            action="AUTH_LOGIN_FAILED",
            outcome=AuditOutcome.denied,
            resource_type="auth",
            ip=ip,
            metadata={"reason": "invalid_credentials"},
        )
        db.commit()
        raise AppError(ErrorCode.INVALID_CREDENTIALS, 401, "Invalid email or password.")

    if user.locked_until is not None and user.locked_until > now:
        mins_left = max(1, math.ceil((user.locked_until - now).total_seconds() / 60))
        audit.record(
            db,
            action="AUTH_LOGIN_FAILED",
            outcome=AuditOutcome.denied,
            actor=user,
            resource_type="user",
            resource_id=str(user.id),
            ip=ip,
            metadata={"reason": "account_locked"},
        )
        db.commit()
        raise AppError(
            ErrorCode.ACCOUNT_LOCKED,
            423,
            f"Account temporarily locked after failed sign-in attempts. Try again in {mins_left} minute(s).",
        )

    password_ok = (
        verify_password(user.password_hash, payload.password)
        if user.password_hash is not None
        else (verify_password(DUMMY_PASSWORD_HASH, payload.password) and False)
    )
    if not password_ok:
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            audit.record(
                db,
                action="AUTH_LOCKED",
                outcome=AuditOutcome.denied,
                actor=user,
                resource_type="user",
                resource_id=str(user.id),
                ip=ip,
                metadata={"failed_attempts": user.failed_login_count},
            )
            db.commit()
            raise AppError(
                ErrorCode.ACCOUNT_LOCKED,
                423,
                f"Account temporarily locked after failed sign-in attempts. Try again in {LOCKOUT_MINUTES} minute(s).",
            )
        audit.record(
            db,
            action="AUTH_LOGIN_FAILED",
            outcome=AuditOutcome.denied,
            actor=user,
            resource_type="user",
            resource_id=str(user.id),
            ip=ip,
            metadata={"failed_attempts": user.failed_login_count},
        )
        db.commit()
        raise AppError(ErrorCode.INVALID_CREDENTIALS, 401, "Invalid email or password.")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    _create_session_and_set_cookies(db=db, user=user, request=request, response=response)
    audit.record(
        db,
        action="AUTH_LOGIN_SUCCESS",
        outcome=AuditOutcome.allowed,
        actor=user,
        resource_type="user",
        resource_id=str(user.id),
        ip=ip,
    )
    db.commit()
    return AuthSessionResponse(user=serialize_user(user))


@router.post("/google", response_model=AuthSessionResponse)
@limiter.limit("10/minute")
def google_login(
    request: Request,
    payload: GoogleAuthRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthSessionResponse:
    identity = verify_google_credential(payload.credential)
    ip = get_client_ip(request)
    now = datetime.now(timezone.utc)

    user = db.execute(select(User).where(User.google_sub == identity.sub)).scalar_one_or_none()
    if user is None:
        by_email = db.execute(select(User).where(User.email == identity.email)).scalar_one_or_none()
        if by_email is not None:
            if by_email.google_sub is not None and by_email.google_sub != identity.sub:
                raise AppError(ErrorCode.GOOGLE_TOKEN_INVALID, 401, "Google account does not match existing profile.")
            by_email.google_sub = identity.sub
            user = by_email
        else:
            user = User(
                email=identity.email,
                password_hash=None,
                google_sub=identity.sub,
                full_name=identity.full_name,
                role=UserRole.doctor,
                status=UserStatus.active,
            )
            db.add(user)
            db.flush()

    if user.locked_until is not None and user.locked_until > now:
        mins_left = max(1, math.ceil((user.locked_until - now).total_seconds() / 60))
        raise AppError(
            ErrorCode.ACCOUNT_LOCKED,
            423,
            f"Account temporarily locked. Try again in {mins_left} minute(s).",
        )

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    _create_session_and_set_cookies(db=db, user=user, request=request, response=response)
    audit.record(
        db,
        action="AUTH_GOOGLE_LOGIN",
        outcome=AuditOutcome.allowed,
        actor=user,
        resource_type="user",
        resource_id=str(user.id),
        ip=ip,
    )
    db.commit()
    return AuthSessionResponse(user=serialize_user(user))


@router.post("/refresh", response_model=AuthSessionResponse)
@limiter.limit("10/minute")
def refresh_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthSessionResponse:
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh:
        raise AppError(ErrorCode.UNAUTHENTICATED, 401, "Authentication required.")

    ip = get_client_ip(request)
    now = datetime.now(timezone.utc)
    token_hash = sha256_hex(raw_refresh)

    session_row = db.execute(
        select(SessionRecord).where(SessionRecord.token_hash == token_hash).with_for_update()
    ).scalar_one_or_none()
    if session_row is None:
        clear_auth_cookies(response)
        raise AppError(ErrorCode.UNAUTHENTICATED, 401, "Authentication required.")

    user = db.get(User, session_row.user_id)
    if user is None:
        clear_auth_cookies(response)
        raise AppError(ErrorCode.UNAUTHENTICATED, 401, "Authentication required.")

    # Rules.md S2: Reuse of a revoked refresh token revokes the entire session family and wipes its vault.
    if session_row.revoked_at is not None:
        db.execute(
            update(SessionRecord)
            .where(
                SessionRecord.family_id == session_row.family_id,
                SessionRecord.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        audit.record(
            db,
            action="AUTH_REFRESH_REUSE_DETECTED",
            outcome=AuditOutcome.denied,
            actor=user,
            resource_type="session_family",
            resource_id=str(session_row.family_id),
            ip=ip,
        )
        db.commit()
        trigger_session_wipe(session_row.family_id)
        clear_auth_cookies(response)
        raise AppError(
            ErrorCode.SESSION_REVOKED,
            401,
            "Session revoked due to suspicious token reuse. Please sign in again.",
        )

    if session_row.expires_at <= now:
        session_row.revoked_at = now
        db.commit()
        clear_auth_cookies(response)
        raise AppError(ErrorCode.TOKEN_EXPIRED, 401, "Session expired. Please sign in again.")

    new_session = _create_session_and_set_cookies(
        db=db,
        user=user,
        request=request,
        response=response,
        family_id=session_row.family_id,
    )
    session_row.revoked_at = now
    session_row.replaced_by_id = new_session.id
    session_row.last_used_at = now
    db.commit()
    return AuthSessionResponse(user=serialize_user(user))


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> MessageResponse:
    ip = get_client_ip(request)
    now = datetime.now(timezone.utc)
    family_id: uuid.UUID | None = None
    actor: User | None = None

    raw_access = request.cookies.get(ACCESS_COOKIE_NAME)
    if raw_access:
        try:
            claims = decode_access_token(raw_access)
            family_id = claims.sid
            actor = db.get(User, claims.sub)
        except AppError:
            pass

    if family_id is None:
        raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
        if raw_refresh:
            sess = db.execute(
                select(SessionRecord).where(SessionRecord.token_hash == sha256_hex(raw_refresh))
            ).scalar_one_or_none()
            if sess is not None:
                family_id = sess.family_id
                actor = db.get(User, sess.user_id)

    if family_id is not None:
        db.execute(
            update(SessionRecord)
            .where(
                SessionRecord.family_id == family_id,
                SessionRecord.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        audit.record(
            db,
            action="AUTH_LOGOUT",
            outcome=AuditOutcome.allowed,
            actor=actor,
            resource_type="session_family",
            resource_id=str(family_id),
            ip=ip,
        )
        db.commit()
        trigger_session_wipe(family_id)

    clear_auth_cookies(response)
    return MessageResponse(message="Signed out.")
