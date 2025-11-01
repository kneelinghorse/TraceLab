"""Schemas for retrieval queries and responses."""
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class RetrievalQuery(BaseModel):
    """Client payload for semantic search."""
    query: str = Field(..., min_length=1, description="Natural language search query.")
    top_k: int = Field(5, ge=1, le=50, description="Number of chunks to return.")
    project_id: Optional[UUID] = Field(None, description="Filter by project UUID.")
    document_id: Optional[UUID] = Field(None, description="Filter by document UUID.")
    source_type: Optional[str] = Field(None, description="Filter by document source type.")
    hnsw_ef: Optional[int] = Field(
        default=None,
        ge=1,
        le=512,
        description="Optional HNSW ef override; defaults to tuned mission latency tiers."
    )


class RetrievedChunk(BaseModel):
    """Chunk returned from semantic search."""
    chunk_id: str
    content: str
    document_id: Optional[str]
    project_id: Optional[str]
    chunk_index: Optional[int]
    source_type: Optional[str] = None
    score: float


class RetrievalResponse(BaseModel):
    """Response payload containing ranked chunks."""
    results: List[RetrievedChunk]
