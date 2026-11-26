from datetime import datetime
from typing import Literal
import uuid

from sqlalchemy import String, asc, cast, desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus, TaskType
from app.schemas.document import DocumentListItem, DocumentListResponse


def query_user_documents(
    db: Session,
    *,
    owner_id: uuid.UUID,
    q: str | None = None,
    status: DocumentStatus | None = None,
    task_type: TaskType | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: Literal["created_at", "original_filename", "status", "entity_count"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    page: int = 1,
    page_size: int = 10,
) -> DocumentListResponse:
    stmt = select(Document).where(Document.owner_id == owner_id)

    if q and q.strip():
        needle = f"%{q.strip()}%"
        id_prefix = f"{q.strip()}%"
        stmt = stmt.where(
            or_(
                Document.original_filename.ilike(needle),
                cast(Document.id, String).ilike(id_prefix),
            )
        )
    if status is not None:
        stmt = stmt.where(Document.status == status)
    if task_type is not None:
        stmt = stmt.where(Document.task_type == task_type)
    if date_from is not None:
        stmt = stmt.where(Document.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Document.created_at <= date_to)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    if sort == "entity_count":
        all_rows = db.execute(stmt.order_by(desc(Document.created_at))).scalars().all()
        all_rows.sort(
            key=lambda d: (sum((d.entity_summary or {}).values()), d.created_at),
            reverse=(order == "desc"),
        )
        start_idx = (page - 1) * page_size
        rows = all_rows[start_idx : start_idx + page_size]
    else:
        col_map = {
            "created_at": Document.created_at,
            "original_filename": Document.original_filename,
            "status": Document.status,
        }
        direction = asc if order == "asc" else desc
        rows = (
            db.execute(
                stmt.order_by(direction(col_map[sort]), desc(Document.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )

    return DocumentListResponse(
        items=[
            DocumentListItem(
                id=d.id,
                original_filename=d.original_filename,
                size_bytes=d.size_bytes,
                page_count=d.page_count,
                task_type=d.task_type.value,
                status=d.status.value,
                entity_count=sum((d.entity_summary or {}).values()),
                vault_expired=d.vault_expired,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in rows
        ],
        total=int(total),
        page=page,
        page_size=page_size,
    )
