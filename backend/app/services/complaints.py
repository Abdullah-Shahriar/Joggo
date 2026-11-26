from datetime import datetime, timezone
import uuid

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.errors import AppError, ErrorCode
from app.models.audit import AuditOutcome
from app.models.complaint import Complaint, ComplaintCategory, ComplaintMessage, ComplaintStatus
from app.models.document import Document
from app.models.user import User, UserRole
from app.schemas.complaint import (
    ComplaintDetailResponse,
    ComplaintListResponse,
    ComplaintMessageItem,
    ComplaintSummaryItem,
)
from app.services import audit

ALLOWED_COMPLAINT_TRANSITIONS: dict[ComplaintStatus, set[ComplaintStatus]] = {
    ComplaintStatus.open: {ComplaintStatus.in_progress, ComplaintStatus.resolved},
    ComplaintStatus.in_progress: {ComplaintStatus.resolved},
    ComplaintStatus.resolved: {ComplaintStatus.in_progress},
}


def _serialize_summary(complaint: Complaint, owner: User) -> ComplaintSummaryItem:
    return ComplaintSummaryItem(
        id=complaint.id,
        user_id=complaint.user_id,
        user_name=owner.full_name,
        user_email=owner.email,
        subject=complaint.subject,
        category=complaint.category.value,
        status=complaint.status.value,
        document_id=complaint.document_id,
        created_at=complaint.created_at,
        updated_at=complaint.updated_at,
        resolved_at=complaint.resolved_at,
    )


def serialize_detail(db: Session, complaint: Complaint) -> ComplaintDetailResponse:
    owner = db.get(User, complaint.user_id)
    assert owner is not None
    msgs = (
        db.execute(
            select(ComplaintMessage, User.full_name)
            .join(User, User.id == ComplaintMessage.author_id)
            .where(ComplaintMessage.complaint_id == complaint.id)
            .order_by(ComplaintMessage.created_at.asc())
        )
        .all()
    )
    return ComplaintDetailResponse(
        id=complaint.id,
        user_id=complaint.user_id,
        user_name=owner.full_name,
        user_email=owner.email,
        subject=complaint.subject,
        category=complaint.category.value,
        message=complaint.message,
        document_id=complaint.document_id,
        status=complaint.status.value,
        created_at=complaint.created_at,
        updated_at=complaint.updated_at,
        resolved_at=complaint.resolved_at,
        messages=[
            ComplaintMessageItem(
                id=msg.id,
                author_id=msg.author_id,
                author_name=author_name,
                author_role=msg.author_role,
                body=msg.body,
                created_at=msg.created_at,
            )
            for msg, author_name in msgs
        ],
    )


def create_complaint(
    db: Session,
    *,
    user: User,
    subject: str,
    category: ComplaintCategory,
    message: str,
    document_id: uuid.UUID | None,
    ip: str | None,
) -> ComplaintDetailResponse:
    if document_id is not None:
        doc = db.get(Document, document_id)
        if doc is None or doc.owner_id != user.id:
            audit.record(
                db,
                action="DOC_ACCESS_DENIED",
                outcome=AuditOutcome.denied,
                actor=user,
                resource_type="document",
                resource_id=str(document_id),
                ip=ip,
            )
            db.commit()
            raise AppError(ErrorCode.NOT_FOUND, 404, "Related document not found.")

    cleaned_subject = subject.strip()
    cleaned_message = message.strip()
    if len(cleaned_subject) < 3 or len(cleaned_message) < 10:
        raise AppError(ErrorCode.VALIDATION_ERROR, 422, "Please provide a valid subject and message.")

    complaint = Complaint(
        user_id=user.id,
        subject=cleaned_subject,
        category=category,
        message=cleaned_message,
        document_id=document_id,
        status=ComplaintStatus.open,
    )
    db.add(complaint)
    db.flush()

    audit.record(
        db,
        action="COMPLAINT_CREATE",
        outcome=AuditOutcome.allowed,
        actor=user,
        resource_type="complaint",
        resource_id=str(complaint.id),
        ip=ip,
        metadata={"category": category.value, "has_document": document_id is not None},
    )
    db.commit()
    db.refresh(complaint)
    return serialize_detail(db, complaint)


def list_complaints(
    db: Session,
    *,
    owner_id: uuid.UUID | None = None,
    status: ComplaintStatus | None = None,
    category: ComplaintCategory | None = None,
    q: str | None = None,
    sort: str = "updated_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 10,
) -> ComplaintListResponse:
    stmt = select(Complaint, User).join(User, User.id == Complaint.user_id)
    if owner_id is not None:
        stmt = stmt.where(Complaint.user_id == owner_id)
    if status is not None:
        stmt = stmt.where(Complaint.status == status)
    if category is not None:
        stmt = stmt.where(Complaint.category == category)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Complaint.subject.ilike(needle),
                User.full_name.ilike(needle),
                User.email.ilike(needle),
            )
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    col_map = {
        "updated_at": Complaint.updated_at,
        "created_at": Complaint.created_at,
        "status": Complaint.status,
        "subject": Complaint.subject,
    }
    sort_col = col_map.get(sort, Complaint.updated_at)
    direction = asc if order == "asc" else desc

    rows = (
        db.execute(
            stmt.order_by(direction(sort_col), desc(Complaint.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .all()
    )

    return ComplaintListResponse(
        items=[_serialize_summary(c, u) for c, u in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


def add_complaint_message(
    db: Session,
    *,
    complaint: Complaint,
    author: User,
    body: str,
    ip: str | None,
) -> ComplaintDetailResponse:
    cleaned = body.strip()
    if not cleaned:
        raise AppError(ErrorCode.VALIDATION_ERROR, 422, "Reply message cannot be empty.")

    if author.role != UserRole.admin and complaint.status == ComplaintStatus.resolved:
        raise AppError(ErrorCode.COMPLAINT_CLOSED, 409, "This complaint is resolved.")

    now = datetime.now(timezone.utc)
    msg = ComplaintMessage(
        complaint_id=complaint.id,
        author_id=author.id,
        author_role=author.role.value,
        body=cleaned,
    )
    db.add(msg)
    complaint.updated_at = now

    auto_moved = False
    if author.role == UserRole.admin and complaint.status == ComplaintStatus.open:
        complaint.status = ComplaintStatus.in_progress
        auto_moved = True

    audit.record(
        db,
        action="COMPLAINT_REPLY",
        outcome=AuditOutcome.allowed,
        actor=author,
        resource_type="complaint",
        resource_id=str(complaint.id),
        ip=ip,
        metadata={"auto_in_progress": auto_moved},
    )
    db.commit()
    db.refresh(complaint)
    return serialize_detail(db, complaint)


def update_complaint_status(
    db: Session,
    *,
    complaint: Complaint,
    admin_user: User,
    new_status: ComplaintStatus,
    ip: str | None,
) -> ComplaintDetailResponse:
    allowed = ALLOWED_COMPLAINT_TRANSITIONS.get(complaint.status, set())
    if new_status not in allowed:
        raise AppError(
            ErrorCode.INVALID_COMPLAINT_TRANSITION,
            409,
            f"Cannot change complaint status from {complaint.status.value} to {new_status.value}.",
        )

    now = datetime.now(timezone.utc)
    prev_status = complaint.status.value
    complaint.status = new_status
    complaint.updated_at = now
    if new_status == ComplaintStatus.resolved:
        complaint.resolved_at = now
    else:
        complaint.resolved_at = None

    audit.record(
        db,
        action="COMPLAINT_STATUS",
        outcome=AuditOutcome.allowed,
        actor=admin_user,
        resource_type="complaint",
        resource_id=str(complaint.id),
        ip=ip,
        metadata={"from_status": prev_status, "to_status": new_status.value},
    )
    db.commit()
    db.refresh(complaint)
    return serialize_detail(db, complaint)
