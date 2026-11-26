import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, get_client_ip
from app.errors import AppError, ErrorCode
from app.models.complaint import Complaint, ComplaintCategory, ComplaintStatus
from app.models.user import User, UserRole
from app.schemas.complaint import (
    ComplaintDetailResponse,
    ComplaintListResponse,
    ComplaintMessageCreateRequest,
    CreateComplaintRequest,
)
from app.services import complaints as complaint_svc

router = APIRouter(prefix="/api/complaints", tags=["complaints"])


def _ensure_non_admin(user: User) -> User:
    if user.role == UserRole.admin:
        raise AppError(ErrorCode.FORBIDDEN, 403, "Administrators manage complaints from the admin inbox.")
    return user


def _get_owned_complaint(db: Session, complaint_id: uuid.UUID, user: User) -> Complaint:
    comp = db.get(Complaint, complaint_id)
    if comp is None or comp.user_id != user.id:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Complaint not found.")
    return comp


@router.post("", response_model=ComplaintDetailResponse, status_code=201)
def create_complaint_endpoint(
    request: Request,
    payload: CreateComplaintRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ComplaintDetailResponse:
    _ensure_non_admin(user)
    return complaint_svc.create_complaint(
        db,
        user=user,
        subject=payload.subject,
        category=payload.category,
        message=payload.message,
        document_id=payload.document_id,
        ip=get_client_ip(request),
    )


@router.get("", response_model=ComplaintListResponse)
def list_my_complaints(
    status: ComplaintStatus | None = Query(default=None),
    category: ComplaintCategory | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ComplaintListResponse:
    _ensure_non_admin(user)
    return complaint_svc.list_complaints(
        db,
        owner_id=user.id,
        status=status,
        category=category,
        page=page,
        page_size=page_size,
    )


@router.get("/{complaint_id}", response_model=ComplaintDetailResponse)
def get_my_complaint(
    complaint_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ComplaintDetailResponse:
    _ensure_non_admin(user)
    comp = _get_owned_complaint(db, complaint_id, user)
    return complaint_svc.serialize_detail(db, comp)


@router.post("/{complaint_id}/messages", response_model=ComplaintDetailResponse, status_code=201)
def reply_my_complaint(
    complaint_id: uuid.UUID,
    request: Request,
    payload: ComplaintMessageCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ComplaintDetailResponse:
    _ensure_non_admin(user)
    comp = _get_owned_complaint(db, complaint_id, user)
    return complaint_svc.add_complaint_message(
        db,
        complaint=comp,
        author=user,
        body=payload.body,
        ip=get_client_ip(request),
    )
