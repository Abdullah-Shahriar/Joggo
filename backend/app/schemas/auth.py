from datetime import datetime
from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field


PortalType = Literal["doctor", "admin", "auditor"]


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = Field(max_length=320)
    password: str = Field(max_length=256)
    full_name: str = Field(max_length=80)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)
    portal: PortalType | None = None


class GoogleAuthRequest(BaseModel):
    credential: str = Field(min_length=10, max_length=8192)
    portal: PortalType | None = None


class AuthConfigResponse(BaseModel):
    google_client_id: str | None = None


class AuthUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    age: int | None = None
    designation: str | None = None
    hospital_name: str | None = None
    avatar_data_url: str | None = None
    role: str
    status: str
    restricted_reason: str | None
    has_password: bool
    has_google: bool
    created_at: datetime
    last_login_at: datetime | None


class AuthSessionResponse(BaseModel):
    user: AuthUserResponse


class MessageResponse(BaseModel):
    message: str
