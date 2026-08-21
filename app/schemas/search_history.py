"""Schemas for search history APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.rag import RagResponse
from app.schemas.retrieval import RetrievalResponse


class SearchHistoryEntry(BaseModel):
    """Search history record returned to clients."""

    id: UUID
    query_text: str
    search_mode: str
    filters: dict[str, Any] = Field(default_factory=dict)
    result_count: int
    top_k: int
    duration_ms: int | None = None
    cache_hit: bool = False
    owner_id: UUID | None = None
    user_label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    top_chunks: list[str] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


class SearchHistoryListResponse(BaseModel):
    """Response payload for list endpoint."""

    entries: list[SearchHistoryEntry]
    retention: dict[str, int]


class SearchReplayResponse(BaseModel):
    """Response returned when replaying a past search."""

    entry: SearchHistoryEntry
    rag: RagResponse
    semantic: RetrievalResponse
