"""Pydantic schemas for authentication."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8)
    totp_code: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        local, separator, domain = value.strip().lower().partition("@")
        if not separator or not local or "." not in domain or domain.startswith("."):
            raise ValueError("Invalid email address")
        return f"{local}@{domain}"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserMeResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    status: str
    mfa_enabled: bool
    permissions: list[str]
    roles: list[str]
    last_login_at: datetime | None = None


class MfaEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str
    recovery_codes: list[str]


class MfaVerifyRequest(BaseModel):
    totp_code: str
