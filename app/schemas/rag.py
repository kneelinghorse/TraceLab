"""Schemas for RAG query requests and responses."""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievalQuery, RetrievedChunk


class RagQuery(RetrievalQuery):
    """Client payload for full RAG query execution."""
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
    document_id: Optional[str]
    chunk_id: Optional[str]
    chunk_index: Optional[int]
    source_type: Optional[str] = None
    score: Optional[float] = None
    snippet: Optional[str] = None


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
    score: Optional[float] = None
    age_seconds: Optional[float] = None
    ttl_seconds: Optional[float] = None


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
    hard_failures: List[str]
    reasons: List[str]
    pre_escalation_score: Optional[float] = None


class RoutingAttempt(BaseModel):
    """Metadata describing a single routing attempt."""
    model: str
    quality_score: float
    below_threshold: bool
    hard_failures: List[str]
    citation_count: int


class RoutingMetrics(BaseModel):
    """Simple counters tracking routing behaviour."""
    total_queries: int
    escalations: int


class RoutingDetails(BaseModel):
    """Routing outcome including whether escalation occurred."""
    selected_model: str
    escalated: bool
    attempts: List[RoutingAttempt]
    estimated_cost_usd: float
    metrics: RoutingMetrics


class RagResponse(BaseModel):
    """Response containing the generated answer alongside supporting metadata."""
    answer: str
    citations: List[RagCitation]
    sources: List[RetrievedChunk]
    latency_ms: float
    compression: CompressionMetrics
    cache: CacheInfo
    quality: QualityReport
    routing: RoutingDetails
