from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, Field

from app.models.user import UserRole, UserStatus
from app.schemas.document import DocumentListItem


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


class EntityTypeCount(BaseModel):
    entity_type: str
    count: int


class DashboardResponse(BaseModel):
    counts_by_status: dict[str, int]
    processed_last_7_days: int
    waiting_for_review: int
    blocked_count: int
    recent_documents: list[DocumentListItem]
    top_entity_types: list[EntityTypeCount]
    avg_pipeline_seconds: float | None


class AdminOverviewResponse(BaseModel):
    open_complaints: int
    in_progress_complaints: int
    restricted_users: int
    documents_processed_today: int


class AdminUserItem(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    status: str
    restricted_reason: str | None
    restricted_at: datetime | None
    created_at: datetime
    last_login_at: datetime | None
    documents_count: int


class AdminUserListResponse(BaseModel):
    items: list[AdminUserItem]
    total: int
    page: int
    page_size: int


class AdminUserUpdateRequest(BaseModel):
    status: UserStatus | None = None
    restricted_reason: str | None = Field(default=None, max_length=500)
    role: UserRole | None = None


class DailyDocumentStatusCounts(BaseModel):
    date: str
    total: int
    by_status: dict[str, int]


class AdminAnalyticsResponse(BaseModel):
    users_by_role: dict[str, int]
    users_by_status: dict[str, int]
    documents_per_day: list[DailyDocumentStatusCounts]
    llm_provider_usage: dict[str, int]
    llm_fallback_count: int
    avg_llm_latency_ms: float | None
    complaints_by_status: dict[str, int]
    safety_block_rate: float
    entity_type_totals: list[EntityTypeCount]
