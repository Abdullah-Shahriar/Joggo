from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, current_user, get_client_ip, get_current_auth, trigger_session_wipe
from app.errors import AppError, ErrorCode
from app.models.audit import AuditOutcome
from app.models.session import SessionRecord
from app.models.user import User
from app.routers.auth import serialize_user
from app.schemas.auth import AuthUserResponse, MessageResponse
from app.schemas.user import (
    ChangePasswordRequest,
    SessionInfoResponse,
    SessionListResponse,
    UpdateProfileRequest,
)
from app.security import (
    clear_auth_cookies,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.services import audit

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=AuthUserResponse)
def get_me(user: User = Depends(current_user)) -> AuthUserResponse:
    return serialize_user(user)


@router.patch("", response_model=AuthUserResponse)
def update_me(
    payload: UpdateProfileRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AuthUserResponse:
    cleaned_name = payload.full_name.strip()
    if len(cleaned_name) < 2:
        raise AppError(ErrorCode.VALIDATION_ERROR, 422, "Full name must be at least 2 characters.")
    user.full_name = cleaned_name
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.post("/password", response_model=MessageResponse)
def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    response: Response,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> MessageResponse:
    user = auth.user
    if user.password_hash is None:
        raise AppError(
            ErrorCode.NO_PASSWORD_SET,
            400,
            "You sign in with Google, so there is no password to change.",
        )

    if not verify_password(user.password_hash, payload.current):
        raise AppError(ErrorCode.INVALID_CREDENTIALS, 401, "Current password is incorrect.")

    if not validate_password_strength(payload.new):
        raise AppError(
            ErrorCode.WEAK_PASSWORD,
            422,
            "Password must be at least 10 characters and include a letter and a digit.",
        )

    now = datetime.now(timezone.utc)
    active_families = list(
        db.execute(
            select(SessionRecord.family_id)
            .where(
                SessionRecord.user_id == user.id,
                SessionRecord.revoked_at.is_(None),
            )
            .distinct()
        ).scalars()
    )

    user.password_hash = hash_password(payload.new)
    user.token_version += 1
    db.execute(
        update(SessionRecord)
        .where(
            SessionRecord.user_id == user.id,
            SessionRecord.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    audit.record(
        db,
        action="PASSWORD_CHANGED",
        outcome=AuditOutcome.allowed,
        actor=user,
        resource_type="user",
        resource_id=str(user.id),
        ip=get_client_ip(request),
    )
    db.commit()

    for fam_id in active_families:
        trigger_session_wipe(fam_id)

    clear_auth_cookies(response)
    return MessageResponse(message="Password updated. Please sign in again.")


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> SessionListResponse:
    now = datetime.now(timezone.utc)
    rows = (
        db.execute(
            select(SessionRecord)
            .where(
                SessionRecord.user_id == auth.user.id,
                SessionRecord.revoked_at.is_(None),
                SessionRecord.expires_at > now,
            )
            .order_by(SessionRecord.created_at.desc())
        )
        .scalars()
        .all()
    )

    return SessionListResponse(
        items=[
            SessionInfoResponse(
                id=row.id,
                family_id=row.family_id,
                user_agent=row.user_agent,
                ip=row.ip,
                created_at=row.created_at,
                last_used_at=row.last_used_at,
                expires_at=row.expires_at,
                is_current=(row.family_id == auth.session_family_id),
            )
            for row in rows
        ]
    )


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> MessageResponse:
    target = db.execute(
        select(SessionRecord).where(
            SessionRecord.id == session_id,
            SessionRecord.user_id == auth.user.id,
        )
    ).scalar_one_or_none()
    if target is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Session not found.")

    now = datetime.now(timezone.utc)
    db.execute(
        update(SessionRecord)
        .where(
            SessionRecord.family_id == target.family_id,
            SessionRecord.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    audit.record(
        db,
        action="AUTH_LOGOUT",
        outcome=AuditOutcome.allowed,
        actor=auth.user,
        resource_type="session_family",
        resource_id=str(target.family_id),
        ip=get_client_ip(request),
    )
    db.commit()
    trigger_session_wipe(target.family_id)

    if target.family_id == auth.session_family_id:
        clear_auth_cookies(response)

    return MessageResponse(message="Session signed out.")
