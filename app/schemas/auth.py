"""Pydantic schemas for authentication APIs."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
