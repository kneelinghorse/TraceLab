"""Pydantic schemas for authentication APIs."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class TokenUser(BaseModel):
    """Represents the authenticated user returned to the frontend."""

    username: str = Field(..., description="Username associated with the issued token")


class TokenResponse(BaseModel):
    """Response payload for login and refresh endpoints."""

    access_token: str = Field(..., description="JWT access token to use in Authorization header")
    token_type: Literal["bearer"] = Field(default="bearer")
    expires_in: int = Field(..., description="Token lifetime in seconds")
    user: TokenUser


class LoginRequest(BaseModel):
    """Credentials submitted to the login endpoint."""

    username: str
    password: str


class RegisterRequest(BaseModel):
    """Payload for user registration."""

    email: str = Field(..., min_length=3, description="Email address")
    password: str = Field(..., min_length=8, description="Password (minimum 8 characters)")
    display_name: Optional[str] = Field(None, max_length=100, description="Optional display name")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Basic email format validation."""
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v
