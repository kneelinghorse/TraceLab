"""Pydantic schemas for authentication APIs."""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TokenUser(BaseModel):
    """Represents the authenticated user returned to the frontend."""

    user_id: UUID = Field(..., description="User UUID")
    email: str = Field(..., description="User email address")
    display_name: str = Field(..., description="User display name")
    username: Optional[str] = Field(None, description="Deprecated: use display_name")


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
