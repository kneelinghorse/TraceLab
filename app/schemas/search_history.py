"""Schemas for search history APIs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.rag import RagResponse
from app.schemas.retrieval import RetrievalResponse


class SearchHistoryEntry(BaseModel):
    """Search history record returned to clients."""

    id: UUID
    query_text: str
    search_mode: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    result_count: int
    top_k: int
    duration_ms: Optional[int] = None
    cache_hit: bool = False
    user_label: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    top_chunks: List[str] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


class SearchHistoryListResponse(BaseModel):
    """Response payload for list endpoint."""

    entries: List[SearchHistoryEntry]
    retention: Dict[str, int]


class SearchReplayResponse(BaseModel):
    """Response returned when replaying a past search."""

    entry: SearchHistoryEntry
    rag: RagResponse
    semantic: RetrievalResponse
