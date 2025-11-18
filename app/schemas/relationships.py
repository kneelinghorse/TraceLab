"""Pydantic schemas for mission relationship context responses."""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RelationshipEdgeInfo(BaseModel):
    """Metadata describing how an entity is related to the mission."""

    relationship_type: str = Field(..., description="Type of relationship, e.g. evidence_chunk")
    evidence_ids: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    source: Optional[str] = None
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RelatedChunk(BaseModel):
    """Chunk relationship surfaced from Mission Protocol evidence."""

    id: UUID
    document_id: UUID
    document_name: Optional[str] = None
    chunk_index: int
    preview: Optional[str] = None
    relationship: RelationshipEdgeInfo


class RelatedDocument(BaseModel):
    """Document relationship built from chunk evidence."""

    id: UUID
    name: str
    file_type: Optional[str] = None
    source_type: Optional[str] = None
    evidence_chunks: int = 0
    chunk_ids: List[UUID] = Field(default_factory=list)
    relationship: RelationshipEdgeInfo


class RelatedInsight(BaseModel):
    """Insight backed by the mission's evidence."""

    id: UUID
    title: str
    insight_type: Optional[str] = None
    validated: bool = False
    relationship: RelationshipEdgeInfo


class RelatedMission(BaseModel):
    """Sibling mission exposed for context."""

    id: UUID
    mission_identifier: Optional[str] = None
    title: Optional[str] = None
    status: str
    completion_percentage: int
    shared_documents: int = 0
    shared_chunks: int = 0
    shared_insights: int = 0
    relationship: RelationshipEdgeInfo


class RelationshipFilters(BaseModel):
    """Normalized filters applied to the relationship request."""

    entity_types: List[str] = Field(default_factory=list)
    min_relevance: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RelationshipTotals(BaseModel):
    """Aggregate counts used by clients to summarise coverage."""

    documents: int = 0
    insights: int = 0
    chunks: int = 0
    missions: int = 0


class RelationshipContextResponse(BaseModel):
    """Full response payload for relationship lookups."""

    mission_id: UUID
    mission_identifier: Optional[str] = None
    project_id: UUID
    depth: int = Field(..., ge=1, le=2)
    filters: RelationshipFilters
    documents: List[RelatedDocument] = Field(default_factory=list)
    insights: List[RelatedInsight] = Field(default_factory=list)
    chunks: List[RelatedChunk] = Field(default_factory=list)
    related_missions: List[RelatedMission] = Field(default_factory=list)
    totals: RelationshipTotals = Field(default_factory=RelationshipTotals)
    warnings: List[str] = Field(default_factory=list)
    cached: bool = False

    model_config = ConfigDict(populate_by_name=True)
