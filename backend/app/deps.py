from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import AppError, ErrorCode
from app.models.audit import AuditOutcome
from app.models.document import Document
from app.models.session import SessionRecord
from app.models.user import User, UserRole, UserStatus
from app.security import ACCESS_COOKIE_NAME, decode_access_token
from app.services import audit

STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Hook invoked when a session family is revoked/logged out; wired to Vault in M3.
_session_wipe_hook: Callable[[uuid.UUID], None] | None = None


def register_session_wipe_hook(hook: Callable[[uuid.UUID], None]) -> None:
    global _session_wipe_hook
    _session_wipe_hook = hook


def trigger_session_wipe(session_family_id: uuid.UUID) -> None:
    if _session_wipe_hook is not None:
        _session_wipe_hook(session_family_id)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session_family_id: uuid.UUID


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return "unknown"


def verify_csrf(request: Request) -> None:
    """Rules.md S7: State-changing requests require X-Requested-With: fetch and matching Origin."""
    if request.method.upper() not in STATE_CHANGING_METHODS:
        return

    if request.headers.get("x-requested-with") != "fetch":
        raise AppError(ErrorCode.CSRF_REJECTED, 403, "Request blocked by CSRF protection.")

    settings = get_settings()
    expected_origin = settings.FRONTEND_ORIGIN.rstrip("/")
    origin = (request.headers.get("origin") or "").rstrip("/")
    if not origin or origin != expected_origin:
        raise AppError(ErrorCode.CSRF_REJECTED, 403, "Request origin is not allowed.")


def get_current_auth(
    request: Request,
    db: Session = Depends(get_db),
) -> AuthContext:
    """Rules.md S3: Load user from DB on every request; verify token_version and active session family."""
    raw_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not raw_token:
        raise AppError(ErrorCode.UNAUTHENTICATED, 401, "Authentication required.")

    claims = decode_access_token(raw_token)
    user = db.get(User, claims.sub)
    if user is None:
        raise AppError(ErrorCode.UNAUTHENTICATED, 401, "Authentication required.")

    if user.token_version != claims.tv:
        raise AppError(ErrorCode.SESSION_REVOKED, 401, "Session is no longer valid. Please sign in again.")

    now = datetime.now(timezone.utc)
    active_session = db.execute(
        select(SessionRecord.id)
        .where(
            SessionRecord.user_id == user.id,
            SessionRecord.family_id == claims.sid,
            SessionRecord.revoked_at.is_(None),
            SessionRecord.expires_at > now,
        )
        .limit(1)
    ).scalar_one_or_none()
    if active_session is None:
        raise AppError(ErrorCode.SESSION_REVOKED, 401, "Session has been revoked. Please sign in again.")

    request.state.rate_limit_user_id = str(user.id)
    return AuthContext(user=user, session_family_id=claims.sid)


def current_user(auth: AuthContext = Depends(get_current_auth)) -> User:
    return auth.user


def require_active(user: User = Depends(current_user)) -> User:
    if user.status != UserStatus.active:
        raise AppError(
            ErrorCode.ACCOUNT_RESTRICTED,
            403,
            "Your account is restricted. You can contact support from Help.",
        )
    return user


def require_role(*roles: UserRole) -> Callable[[User], User]:
    allowed = frozenset(roles)

    def _checker(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise AppError(ErrorCode.FORBIDDEN, 403, "You do not have access to this resource.")
        return user

    return _checker


def require_doctor_for_documents(
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> AuthContext:
    """Rules.md S5: Admin/auditor calling any document endpoint gets 403 ADMIN_NO_DOCUMENT_ACCESS + audit."""
    if auth.user.role in (UserRole.admin, UserRole.auditor):
        audit.record(
            db,
            action="ADMIN_DOC_ACCESS_DENIED",
            outcome=AuditOutcome.denied,
            actor=auth.user,
            resource_type="document",
            ip=get_client_ip(request),
            metadata={"path": request.url.path},
        )
        db.commit()
        raise AppError(
            ErrorCode.ADMIN_NO_DOCUMENT_ACCESS,
            403,
            "Administrators and auditors cannot access clinical documents.",
        )
    return auth


def require_active_doctor_for_documents(
    auth: AuthContext = Depends(require_doctor_for_documents),
) -> AuthContext:
    if auth.user.status != UserStatus.active:
        raise AppError(
            ErrorCode.ACCOUNT_RESTRICTED,
            403,
            "Your account is restricted. You can contact support from Help.",
        )
    return auth


def get_owned_document(
    document_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_doctor_for_documents),
    db: Session = Depends(get_db),
) -> Document:
    """Rules.md S5: Non-owner (or missing) returns 404 + audit DOC_ACCESS_DENIED."""
    doc = db.get(Document, document_id)
    if doc is None or doc.owner_id != auth.user.id:
        audit.record(
            db,
            action="DOC_ACCESS_DENIED",
            outcome=AuditOutcome.denied,
            actor=auth.user,
            resource_type="document",
            resource_id=str(document_id),
            ip=get_client_ip(request),
        )
        db.commit()
        raise AppError(ErrorCode.NOT_FOUND, 404, "Document not found.")
    return doc
