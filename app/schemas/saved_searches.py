"""Pydantic models for saved search APIs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.rag import RagResponse
from app.schemas.retrieval import RetrievalResponse


class SavedSearchBase(BaseModel):
    """Common fields shared by saved search requests."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    query_text: str = Field(..., min_length=1)
    search_mode: str = Field(default="semantic")
    filters: Dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=50)


class SavedSearchCreateRequest(SavedSearchBase):
    """Payload for creating a saved search."""


class SavedSearchUpdateRequest(BaseModel):
    """Payload for updating saved search metadata."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    query_text: Optional[str] = Field(default=None, min_length=1)
    search_mode: Optional[str] = Field(default=None)
    filters: Optional[Dict[str, Any]] = Field(default=None)
    top_k: Optional[int] = Field(default=None, ge=1, le=50)


class SavedSearchResponse(SavedSearchBase):
    """Saved search representation returned by the API."""

    id: UUID
    owner: str
    use_count: int = 0
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SavedSearchListResponse(BaseModel):
    """List response with per-user quota metadata."""

    items: List[SavedSearchResponse]
    limit_per_user: int


class SavedSearchExecuteResponse(BaseModel):
    """Response payload for executing a saved search."""

    saved_search: SavedSearchResponse
    rag: RagResponse
    semantic: RetrievalResponse
