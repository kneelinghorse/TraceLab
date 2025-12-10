"""Schemas for retrieval queries and responses."""
from datetime import date
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


# Valid element types for PEDR syntactic layer
ElementTypeValue = Literal["mission", "document", "insight", "chunk"]


class RetrievalQuery(BaseModel):
    """Client payload for semantic search."""
    query: str = Field(..., min_length=1, description="Natural language search query.")
    top_k: int = Field(5, ge=1, le=50, description="Number of chunks to return.")
    project_id: Optional[UUID] = Field(None, description="Filter by project UUID.")
    document_id: Optional[UUID] = Field(None, description="Filter by document UUID.")
    source_type: Optional[str] = Field(None, description="Filter by document source type.")
    document_types: Optional[List[str]] = Field(
        default=None,
        description="Optional list of document types to include (e.g., transcript, survey).",
    )
    source_types: Optional[List[str]] = Field(
        default=None,
        description="Optional list of source types to include.",
    )
    date_from: Optional[date] = Field(
        default=None,
        description="Restrict documents collected on/after this date.",
    )
    date_to: Optional[date] = Field(
        default=None,
        description="Restrict documents collected on/before this date.",
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Optional list of tag names to match (OR semantics).",
    )
    hnsw_ef: Optional[int] = Field(
        default=None,
        ge=1,
        le=512,
        description="Optional HNSW ef override; defaults to tuned mission latency tiers."
    )
    min_quality_gates: Optional[int] = Field(
        default=None,
        ge=0,
        le=5,
        description="Minimum number of passing quality gates required for a mission.",
    )
    status: Optional[List[str]] = Field(
        default=None,
        description="Allowed mission statuses (draft, in_progress, review, complete).",
    )
    allow_pii: Optional[bool] = Field(
        default=True,
        description="When False, exclude missions flagged for PII handling.",
    )
    # PEDR syntactic layer parameters
    element_type: Optional[ElementTypeValue] = Field(
        default=None,
        description="Filter by entity type (mission, document, insight, chunk). Auto-detected from query if not specified.",
    )
    element_types: Optional[List[ElementTypeValue]] = Field(
        default=None,
        description="Filter by multiple entity types (OR semantics).",
    )
    auto_detect_type: bool = Field(
        default=True,
        description="Auto-detect element type from query phrasing when not explicitly specified.",
    )
    type_boost_enabled: bool = Field(
        default=True,
        description="Apply score boost to results matching detected/specified element type.",
    )


class RetrievedChunk(BaseModel):
    """Chunk returned from semantic search."""
    chunk_id: str
    content: str
    document_id: Optional[str]
    project_id: Optional[str]
    chunk_index: Optional[int]
    source_type: Optional[str] = None
    document_type: Optional[str] = None
    collection_date: Optional[date] = None
    tags: Optional[List[str]] = None
    score: float
    quality_score: Optional[float] = None
    quality_base_score: Optional[float] = None
    quality_boost: Optional[float] = None
    quality_status: Optional[str] = None
    quality_gates_passed: Optional[int] = None
    quality_gates_total: Optional[int] = None
    quality_validated: Optional[bool] = None
    quality_mission_id: Optional[str] = None
    quality_pii_flagged: Optional[bool] = None
    # PEDR syntactic layer fields
    element_type: Optional[str] = None
    element_type_match: Optional[bool] = None
    type_boost: Optional[float] = None


class RetrievalResponse(BaseModel):
    """Response payload containing ranked chunks."""
    results: List[RetrievedChunk]
