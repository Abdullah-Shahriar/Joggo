from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.errors import AppError, ErrorCode
from app.models.document import Document, DocumentStatus


def transition(
    db: Session,
    doc_id: uuid.UUID,
    expected_from: set[DocumentStatus],
    to: DocumentStatus,
    **fields: Any,
) -> Document:
    """Atomic conditional state transition (rules.md B4, architecture.md §9)."""
    if not expected_from:
        raise AppError(ErrorCode.INVALID_STATE, 409, "Invalid state transition.")

    values: dict[str, Any] = {
        "status": to,
        "version": Document.version + 1,
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(fields)

    result = db.execute(
        update(Document)
        .where(
            Document.id == doc_id,
            Document.status.in_(list(expected_from)),
        )
        .values(**values)
    )
    if (result.rowcount or 0) == 0:
        raise AppError(
            ErrorCode.INVALID_STATE,
            409,
            "Document cannot be updated in its current state.",
        )

    db.flush()
    doc = db.get(Document, doc_id)
    if doc is None:
        raise AppError(ErrorCode.NOT_FOUND, 404, "Document not found.")
    db.refresh(doc)
    return doc
