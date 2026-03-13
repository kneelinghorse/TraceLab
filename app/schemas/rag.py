"""Schemas for RAG query requests and responses."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievalQuery, RetrievedChunk


class RagQuery(RetrievalQuery):
    """Client payload for full RAG query execution."""

    search_mode: Literal["semantic", "keyword", "hybrid"] = Field(
        default="semantic",
        description="Select semantic (vector), keyword (full-text), or hybrid search.",
    )
    max_tokens: int = Field(
        default=350,
        ge=64,
        le=1024,
        description="Maximum number of tokens to generate in the answer.",
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for answer generation.",
    )


class RagCitation(BaseModel):
    """Structured citation extracted from the generated answer."""

    document_id: str | None
    chunk_id: str | None
    chunk_index: int | None
    source_type: str | None = None
    score: float | None = None
    snippet: str | None = None


class CompressionMetrics(BaseModel):
    """Observability metrics for context compression."""

    original_chunks: int
    filtered_chunks: int
    original_tokens: int
    filtered_tokens: int
    reduction_ratio: float
    threshold: float
    compression_ms: float


class CacheInfo(BaseModel):
    """Metadata describing semantic cache evaluation."""

    hit: bool
    score: float | None = None
    age_seconds: float | None = None
    ttl_seconds: float | None = None


class QualityPillarScores(BaseModel):
    """Breakdown of the heuristic pillar scores."""

    linguistic_uncertainty: float
    answer_integrity: float
    source_provenance: float


class QualityReport(BaseModel):
    """Composite quality assessment report."""

    composite_score: float
    threshold: float
    pillar_scores: QualityPillarScores
    hard_failures: list[str]
    reasons: list[str]
    pre_escalation_score: float | None = None


class RoutingAttempt(BaseModel):
    """Metadata describing a single routing attempt."""

    model: str
    quality_score: float
    below_threshold: bool
    hard_failures: list[str]
    citation_count: int


class RoutingMetrics(BaseModel):
    """Simple counters tracking routing behaviour."""

    total_queries: int
    escalations: int


class RoutingDetails(BaseModel):
    """Routing outcome including whether escalation occurred."""

    selected_model: str
    escalated: bool
    attempts: list[RoutingAttempt]
    estimated_cost_usd: float
    metrics: RoutingMetrics


class RagResponse(BaseModel):
    """Response containing the generated answer alongside supporting metadata."""

    answer: str
    citations: list[RagCitation]
    sources: list[RetrievedChunk]
    latency_ms: float
    compression: CompressionMetrics
    cache: CacheInfo
    quality: QualityReport
    routing: RoutingDetails
    search_mode: Literal["semantic", "keyword", "hybrid"]
