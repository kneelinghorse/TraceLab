"""Pydantic schemas for API key management."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    """Request to create a new API key."""

    name: str = Field(..., description="Human-readable label (e.g., 'MCP Server', 'CI Pipeline')")
    expires_in_days: Optional[int] = Field(
        default=None,
        description="Number of days until the key expires (null = never expires)",
    )


class APIKeyResponse(BaseModel):
    """Response when creating a new API key (includes the full key, shown only once)."""

    id: UUID
    name: str
    key: str = Field(..., description="Full API key - shown only at creation time")
    key_prefix: str = Field(..., description="Key prefix for identification (e.g., tl_a1b2c3d4)")
    created_at: datetime
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


class APIKeyInfo(BaseModel):
    """API key info for listing (excludes the actual key value)."""

    id: UUID
    name: str
    key_prefix: str = Field(..., description="Key prefix for identification (e.g., tl_a1b2c3d4)")
    created_at: datetime
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


class APIKeyList(BaseModel):
    """List of API keys."""

    keys: list[APIKeyInfo]
    total: int


class APIKeyDeleted(BaseModel):
    """Response when deleting an API key."""

    success: bool
    message: str
