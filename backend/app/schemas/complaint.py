from datetime import datetime
import uuid

from pydantic import BaseModel, Field

from app.models.complaint import ComplaintCategory, ComplaintStatus


class CreateComplaintRequest(BaseModel):
    subject: str = Field(min_length=3, max_length=120)
    category: ComplaintCategory
    message: str = Field(min_length=10, max_length=4000)
    document_id: uuid.UUID | None = None


class ComplaintMessageCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ComplaintStatusUpdateRequest(BaseModel):
    status: ComplaintStatus


class ComplaintMessageItem(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    author_role: str
    body: str
    created_at: datetime


class ComplaintSummaryItem(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    user_email: str
    subject: str
    category: str
    status: str
    document_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class ComplaintDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    user_email: str
    subject: str
    category: str
    message: str
    document_id: uuid.UUID | None
    status: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    messages: list[ComplaintMessageItem]


class ComplaintListResponse(BaseModel):
    items: list[ComplaintSummaryItem]
    total: int
    page: int
    page_size: int
