from datetime import datetime
import uuid

from pydantic import BaseModel, Field


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=80)


class ChangePasswordRequest(BaseModel):
    current: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=1, max_length=256)


class SessionInfoResponse(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    user_agent: str | None
    ip: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    is_current: bool


class SessionListResponse(BaseModel):
    items: list[SessionInfoResponse]
