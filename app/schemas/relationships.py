"""Pydantic schemas for mission relationship context responses."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RelationshipEdgeInfo(BaseModel):
    """Metadata describing how an entity is related to the mission."""

    relationship_type: str = Field(
        ..., description="Type of relationship, e.g. evidence_chunk"
    )
    evidence_ids: list[str] = Field(default_factory=list)
    summary: str | None = None
    source: str | None = None
    relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)


class RelatedChunk(BaseModel):
    """Chunk relationship surfaced from Mission Protocol evidence."""

    id: UUID
    document_id: UUID
    document_name: str | None = None
    chunk_index: int
    preview: str | None = None
    relationship: RelationshipEdgeInfo


class RelatedDocument(BaseModel):
    """Document relationship built from chunk evidence."""

    id: UUID
    name: str
    file_type: str | None = None
    source_type: str | None = None
    evidence_chunks: int = 0
    chunk_ids: list[UUID] = Field(default_factory=list)
    relationship: RelationshipEdgeInfo


class RelatedInsight(BaseModel):
    """Insight backed by the mission's evidence."""

    id: UUID
    title: str
    insight_type: str | None = None
    validated: bool = False
    relationship: RelationshipEdgeInfo


class RelatedMission(BaseModel):
    """Sibling mission exposed for context."""

    id: UUID
    mission_identifier: str | None = None
    title: str | None = None
    status: str
    completion_percentage: int
    shared_documents: int = 0
    shared_chunks: int = 0
    shared_insights: int = 0
    relationship: RelationshipEdgeInfo


class RelationshipFilters(BaseModel):
    """Normalized filters applied to the relationship request."""

    entity_types: list[str] = Field(default_factory=list)
    min_relevance: float | None = Field(default=None, ge=0.0, le=1.0)


class RelationshipTotals(BaseModel):
    """Aggregate counts used by clients to summarise coverage."""

    documents: int = 0
    insights: int = 0
    chunks: int = 0
    missions: int = 0


class RelationshipContextResponse(BaseModel):
    """Full response payload for relationship lookups."""

    mission_id: UUID
    mission_identifier: str | None = None
    project_id: UUID
    depth: int = Field(..., ge=1, le=2)
    filters: RelationshipFilters
    documents: list[RelatedDocument] = Field(default_factory=list)
    insights: list[RelatedInsight] = Field(default_factory=list)
    chunks: list[RelatedChunk] = Field(default_factory=list)
    related_missions: list[RelatedMission] = Field(default_factory=list)
    totals: RelationshipTotals = Field(default_factory=RelationshipTotals)
    warnings: list[str] = Field(default_factory=list)
    cached: bool = False

    model_config = ConfigDict(populate_by_name=True)
