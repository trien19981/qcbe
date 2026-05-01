from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserPublic(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    avatar_url: str | None = None

    model_config = {"from_attributes": True}

    @field_validator("role", mode="before")
    @classmethod
    def role_as_str(cls, v: object) -> str:
        return v if isinstance(v, str) else str(v)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LogoutResponse(BaseModel):
    message: str


class MeResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    avatar_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("role", mode="before")
    @classmethod
    def role_as_str(cls, v: object) -> str:
        return v if isinstance(v, str) else str(v)

    @field_validator("is_active", mode="before")
    @classmethod
    def active_default(cls, v: object) -> bool:
        if v is None:
            return True
        return bool(v)
