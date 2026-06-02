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

    display_name: str | None = Field(None, max_length=100, description="New display name")
    current_password: str | None = Field(None, description="Required when changing password")
    new_password: str | None = Field(None, min_length=8, description="New password (minimum 8 characters)")

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("display_name cannot be blank")
        return v


class ProfileResponse(BaseModel):
    """Profile payload for GET/PATCH /auth/me.

    ``role`` is the caller's live, per-request role (decision #226 — never baked
    into the JWT, so a demote/disable takes effect on the next request). This is
    the ONLY channel by which the frontend learns its role (T48.1); the token,
    TokenUser, and StoredAuth deliberately carry no role.
    """

    user_id: UUID
    email: str
    display_name: str
    role: str


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


class AdminUserCreate(BaseModel):
    """Payload for admin-provisioning a user directly (T47.1).

    Lets an admin/owner mint a user at an explicit role without the
    register->demote dance. ``role`` defaults to the least-privilege tier so a
    forgotten role never mints an admin; granting ``owner`` is owner-gated in the
    route, not here. Role validity is checked in the route (400) to share the admin
    API's existing _VALID_ROLES vocabulary and error shape."""

    email: str = Field(..., min_length=3, description="Email address")
    password: str = Field(..., min_length=8, description="Password (minimum 8 characters)")
    display_name: str = Field(..., max_length=100, description="Display name")
    role: str = Field(
        default="member", description="member | viewer | admin | owner | service"
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        # Mirror ProfileUpdate: a whitespace-only display name is not meaningful and
        # the column is NOT NULL with no check constraint, so reject it at the edge.
        v = v.strip()
        if not v:
            raise ValueError("display_name cannot be blank")
        return v


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
