"""Pydantic schemas for PEDR unified search API.

These schemas define the request/response contract for the POST /api/v1/pedr/search
endpoint that orchestrates all 6 PEDR layers (including optional graph expansion)
with RRF fusion.
"""

from datetime import date
from typing import Any, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

# Element types supported by PEDR syntactic layer
PEDRElementType = Literal["mission", "document", "insight", "chunk"]

# Query intents from PEDR pragmatic layer
PEDRQueryIntent = Literal["search", "create", "update", "delete", "execute", "unknown"]

# Rerank mode for hybrid search optimization
PEDRRerankMode = Literal["full", "hybrid"]
PEDRGovernanceMode = Literal["strict", "soft", "warn"]


class PEDRLayerWeights(BaseModel):
    """Configurable weights for each PEDR layer in RRF fusion."""

    lexical: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Weight for lexical (keyword) search layer",
    )
    semantic: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Weight for semantic (vector) search layer",
    )
    syntactic: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Weight for syntactic (type detection) layer",
    )
    pragmatic: float = Field(
        default=0.10, ge=0.0, le=1.0, description="Weight for pragmatic (intent) layer"
    )
    governance: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Weight for governance (quality) layer",
    )


class PEDRSearchRequest(BaseModel):
    """Request payload for PEDR unified search."""

    # Core query
    query: str = Field(
        ..., min_length=1, max_length=2000, description="Natural language search query"
    )
    top_k: int = Field(
        default=10, ge=1, le=100, description="Number of results to return"
    )

    # Standard filters
    project_id: UUID | None = Field(default=None, description="Filter by project UUID")
    document_id: UUID | None = Field(
        default=None, description="Filter by document UUID"
    )
    source_type: str | None = Field(
        default=None, description="Filter by document source type"
    )
    source_origin: str | None = Field(
        default=None,
        description="Filter by document origin: 'upload' (user uploaded), 'synthesized' (from mission/report), 'imported' (external)",
    )
    document_types: list[str] | None = Field(
        default=None, description="Filter by document types (OR semantics)"
    )
    source_types: list[str] | None = Field(
        default=None, description="Filter by source types (OR semantics)"
    )
    date_from: date | None = Field(
        default=None, description="Filter documents from this date"
    )
    date_to: date | None = Field(
        default=None, description="Filter documents up to this date"
    )
    tags: list[str] | None = Field(
        default=None, description="Filter by tags (OR semantics)"
    )

    # Syntactic layer options
    element_type: PEDRElementType | None = Field(
        default=None,
        description="Single element type filter (mission, document, insight, chunk)",
    )
    element_types: list[PEDRElementType] | None = Field(
        default=None,
        description="Multiple element type filters (OR semantics)",
    )
    auto_detect_type: bool = Field(
        default=True,
        description="Auto-detect element type from query phrasing",
    )
    type_boost_enabled: bool = Field(
        default=True,
        description="Boost scores for results matching detected/specified type",
    )

    # Pragmatic layer options
    intent_boost_enabled: bool = Field(
        default=True,
        description="Boost scores based on detected query intent",
    )

    # Governance layer options
    min_quality_gates: int | None = Field(
        default=None,
        ge=0,
        le=5,
        description="Minimum number of passing quality gates required",
    )
    status_filters: list[str] | None = Field(
        default=None,
        description="Allowed mission statuses (draft, in_progress, review, complete)",
    )
    allow_pii: bool = Field(
        default=True,
        description="When False, apply governance handling to PII-flagged content",
    )
    governance_mode: PEDRGovernanceMode = Field(
        default="strict",
        description="Governance behavior: strict (exclude), soft (penalize), warn (log only).",
    )

    # Layer control
    enable_lexical: bool = Field(
        default=True, description="Enable lexical (keyword) search layer"
    )
    enable_semantic: bool = Field(
        default=True, description="Enable semantic (vector) search layer"
    )
    enable_syntactic: bool = Field(
        default=True, description="Enable syntactic type processing"
    )
    enable_pragmatic: bool = Field(
        default=True, description="Enable pragmatic intent processing"
    )
    enable_governance: bool = Field(
        default=True, description="Enable governance quality scoring"
    )

    # Layer weights
    layer_weights: PEDRLayerWeights | None = Field(
        default=None,
        description="Custom weights for each layer in RRF fusion",
    )

    # Advanced options
    hnsw_ef: int | None = Field(
        default=None,
        ge=1,
        le=512,
        description="HNSW ef override for semantic search",
    )

    # Hybrid rerank options (B19.4)
    rerank_mode: PEDRRerankMode = Field(
        default="full",
        description=(
            "Search rerank mode: 'full' for standard semantic search across entire corpus, "
            "'hybrid' for FTS-first with semantic reranking (faster, <300ms target)"
        ),
    )
    candidate_pool: int = Field(
        default=50,
        ge=10,
        le=200,
        description="Number of FTS candidates to retrieve for hybrid reranking (only used when rerank_mode='hybrid')",
    )

    # Graph layer options (L6)
    enable_graph: bool = Field(
        default=False,
        description="Enable graph layer expansion",
    )
    graph_depth: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Max BFS traversal depth",
    )
    graph_decay: float = Field(
        default=0.7,
        ge=0.1,
        le=1.0,
        description="Score decay per hop",
    )
    graph_edge_types: list[str] | None = Field(
        default=None,
        description="Filter to specific graph edge types (None = all)",
    )
    graph_weight: float = Field(
        default=0.08,
        ge=0.0,
        le=0.5,
        description="Graph layer weight in RRF fusion",
    )

    # Graph expansion options (Relational Layer)
    include_related: bool = Field(
        default=False,
        description="Include related entities for each result (graph expansion)",
    )
    max_related_per_result: int = Field(
        default=5,
        ge=0,
        le=20,
        description="Maximum related entities to include per result",
    )

    # Embedding passthrough options (B21.7)
    include_embeddings: bool = Field(
        default=False,
        description="Include embedding vectors in results (for RAG context compression)",
    )

    @model_validator(mode="after")
    def validate_hybrid_candidate_pool(self) -> "PEDRSearchRequest":
        """Ensure hybrid rerank has room to rerank beyond final top_k."""
        if self.rerank_mode == "hybrid" and self.candidate_pool <= self.top_k:
            raise ValueError(
                "candidate_pool must be greater than top_k when rerank_mode='hybrid'."
            )
        return self


class PEDRLayerTimings(BaseModel):
    """Timing information for each PEDR search layer."""

    lexical_ms: float = Field(description="Lexical search latency in milliseconds")
    semantic_ms: float = Field(description="Semantic search latency in milliseconds")
    graph_ms: float = Field(
        default=0.0, description="Graph layer latency in milliseconds"
    )
    syntactic_ms: float = Field(
        description="Syntactic processing latency in milliseconds"
    )
    pragmatic_ms: float = Field(
        description="Pragmatic processing latency in milliseconds"
    )
    governance_ms: float = Field(
        description="Governance scoring latency in milliseconds"
    )
    fusion_ms: float = Field(description="RRF fusion latency in milliseconds")
    relational_ms: float = Field(
        default=0.0, description="Graph expansion latency in milliseconds"
    )
    total_ms: float = Field(description="Total search latency in milliseconds")


# Layer status: ok, error, skipped, disabled
PEDRLayerStatus = Literal["ok", "error", "skipped", "disabled"]


class PEDRLayerDiagnostic(BaseModel):
    """Diagnostic information for a single PEDR layer execution."""

    layer: str = Field(
        description="Layer name (lexical, semantic, graph, syntactic, pragmatic, governance)"
    )
    status: PEDRLayerStatus = Field(description="Layer execution status")
    duration_ms: float = Field(
        default=0.0, ge=0.0, description="Execution time in milliseconds"
    )
    result_count: int = Field(
        default=0, ge=0, description="Number of results produced by this layer"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if status is 'error'"
    )
    error_type: Optional[str] = Field(
        default=None, description="Exception class name if status is 'error'"
    )


class PEDRSearchMetadata(BaseModel):
    """Metadata about PEDR search execution."""

    query: str = Field(description="Original search query")
    intent: PEDRQueryIntent = Field(description="Detected query intent")
    intent_confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in intent classification"
    )
    detected_type: PEDRElementType | None = Field(
        description="Auto-detected element type (if any)"
    )
    type_confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in type detection"
    )
    layers_used: list[str] = Field(
        description="List of layers that contributed results"
    )
    layer_weights: dict[str, float] = Field(description="Effective layer weights used")
    timings: PEDRLayerTimings = Field(description="Per-layer timing information")
    layer_diagnostics: List[PEDRLayerDiagnostic] = Field(
        default_factory=list,
        description="Per-layer execution diagnostics (timing, status, result count, errors)",
    )
    degraded: bool = Field(
        default=False,
        description="True if one or more layers failed but partial results were returned",
    )
    graph_enabled: bool = Field(
        default=False, description="True if graph layer was enabled"
    )
    graph_candidates_expanded: int | None = Field(
        default=None,
        ge=0,
        description="Number of graph candidates expanded when graph layer enabled",
    )
    total_candidates: int = Field(
        ge=0, description="Total unique candidates before final ranking"
    )
    result_count: int = Field(ge=0, description="Number of results returned")
    rerank_mode: PEDRRerankMode | None = Field(
        default=None,
        description="Rerank mode used for this search (full or hybrid)",
    )
    hybrid_fallback_used: bool = Field(
        default=False,
        description="True if hybrid mode fell back to full semantic (FTS returned no candidates)",
    )


class PEDRSearchResult(BaseModel):
    """A single result from PEDR unified search."""

    # Core identification
    chunk_id: str = Field(description="Unique chunk identifier")
    content: str = Field(description="Chunk text content")
    document_id: str | None = Field(default=None, description="Parent document ID")
    project_id: str | None = Field(default=None, description="Associated project ID")

    # PEDR scores
    rrf_score: float = Field(ge=0.0, description="Final RRF fusion score")
    rrf_rank: int = Field(ge=1, description="Final rank after fusion")
    layer_ranks: dict[str, int] = Field(
        default_factory=dict,
        description="Rank in each contributing layer (0 if not present)",
    )
    layer_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Original score from each contributing layer",
    )

    # Semantic Protocol metadata
    urn: str | None = Field(
        default=None, description="URN identifier (urn:research:{type}:{id})"
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Bayesian confidence score"
    )
    criticality: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Criticality score"
    )

    # Layer annotations
    element_type: str | None = Field(default=None, description="Inferred element type")
    query_intent: str | None = Field(
        default=None, description="Query intent applied to this result"
    )
    quality_score: float = Field(
        default=1.0, ge=0.0, description="Quality gate score multiplier"
    )
    quality_status: str | None = Field(
        default=None, description="Associated mission status"
    )
    quality_gates_passed: int = Field(
        default=0, ge=0, description="Number of quality gates passed"
    )

    # Provenance
    contributing_layers: list[str] = Field(
        default_factory=list,
        description="Layers that found this result",
    )

    # Chunk metadata
    chunk_index: int | None = Field(
        default=None, ge=0, description="Position in parent document"
    )
    source_type: str | None = Field(default=None, description="Document source type")
    source_origin: str | None = Field(
        default=None,
        description="Document origin: 'upload', 'synthesized', or 'imported'",
    )

    # Compatibility aliases
    score: float = Field(
        default=0.0, description="Alias for rrf_score (backward compatibility)"
    )
    combined_score: float = Field(
        default=0.0, description="Alias for rrf_score (backward compatibility)"
    )

    # Embedding vector (populated when include_embeddings=true)
    embedding: list[float] | None = Field(
        default=None,
        description="Embedding vector for this chunk (when include_embeddings=true)",
    )

    # Graph expansion (populated when include_related=true)
    related_entities: list[dict[str, Any]] | None = Field(
        default=None,
        description="Related entities from graph expansion (when include_related=true)",
    )


class PEDRSearchResponse(BaseModel):
    """Response payload from PEDR unified search."""

    results: list[PEDRSearchResult] = Field(description="Ranked search results")
    metadata: PEDRSearchMetadata = Field(description="Search execution metadata")


# Convenience types for API documentation
PEDRSearchQuery = PEDRSearchRequest  # Alias


__all__ = [
    "PEDRElementType",
    "PEDRQueryIntent",
    "PEDRRerankMode",
    "PEDRLayerStatus",
    "PEDRLayerWeights",
    "PEDRSearchRequest",
    "PEDRLayerTimings",
    "PEDRLayerDiagnostic",
    "PEDRSearchMetadata",
    "PEDRSearchResult",
    "PEDRSearchResponse",
    "PEDRSearchQuery",
]
