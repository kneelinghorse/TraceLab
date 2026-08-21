"""Pydantic models for saved search APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.rag import RagResponse
from app.schemas.retrieval import RetrievalResponse


class SavedSearchBase(BaseModel):
    """Common fields shared by saved search requests."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    query_text: str = Field(..., min_length=1)
    search_mode: str = Field(default="semantic")
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=50)


class SavedSearchCreateRequest(SavedSearchBase):
    """Payload for creating a saved search."""


class SavedSearchUpdateRequest(BaseModel):
    """Payload for updating saved search metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    query_text: str | None = Field(default=None, min_length=1)
    search_mode: str | None = Field(default=None)
    filters: dict[str, Any] | None = Field(default=None)
    top_k: int | None = Field(default=None, ge=1, le=50)


class SavedSearchResponse(SavedSearchBase):
    """Saved search representation returned by the API."""

    id: UUID
    owner_id: UUID | None = None
    owner: str
    use_count: int = 0
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SavedSearchListResponse(BaseModel):
    """List response with per-user quota metadata."""

    items: list[SavedSearchResponse]
    limit_per_user: int


class SavedSearchExecuteResponse(BaseModel):
    """Response payload for executing a saved search."""

    saved_search: SavedSearchResponse
    rag: RagResponse
    semantic: RetrievalResponse
