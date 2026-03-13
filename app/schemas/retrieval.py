"""Schemas for retrieval queries and responses."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Valid element types for PEDR syntactic layer
ElementTypeValue = Literal["mission", "document", "insight", "chunk"]
GovernanceMode = Literal["strict", "soft", "warn"]


class RetrievalQuery(BaseModel):
    """Client payload for semantic search."""

    query: str = Field(..., min_length=1, description="Natural language search query.")
    top_k: int = Field(5, ge=1, le=50, description="Number of chunks to return.")
    project_id: UUID | None = Field(None, description="Filter by project UUID.")
    document_id: UUID | None = Field(None, description="Filter by document UUID.")
    source_type: str | None = Field(None, description="Filter by document source type.")
    document_types: list[str] | None = Field(
        default=None,
        description="Optional list of document types to include (e.g., transcript, survey).",
    )
    source_types: list[str] | None = Field(
        default=None,
        description="Optional list of source types to include.",
    )
    date_from: date | None = Field(
        default=None,
        description="Restrict documents collected on/after this date.",
    )
    date_to: date | None = Field(
        default=None,
        description="Restrict documents collected on/before this date.",
    )
    tags: list[str] | None = Field(
        default=None,
        description="Optional list of tag names to match (OR semantics).",
    )
    hnsw_ef: int | None = Field(
        default=None,
        ge=1,
        le=512,
        description="Optional HNSW ef override; defaults to tuned mission latency tiers.",
    )
    min_quality_gates: int | None = Field(
        default=None,
        ge=0,
        le=5,
        description="Minimum number of passing quality gates required for a mission.",
    )
    status: list[str] | None = Field(
        default=None,
        description="Allowed mission statuses (draft, in_progress, review, complete).",
    )
    allow_pii: bool | None = Field(
        default=True,
        description="When False, apply governance handling to PII-flagged missions.",
    )
    governance_mode: GovernanceMode = Field(
        default="strict",
        description="Governance behavior: strict (exclude), soft (penalize), warn (log only).",
    )
    # PEDR syntactic layer parameters
    element_type: ElementTypeValue | None = Field(
        default=None,
        description="Filter by entity type (mission, document, insight, chunk). Auto-detected from query if not specified.",
    )
    element_types: list[ElementTypeValue] | None = Field(
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
    document_id: str | None
    project_id: str | None
    chunk_index: int | None
    source_type: str | None = None
    document_type: str | None = None
    collection_date: date | None = None
    tags: list[str] | None = None
    score: float
    quality_score: float | None = None
    quality_base_score: float | None = None
    quality_boost: float | None = None
    quality_status: str | None = None
    quality_gates_passed: int | None = None
    quality_gates_total: int | None = None
    quality_validated: bool | None = None
    quality_mission_id: str | None = None
    quality_pii_flagged: bool | None = None
    # PEDR syntactic layer fields
    element_type: str | None = None
    element_type_match: bool | None = None
    type_boost: float | None = None


class RetrievalResponse(BaseModel):
    """Response payload containing ranked chunks."""

    results: list[RetrievedChunk]
