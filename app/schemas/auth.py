"""Pydantic schemas for authentication APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TokenUser(BaseModel):
    """Represents the authenticated user returned to the frontend."""

    user_id: UUID = Field(..., description="User UUID")
    email: str = Field(..., description="User email address")
    display_name: str = Field(..., description="User display name")
    username: str | None = Field(None, description="Deprecated: use display_name")


class TokenResponse(BaseModel):
    """Response payload for login and refresh endpoints."""

    access_token: str = Field(..., description="JWT access token to use in Authorization header")
    token_type: Literal["bearer"] = Field(default="bearer")
    expires_in: int = Field(..., description="Token lifetime in seconds")
    user: TokenUser


class LoginRequest(BaseModel):
    """Credentials submitted to the login endpoint."""

    email: str = Field(..., description="Email address")
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class ProfileUpdate(BaseModel):
    """Payload for updating the authenticated user's profile."""

    display_name: Optional[str] = Field(None, max_length=100, description="New display name")
    current_password: Optional[str] = Field(None, description="Required when changing password")
    new_password: Optional[str] = Field(None, min_length=8, description="New password (minimum 8 characters)")

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("display_name cannot be blank")
        return v


class ProfileResponse(BaseModel):
    """Response after a profile update."""

    user_id: UUID
    email: str
    display_name: str


class AdminUserResponse(BaseModel):
    """User representation for the admin user-management API (T43.5)."""

    id: UUID
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    """Payload for user registration."""

    email: str = Field(..., min_length=3, description="Email address")
    password: str = Field(..., min_length=8, description="Password (minimum 8 characters)")
    display_name: str = Field(..., max_length=100, description="Display name")
    invite_code: str = Field(..., min_length=8, max_length=8, description="8-character invite code")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Basic email format validation."""
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v
