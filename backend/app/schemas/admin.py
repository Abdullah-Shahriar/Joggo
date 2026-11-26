from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: int
    ts: datetime
    actor_id: uuid.UUID | None
    actor_role: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    outcome: str
    ip: str | None
    metadata: dict[str, Any]


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int


class AuditVerifyResponse(BaseModel):
    ok: bool
    checked: int
    first_broken_id: int | None
