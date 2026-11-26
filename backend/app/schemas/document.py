from datetime import datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field


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


class DocumentListItem(BaseModel):
    id: uuid.UUID
    original_filename: str
    size_bytes: int
    page_count: int
    task_type: str
    status: str
    entity_count: int
    vault_expired: bool
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    total: int
    page: int
    page_size: int


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


class DocumentStepsResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    steps: list[PipelineStepResponse]


class OriginalHighlight(BaseModel):
    start: int
    end: int
    type: str
    token: str
    source: str
    rule: str


class OriginalTextResponse(BaseModel):
    document_id: uuid.UUID
    original_text: str
    highlights: list[OriginalHighlight]


class SafetyFindingView(BaseModel):
    type: str
    reason: str
    start: int
    end: int
    snippet: str | None = None


class SanitizedTextResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    sanitized_text: str
    sanitized_sha256: str
    vault_expired: bool
    version: int
    safety_status: str | None
    findings: list[SafetyFindingView]
    warnings: list[str]


class ManualMarkRequest(BaseModel):
    text: str = Field(min_length=2, max_length=200)
    entity_type: Literal[
        "PATIENT",
        "DOCTOR",
        "PERSON",
        "PHONE",
        "EMAIL",
        "ID",
        "MRN",
        "LOCATION",
        "FACILITY",
        "OTHER",
    ]


class ManualMarkResponse(BaseModel):
    document: DocumentDetailResponse
    occurrences: int


class ApproveDocumentRequest(BaseModel):
    sanitized_sha256: str = Field(min_length=64, max_length=64)


class ExternalHandoffRequest(BaseModel):
    provider: Literal["gemini", "chatgpt", "claude"]
    sanitized_sha256: str = Field(min_length=64, max_length=64)


class ExternalHandoffResponse(BaseModel):
    prompt_text: str


class SendDocumentResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    llm_request_id: uuid.UUID
    idempotency_key: str
    replayed: bool = False


class RehydrateWarning(BaseModel):
    code: str
    token: str


class DocumentResultResponse(BaseModel):
    document_id: uuid.UUID
    text: str
    rehydrated: bool
    vault_expired: bool
    llm_provider_used: str | None
    fallback_used: bool
    warnings: list[RehydrateWarning]
