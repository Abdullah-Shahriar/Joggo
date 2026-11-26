from datetime import datetime, timezone
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import asc, desc, func, or_, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_client_ip, require_role
from app.errors import AppError, ErrorCode
from app.models.audit import AuditOutcome
from app.models.complaint import Complaint, ComplaintCategory, ComplaintStatus
from app.models.document import Document, DocumentStatus
from app.models.session import SessionRecord
from app.models.user import User, UserRole, UserStatus
from app.schemas.admin import (
    AdminAnalyticsResponse,
    AdminOverviewResponse,
    AdminUserItem,
    AdminUserListResponse,
    AdminUserUpdateRequest,
)
from app.schemas.complaint import (
    ComplaintDetailResponse,
    ComplaintListResponse,
    ComplaintMessageCreateRequest,
    ComplaintStatusUpdateRequest,
)
from app.services import audit
from app.services.analytics import get_admin_analytics, get_admin_overview
from app.services import complaints as complaint_svc
from app.services.vault import vault

router = APIRouter(prefix="/api/admin", tags=["admin"])

NON_TERMINAL_DOC_STATUSES: tuple[DocumentStatus, ...] = (
    DocumentStatus.UPLOADED,
    DocumentStatus.PROCESSING,
    DocumentStatus.BLOCKED,
    DocumentStatus.REVIEW_REQUIRED,
    DocumentStatus.APPROVED,
    DocumentStatus.SENDING,
)


def _serialize_admin_user(db: Session, user: User, doc_count: int | None = None) -> AdminUserItem:
    count = (
        doc_count
        if doc_count is not None
        else int(
            db.execute(select(func.count(Document.id)).where(Document.owner_id == user.id)).scalar_one()
        )
    )
    return AdminUserItem(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        status=user.status.value,
        restricted_reason=user.restricted_reason,
        restricted_at=user.restricted_at,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        documents_count=count,
    )


@router.get("/overview", response_model=AdminOverviewResponse)
def admin_overview(
    _admin: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
) -> AdminOverviewResponse:
    return get_admin_overview(db)


@router.get("/analytics", response_model=AdminAnalyticsResponse)
def admin_analytics(
    _admin: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
) -> AdminAnalyticsResponse:
    return get_admin_analytics(db)


@router.get("/users", response_model=AdminUserListResponse)
def list_users(
    q: str | None = Query(default=None),
    role: UserRole | None = Query(default=None),
    status: UserStatus | None = Query(default=None),
    sort: Literal["created_at", "full_name", "email", "last_login_at", "role", "status"] = Query(default="created_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    _admin: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    doc_counts = (
        select(Document.owner_id, func.count(Document.id).label("doc_count"))
        .group_by(Document.owner_id)
        .subquery()
    )
    stmt = select(User, func.coalesce(doc_counts.c.doc_count, 0).label("doc_count")).outerjoin(
        doc_counts, doc_counts.c.owner_id == User.id
    )

    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(needle), User.email.ilike(needle)))
    if role is not None:
        stmt = stmt.where(User.role == role)
    if status is not None:
        stmt = stmt.where(User.status == status)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    col_map = {
        "created_at": User.created_at,
        "full_name": User.full_name,
        "email": User.email,
        "last_login_at": User.last_login_at,
        "role": User.role,
        "status": User.status,
    }
    direction = asc if order == "asc" else desc

    rows = (
        db.execute(
            stmt.order_by(direction(col_map[sort]), desc(User.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .all()
    )

    return AdminUserListResponse(
        items=[_serialize_admin_user(db, u, int(cnt)) for u, cnt in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=AdminUserItem)
def get_user_detail(
    user_id: uuid.UUID,
    _admin: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
) -> AdminUserItem:
    target = db.get(User, user_id)
    if target is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "User not found.")
    return _serialize_admin_user(db, target)


@router.patch("/users/{user_id}", response_model=AdminUserItem)
def update_user(
    user_id: uuid.UUID,
    request: Request,
    payload: AdminUserUpdateRequest,
    admin_user: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
) -> AdminUserItem:
    target = db.get(User, user_id)
    if target is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "User not found.")

    if target.id == admin_user.id:
        raise AppError(ErrorCode.CANNOT_MODIFY_SELF, 400, "Administrators cannot modify their own account.")

    if target.role == UserRole.admin:
        raise AppError(ErrorCode.CANNOT_MODIFY_ADMIN, 403, "Administrators cannot modify another admin account.")

    ip = get_client_ip(request)
    now = datetime.now(timezone.utc)
    should_wipe_vault = False

    if payload.role is not None and payload.role != target.role:
        if payload.role not in {UserRole.doctor, UserRole.auditor}:
            raise AppError(
                ErrorCode.INVALID_ROLE_CHANGE,
                400,
                "Role can only be changed between doctor and auditor.",
            )
        prev_role = target.role.value
        target.role = payload.role
        target.token_version += 1
        db.execute(
            update(SessionRecord)
            .where(SessionRecord.user_id == target.id, SessionRecord.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        audit.record(
            db,
            action="USER_ROLE_CHANGE",
            outcome=AuditOutcome.allowed,
            actor=admin_user,
            resource_type="user",
            resource_id=str(target.id),
            ip=ip,
            metadata={"from_role": prev_role, "to_role": payload.role.value},
        )
        should_wipe_vault = True

    if payload.status is not None and payload.status != target.status:
        if payload.status == UserStatus.restricted:
            reason = (payload.restricted_reason or "Restricted by administrator").strip()[:500]
            target.status = UserStatus.restricted
            target.restricted_reason = reason
            target.restricted_at = now
            # Fail all non-terminal documents owned by this user (architecture.md §9, §23)
            failed_res = db.execute(
                update(Document)
                .where(
                    Document.owner_id == target.id,
                    Document.status.in_(list(NON_TERMINAL_DOC_STATUSES)),
                )
                .values(
                    status=DocumentStatus.FAILED,
                    failure_code=ErrorCode.ACCOUNT_RESTRICTED.value,
                    vault_expired=True,
                    version=Document.version + 1,
                    updated_at=now,
                )
            )
            audit.record(
                db,
                action="USER_RESTRICT",
                outcome=AuditOutcome.allowed,
                actor=admin_user,
                resource_type="user",
                resource_id=str(target.id),
                ip=ip,
                metadata={"failed_documents": failed_res.rowcount or 0},
            )
            should_wipe_vault = True
        elif payload.status == UserStatus.active:
            target.status = UserStatus.active
            target.restricted_reason = None
            target.restricted_at = None
            audit.record(
                db,
                action="USER_RESTORE",
                outcome=AuditOutcome.allowed,
                actor=admin_user,
                resource_type="user",
                resource_id=str(target.id),
                ip=ip,
            )

    db.commit()
    db.refresh(target)

    if should_wipe_vault:
        vault.wipe_user(target.id, mark_db=True)

    return _serialize_admin_user(db, target)


@router.get("/complaints", response_model=ComplaintListResponse)
def admin_list_complaints(
    status: ComplaintStatus | None = Query(default=None),
    category: ComplaintCategory | None = Query(default=None),
    q: str | None = Query(default=None),
    sort: Literal["updated_at", "created_at", "status", "subject"] = Query(default="updated_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    _admin: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
) -> ComplaintListResponse:
    return complaint_svc.list_complaints(
        db,
        status=status,
        category=category,
        q=q,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@router.get("/complaints/{complaint_id}", response_model=ComplaintDetailResponse)
def admin_get_complaint(
    complaint_id: uuid.UUID,
    _admin: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
) -> ComplaintDetailResponse:
    comp = db.get(Complaint, complaint_id)
    if comp is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Complaint not found.")
    return complaint_svc.serialize_detail(db, comp)


@router.post("/complaints/{complaint_id}/messages", response_model=ComplaintDetailResponse, status_code=201)
def admin_reply_complaint(
    complaint_id: uuid.UUID,
    request: Request,
    payload: ComplaintMessageCreateRequest,
    admin_user: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
) -> ComplaintDetailResponse:
    comp = db.get(Complaint, complaint_id)
    if comp is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Complaint not found.")
    return complaint_svc.add_complaint_message(
        db,
        complaint=comp,
        author=admin_user,
        body=payload.body,
        ip=get_client_ip(request),
    )


@router.patch("/complaints/{complaint_id}/status", response_model=ComplaintDetailResponse)
def admin_update_complaint_status(
    complaint_id: uuid.UUID,
    request: Request,
    payload: ComplaintStatusUpdateRequest,
    admin_user: User = Depends(require_role(UserRole.admin)),
    db: Session = Depends(get_db),
) -> ComplaintDetailResponse:
    comp = db.get(Complaint, complaint_id)
    if comp is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Complaint not found.")
    return complaint_svc.update_complaint_status(
        db,
        complaint=comp,
        admin_user=admin_user,
        new_status=payload.status,
        ip=get_client_ip(request),
    )
