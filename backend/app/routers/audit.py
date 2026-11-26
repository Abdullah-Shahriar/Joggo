from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models.audit import AuditLog, AuditOutcome
from app.models.user import User, UserRole
from app.schemas.admin import AuditLogItem, AuditLogListResponse, AuditVerifyResponse
from app.services import audit

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    actor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    outcome: AuditOutcome | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    sort: Literal["ts", "action", "outcome", "id"] = Query(default="ts"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    _user: User = Depends(require_role(UserRole.admin, UserRole.auditor)),
    db: Session = Depends(get_db),
) -> AuditLogListResponse:
    stmt = select(AuditLog)

    if actor:
        actor_clean = actor.strip()
        try:
            actor_uuid = uuid.UUID(actor_clean)
            stmt = stmt.where(AuditLog.actor_id == actor_uuid)
        except ValueError:
            stmt = stmt.where(AuditLog.actor_role == actor_clean)

    if action:
        stmt = stmt.where(AuditLog.action == action.strip())
    if outcome is not None:
        stmt = stmt.where(AuditLog.outcome == outcome)
    if date_from is not None:
        stmt = stmt.where(AuditLog.ts >= date_from)
    if date_to is not None:
        stmt = stmt.where(AuditLog.ts <= date_to)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    sort_col_map = {
        "ts": AuditLog.ts,
        "action": AuditLog.action,
        "outcome": AuditLog.outcome,
        "id": AuditLog.id,
    }
    sort_col = sort_col_map[sort]
    direction = asc if order == "asc" else desc

    rows = (
        db.execute(
            stmt.order_by(direction(sort_col), desc(AuditLog.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    return AuditLogListResponse(
        items=[
            AuditLogItem(
                id=row.id,
                ts=row.ts,
                actor_id=row.actor_id,
                actor_role=row.actor_role,
                action=row.action,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                outcome=row.outcome.value,
                ip=row.ip,
                metadata=row.metadata_ or {},
            )
            for row in rows
        ],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.get("/verify", response_model=AuditVerifyResponse)
def verify_audit_logs(
    _user: User = Depends(require_role(UserRole.admin, UserRole.auditor)),
    db: Session = Depends(get_db),
) -> AuditVerifyResponse:
    ok, checked, first_broken_id = audit.verify_chain(db)
    return AuditVerifyResponse(ok=ok, checked=checked, first_broken_id=first_broken_id)
