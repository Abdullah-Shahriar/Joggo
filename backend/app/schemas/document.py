from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: uuid.UUID
    status: str


class PipelineStepResponse(BaseModel):
    step: str
    status: str
    attempts: int
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None


class DocumentEntityResponse(BaseModel):
    id: uuid.UUID
    token: str
    entity_type: str
    source: str
    detector: str
    rule_id: str
    reason: str
    score: float
    occurrences: int


class DocumentDetailResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    size_bytes: int
    page_count: int
    task_type: str
    status: str
    failure_code: str | None
    entity_summary: dict[str, int]
    safety_report: dict[str, Any] | None
    llm_provider_used: str | None
    approved_at: datetime | None
    vault_expired: bool
    version: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    sanitized_sha256: str | None = None
    steps: list[PipelineStepResponse]
    entities: list[DocumentEntityResponse]
