"""PEDR Search Orchestrator - coordinates all 5 search layers with RRF fusion.

This module implements the unified PEDR search orchestration, combining:
1. Lexical layer (PostgreSQL full-text search)
2. Semantic layer (Qdrant vector search)
3. Syntactic layer (type detection and filtering)
4. Pragmatic layer (intent classification)
5. Governance layer (quality scoring and PII handling)

Results are fused using Reciprocal Rank Fusion (RRF) for robust ranking
across heterogeneous retrieval methods.

Includes query result caching for latency optimization (B19.2):
- Cache hit: <100ms response time
- Cache miss: Full search pipeline executed
- Auto-invalidation on document changes

Reference: PEDR Protocol Architecture Guide
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from app.services.pedr.fusion import (
    LayerResult,
    RRFFusion,
    get_rrf_fusion,
)
from app.services.pedr.pragmatic import (
    PragmaticFilters,
    PragmaticService,
    QueryIntent,
    get_pragmatic_service,
)
from app.services.pedr.quality_scoring import (
    QualityFilters,
    QualityScoringService,
    get_quality_scoring_service,
)
from app.services.pedr.semantic_protocol import (
    SemanticProtocol,
    get_semantic_protocol,
)
from app.services.pedr.syntactic import (
    ElementType,
    SyntacticFilters,
    SyntacticService,
    get_syntactic_service,
)
from app.services.pedr.cache import (
    CacheStats,
    get_pedr_cache,
)

logger = logging.getLogger(__name__)


# Default layer weights for RRF (sum to 1.0 for interpretability)
DEFAULT_LAYER_WEIGHTS = {
    "lexical": 0.25,
    "semantic": 0.35,
    "syntactic": 0.15,
    "pragmatic": 0.10,
    "governance": 0.15,
}


@dataclass(frozen=True)
class PEDRConfig:
    """Configuration for PEDR search orchestration."""

    # Layer weights for RRF fusion
    layer_weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_LAYER_WEIGHTS))

    # RRF constant (k parameter)
    rrf_k: int = 60

    # Layer enablement flags
    enable_lexical: bool = True
    enable_semantic: bool = True
    enable_syntactic: bool = True
    enable_pragmatic: bool = True
    enable_governance: bool = True

    # Search parameters
    top_k_per_layer: int = 20  # Fetch more per layer, fuse down to top_k
    result_multiplier: int = 3

    # Quality filters
    min_quality_gates: Optional[int] = None
    status_filters: Optional[Tuple[str, ...]] = None
    allow_pii: bool = True

    # Syntactic layer
    auto_detect_type: bool = True
    type_boost_enabled: bool = True
    element_type: Optional[str] = None
    element_types: Optional[Tuple[str, ...]] = None

    # Pragmatic layer
    intent_boost_enabled: bool = True


@dataclass
class LayerTimings:
    """Timing information for each search layer."""

    lexical_ms: float = 0.0
    semantic_ms: float = 0.0
    syntactic_ms: float = 0.0
    pragmatic_ms: float = 0.0
    governance_ms: float = 0.0
    fusion_ms: float = 0.0
    relational_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class PEDRMetadata:
    """Metadata about PEDR search execution."""

    query: str
    intent: str
    intent_confidence: float
    detected_type: Optional[str]
    type_confidence: float
    layers_used: List[str]
    layer_weights: Dict[str, float]
    timings: LayerTimings
    total_candidates: int
    result_count: int
    cache_hit: bool = False
    cache_stats: Optional[Dict[str, Any]] = None


@dataclass
class PEDRSearchResult:
    """Single result from PEDR search."""

    # Core identification
    chunk_id: str
    content: str
    document_id: Optional[str] = None
    project_id: Optional[str] = None

    # Scores
    rrf_score: float = 0.0
    rrf_rank: int = 0
    layer_ranks: Dict[str, int] = field(default_factory=dict)
    layer_scores: Dict[str, float] = field(default_factory=dict)

    # Semantic Protocol metadata
    urn: Optional[str] = None
    confidence: float = 0.5
    criticality: float = 0.5

    # Layer annotations
    element_type: Optional[str] = None
    query_intent: Optional[str] = None
    quality_score: float = 1.0
    quality_status: Optional[str] = None
    quality_gates_passed: int = 0

    # Contributing layers
    contributing_layers: List[str] = field(default_factory=list)

    # Original chunk metadata
    chunk_index: Optional[int] = None
    source_type: Optional[str] = None

    # Graph expansion (populated by API layer when include_related=True)
    related_entities: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "document_id": self.document_id,
            "project_id": self.project_id,
            "rrf_score": self.rrf_score,
            "rrf_rank": self.rrf_rank,
            "layer_ranks": self.layer_ranks,
            "layer_scores": self.layer_scores,
            "urn": self.urn,
            "confidence": self.confidence,
            "criticality": self.criticality,
            "element_type": self.element_type,
            "query_intent": self.query_intent,
            "quality_score": self.quality_score,
            "quality_status": self.quality_status,
            "quality_gates_passed": self.quality_gates_passed,
            "contributing_layers": self.contributing_layers,
            "chunk_index": self.chunk_index,
            "source_type": self.source_type,
            "score": self.rrf_score,  # Alias for compatibility
            "combined_score": self.rrf_score,
        }
        if self.related_entities is not None:
            result["related_entities"] = self.related_entities
        return result


@dataclass
class PEDRSearchResponse:
    """Response from PEDR unified search."""

    results: List[PEDRSearchResult]
    metadata: PEDRMetadata

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        metadata_dict = {
            "query": self.metadata.query,
            "intent": self.metadata.intent,
            "intent_confidence": self.metadata.intent_confidence,
            "detected_type": self.metadata.detected_type,
            "type_confidence": self.metadata.type_confidence,
            "layers_used": self.metadata.layers_used,
            "layer_weights": self.metadata.layer_weights,
            "timings": {
                "lexical_ms": self.metadata.timings.lexical_ms,
                "semantic_ms": self.metadata.timings.semantic_ms,
                "syntactic_ms": self.metadata.timings.syntactic_ms,
                "pragmatic_ms": self.metadata.timings.pragmatic_ms,
                "governance_ms": self.metadata.timings.governance_ms,
                "fusion_ms": self.metadata.timings.fusion_ms,
                "relational_ms": self.metadata.timings.relational_ms,
                "total_ms": self.metadata.timings.total_ms,
            },
            "total_candidates": self.metadata.total_candidates,
            "result_count": self.metadata.result_count,
            "cache_hit": self.metadata.cache_hit,
        }
        if self.metadata.cache_stats is not None:
            metadata_dict["cache_stats"] = self.metadata.cache_stats
        return {
            "results": [r.to_dict() for r in self.results],
            "metadata": metadata_dict,
        }


class PEDRSearchOrchestrator:
    """Orchestrates PEDR multi-layer search with RRF fusion.

    The orchestrator coordinates:
    1. Lexical search (PostgreSQL full-text)
    2. Semantic search (Qdrant vectors)
    3. Syntactic processing (type detection/filtering)
    4. Pragmatic processing (intent classification)
    5. Governance scoring (quality gates, PII)

    Results are fused using Reciprocal Rank Fusion (RRF).
    """

    def __init__(
        self,
        *,
        config: Optional[PEDRConfig] = None,
        syntactic_service: Optional[SyntacticService] = None,
        pragmatic_service: Optional[PragmaticService] = None,
        quality_service: Optional[QualityScoringService] = None,
        semantic_protocol: Optional[SemanticProtocol] = None,
        rrf_fusion: Optional[RRFFusion] = None,
        # External search providers (injected)
        lexical_search: Optional[Callable[..., List[Dict[str, Any]]]] = None,
        semantic_search: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    ) -> None:
        """Initialize the PEDR search orchestrator.

        Args:
            config: PEDR configuration. Defaults to standard config.
            syntactic_service: Type detection service.
            pragmatic_service: Intent classification service.
            quality_service: Quality scoring service.
            semantic_protocol: Semantic Protocol service for URN/confidence.
            rrf_fusion: RRF fusion instance.
            lexical_search: Callable for lexical search. Injected from HybridSearchService.
            semantic_search: Callable for semantic search. Injected from RetrievalService.
        """
        self.config = config or PEDRConfig()
        self.syntactic_service = syntactic_service or get_syntactic_service()
        self.pragmatic_service = pragmatic_service or get_pragmatic_service()
        self.quality_service = quality_service or get_quality_scoring_service()
        self.semantic_protocol = semantic_protocol or get_semantic_protocol()
        self.rrf_fusion = rrf_fusion or get_rrf_fusion()

        # External search providers - will be set by factory or injection
        self._lexical_search = lexical_search
        self._semantic_search = semantic_search

    def search(
        self,
        *,
        query: str,
        top_k: int = 10,
        project_id: Optional[str] = None,
        document_id: Optional[str] = None,
        source_type: Optional[str] = None,
        document_types: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        tags: Optional[List[str]] = None,
        hnsw_ef: Optional[int] = None,
        # PEDR-specific parameters
        element_type: Optional[str] = None,
        element_types: Optional[List[str]] = None,
        auto_detect_type: Optional[bool] = None,
        type_boost_enabled: Optional[bool] = None,
        intent_boost_enabled: Optional[bool] = None,
        min_quality_gates: Optional[int] = None,
        status_filters: Optional[List[str]] = None,
        allow_pii: Optional[bool] = None,
        # Layer control
        enable_lexical: Optional[bool] = None,
        enable_semantic: Optional[bool] = None,
        enable_syntactic: Optional[bool] = None,
        enable_pragmatic: Optional[bool] = None,
        enable_governance: Optional[bool] = None,
        layer_weights: Optional[Dict[str, float]] = None,
    ) -> PEDRSearchResponse:
        """Execute PEDR unified search across all layers.

        Args:
            query: Natural language search query.
            top_k: Number of results to return.
            project_id: Filter by project UUID.
            document_id: Filter by document UUID.
            source_type: Filter by source type.
            document_types: Filter by document types.
            source_types: Filter by source types.
            date_from: Filter documents from this date.
            date_to: Filter documents up to this date.
            tags: Filter by tags (OR semantics).
            hnsw_ef: HNSW ef override for semantic search.
            element_type: Single element type filter.
            element_types: Multiple element type filters.
            auto_detect_type: Auto-detect element type from query.
            type_boost_enabled: Enable type-based score boost.
            intent_boost_enabled: Enable intent-based score boost.
            min_quality_gates: Minimum passing quality gates.
            status_filters: Allowed mission statuses.
            allow_pii: Allow PII-flagged content.
            enable_*: Layer enablement overrides.
            layer_weights: Custom layer weights for RRF.

        Returns:
            PEDRSearchResponse with fused results and metadata.
        """
        start_time = time.perf_counter()
        timings = LayerTimings()

        # Build cache filter key from all search parameters
        from app.core.config import settings as app_settings

        cache_filters = {
            "project_id": project_id,
            "document_id": document_id,
            "source_type": source_type,
            "document_types": tuple(document_types) if document_types else None,
            "source_types": tuple(source_types) if source_types else None,
            "date_from": str(date_from) if date_from else None,
            "date_to": str(date_to) if date_to else None,
            "tags": tuple(tags) if tags else None,
            "element_type": element_type,
            "element_types": tuple(element_types) if element_types else None,
        }

        # Check cache first (if enabled)
        cache = get_pedr_cache()
        cache_enabled = getattr(app_settings, "pedr_cache_enabled", True)

        if cache_enabled:
            cached_response = cache.get(query, top_k, cache_filters)
            if cached_response is not None:
                # Cache hit - return cached response with updated timing
                timings.total_ms = (time.perf_counter() - start_time) * 1000
                cache_stats = cache.get_stats().to_dict()
                logger.debug(
                    "PEDR cache hit for query '%s' in %.2fms",
                    query[:50],
                    timings.total_ms,
                )
                return self._build_cached_response(
                    cached_response,
                    query=query,
                    timings=timings,
                    cache_stats=cache_stats,
                )

        # Cache miss - execute full search pipeline
        # Merge config with runtime overrides
        config = self._merge_config(
            element_type=element_type,
            element_types=element_types,
            auto_detect_type=auto_detect_type,
            type_boost_enabled=type_boost_enabled,
            intent_boost_enabled=intent_boost_enabled,
            min_quality_gates=min_quality_gates,
            status_filters=status_filters,
            allow_pii=allow_pii,
            enable_lexical=enable_lexical,
            enable_semantic=enable_semantic,
            enable_syntactic=enable_syntactic,
            enable_pragmatic=enable_pragmatic,
            enable_governance=enable_governance,
            layer_weights=layer_weights,
        )

        # Phase 1: Pre-analysis (syntactic and pragmatic)
        t0 = time.perf_counter()
        syntactic_filters = self._analyze_syntactic(query, config)
        timings.syntactic_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        pragmatic_filters = self._analyze_pragmatic(query, config)
        timings.pragmatic_ms = (time.perf_counter() - t0) * 1000

        # Phase 2: Execute retrieval layers
        layer_results: List[LayerResult] = []
        fetch_count = max(top_k, config.top_k_per_layer) * config.result_multiplier

        search_params = {
            "query": query,
            "top_k": fetch_count,
            "project_id": project_id,
            "document_id": document_id,
            "source_type": source_type,
            "document_types": document_types,
            "source_types": source_types,
            "date_from": date_from,
            "date_to": date_to,
            "tags": tags,
            "hnsw_ef": hnsw_ef,
        }

        # Lexical layer
        if config.enable_lexical and self._lexical_search:
            t0 = time.perf_counter()
            try:
                lexical_results = self._lexical_search(**search_params)
                timings.lexical_ms = (time.perf_counter() - t0) * 1000
                if lexical_results:
                    layer_results.append(
                        LayerResult(
                            layer_name="lexical",
                            results=lexical_results,
                            weight=config.layer_weights.get("lexical", 0.25),
                            latency_ms=timings.lexical_ms,
                        )
                    )
            except Exception as e:
                logger.warning("Lexical search failed: %s", e)
                timings.lexical_ms = (time.perf_counter() - t0) * 1000

        # Semantic layer
        if config.enable_semantic and self._semantic_search:
            t0 = time.perf_counter()
            try:
                semantic_results = self._semantic_search(**search_params)
                timings.semantic_ms = (time.perf_counter() - t0) * 1000
                if semantic_results:
                    layer_results.append(
                        LayerResult(
                            layer_name="semantic",
                            results=semantic_results,
                            weight=config.layer_weights.get("semantic", 0.35),
                            latency_ms=timings.semantic_ms,
                        )
                    )
            except Exception as e:
                logger.warning("Semantic search failed: %s", e)
                timings.semantic_ms = (time.perf_counter() - t0) * 1000

        # Phase 3: Fuse results with RRF
        t0 = time.perf_counter()
        if layer_results:
            fusion_output = self.rrf_fusion.fuse(
                layer_results,
                id_key="chunk_id",
                limit=fetch_count,
            )
            fused_results = [r.data for r in fusion_output.results]
            for i, fused in enumerate(fusion_output.results):
                fused_results[i]["rrf_score"] = fused.rrf_score
                fused_results[i]["rrf_rank"] = fused.rank
                fused_results[i]["layer_ranks"] = fused.layer_ranks
                fused_results[i]["layer_scores"] = fused.layer_scores
                fused_results[i]["contributing_layers"] = fused.contributing_layers
        else:
            fused_results = []
        timings.fusion_ms = (time.perf_counter() - t0) * 1000

        # Phase 4: Apply post-processing layers
        processed = fused_results

        # Syntactic boost
        if config.enable_syntactic and processed:
            processed = self.syntactic_service.apply(
                processed,
                filters=syntactic_filters,
                filter_mode=False,
            )

        # Pragmatic boost
        if config.enable_pragmatic and processed:
            processed = self.pragmatic_service.apply(processed, filters=pragmatic_filters)

        # Governance scoring
        if config.enable_governance and processed:
            t0 = time.perf_counter()
            quality_filters = QualityFilters(
                min_quality_gates=config.min_quality_gates,
                statuses=tuple(config.status_filters or ()),
                allow_pii=config.allow_pii,
            )
            processed = self.quality_service.apply(processed, filters=quality_filters)
            timings.governance_ms = (time.perf_counter() - t0) * 1000

        # Phase 5: Final ranking and enrichment
        final_results = self._finalize_results(
            processed,
            top_k=top_k,
            syntactic_filters=syntactic_filters,
            pragmatic_filters=pragmatic_filters,
        )

        timings.total_ms = (time.perf_counter() - start_time) * 1000

        # Build response
        cache_stats = cache.get_stats().to_dict() if cache_enabled else None
        metadata = PEDRMetadata(
            query=query,
            intent=pragmatic_filters.intent.value,
            intent_confidence=pragmatic_filters.confidence,
            detected_type=(
                syntactic_filters.detected_type.value
                if syntactic_filters.detected_type
                else None
            ),
            type_confidence=syntactic_filters.detection_confidence,
            layers_used=[lr.layer_name for lr in layer_results],
            layer_weights=dict(config.layer_weights),
            timings=timings,
            total_candidates=len(fused_results),
            result_count=len(final_results),
            cache_hit=False,
            cache_stats=cache_stats,
        )

        response = PEDRSearchResponse(results=final_results, metadata=metadata)

        # Store results in cache for future requests
        if cache_enabled and final_results:
            # Convert results to cacheable format (list of dicts)
            cacheable_results = [r.to_dict() for r in final_results]
            cache.set(query, top_k, cache_filters, cacheable_results)
            logger.debug(
                "PEDR cache stored for query '%s' (%d results)",
                query[:50],
                len(final_results),
            )

        return response

    def _merge_config(self, **overrides: Any) -> PEDRConfig:
        """Merge runtime overrides with base config."""
        base = self.config
        return PEDRConfig(
            layer_weights=overrides.get("layer_weights") or dict(base.layer_weights),
            rrf_k=base.rrf_k,
            enable_lexical=(
                overrides.get("enable_lexical")
                if overrides.get("enable_lexical") is not None
                else base.enable_lexical
            ),
            enable_semantic=(
                overrides.get("enable_semantic")
                if overrides.get("enable_semantic") is not None
                else base.enable_semantic
            ),
            enable_syntactic=(
                overrides.get("enable_syntactic")
                if overrides.get("enable_syntactic") is not None
                else base.enable_syntactic
            ),
            enable_pragmatic=(
                overrides.get("enable_pragmatic")
                if overrides.get("enable_pragmatic") is not None
                else base.enable_pragmatic
            ),
            enable_governance=(
                overrides.get("enable_governance")
                if overrides.get("enable_governance") is not None
                else base.enable_governance
            ),
            top_k_per_layer=base.top_k_per_layer,
            result_multiplier=base.result_multiplier,
            min_quality_gates=(
                overrides.get("min_quality_gates")
                if overrides.get("min_quality_gates") is not None
                else base.min_quality_gates
            ),
            status_filters=(
                tuple(overrides.get("status_filters"))
                if overrides.get("status_filters")
                else base.status_filters
            ),
            allow_pii=(
                overrides.get("allow_pii")
                if overrides.get("allow_pii") is not None
                else base.allow_pii
            ),
            auto_detect_type=(
                overrides.get("auto_detect_type")
                if overrides.get("auto_detect_type") is not None
                else base.auto_detect_type
            ),
            type_boost_enabled=(
                overrides.get("type_boost_enabled")
                if overrides.get("type_boost_enabled") is not None
                else base.type_boost_enabled
            ),
            element_type=overrides.get("element_type") or base.element_type,
            element_types=(
                tuple(overrides.get("element_types"))
                if overrides.get("element_types")
                else base.element_types
            ),
            intent_boost_enabled=(
                overrides.get("intent_boost_enabled")
                if overrides.get("intent_boost_enabled") is not None
                else base.intent_boost_enabled
            ),
        )

    def _analyze_syntactic(
        self,
        query: str,
        config: PEDRConfig,
    ) -> SyntacticFilters:
        """Run syntactic analysis on the query."""
        return self.syntactic_service.create_filters(
            element_type=config.element_type,
            element_types=list(config.element_types) if config.element_types else None,
            query=query,
            auto_detect=config.auto_detect_type,
            type_boost_enabled=config.type_boost_enabled,
        )

    def _analyze_pragmatic(
        self,
        query: str,
        config: PEDRConfig,
    ) -> PragmaticFilters:
        """Run pragmatic analysis on the query."""
        return self.pragmatic_service.create_filters(
            query=query,
            intent_boost_enabled=config.intent_boost_enabled,
        )

    def _finalize_results(
        self,
        results: List[Dict[str, Any]],
        *,
        top_k: int,
        syntactic_filters: SyntacticFilters,
        pragmatic_filters: PragmaticFilters,
    ) -> List[PEDRSearchResult]:
        """Finalize and structure results for response."""
        # Re-sort by combined_score (includes all boosts)
        sorted_results = sorted(
            results,
            key=lambda x: float(x.get("combined_score") or x.get("rrf_score") or 0.0),
            reverse=True,
        )[:top_k]

        final: List[PEDRSearchResult] = []
        for i, r in enumerate(sorted_results, start=1):
            # Generate URN if we have enough info
            chunk_id = r.get("chunk_id", "")
            document_id = r.get("document_id")
            urn = None
            if chunk_id:
                urn = self.semantic_protocol.generate_urn("chunk", chunk_id)

            final.append(
                PEDRSearchResult(
                    chunk_id=str(chunk_id),
                    content=r.get("content", ""),
                    document_id=str(document_id) if document_id else None,
                    project_id=str(r.get("project_id")) if r.get("project_id") else None,
                    rrf_score=float(r.get("rrf_score") or r.get("combined_score") or 0.0),
                    rrf_rank=i,
                    layer_ranks=r.get("layer_ranks", {}),
                    layer_scores=r.get("layer_scores", {}),
                    urn=urn,
                    confidence=float(r.get("quality_score") or 0.5),
                    criticality=0.5,  # Would need full entity for proper calc
                    element_type=r.get("element_type"),
                    query_intent=pragmatic_filters.intent.value,
                    quality_score=float(r.get("quality_score") or 1.0),
                    quality_status=r.get("quality_status"),
                    quality_gates_passed=int(r.get("quality_gates_passed") or 0),
                    contributing_layers=r.get("contributing_layers", []),
                    chunk_index=r.get("chunk_index"),
                    source_type=r.get("source_type"),
                )
            )

        return final

    def _build_cached_response(
        self,
        cached_results: List[Dict[str, Any]],
        *,
        query: str,
        timings: LayerTimings,
        cache_stats: Dict[str, Any],
    ) -> PEDRSearchResponse:
        """Build a PEDRSearchResponse from cached result dictionaries.

        Args:
            cached_results: List of result dictionaries from cache.
            query: Original query string.
            timings: Timing information (mostly just total_ms for cache hits).
            cache_stats: Current cache statistics.

        Returns:
            PEDRSearchResponse built from cached data.
        """
        # Reconstruct PEDRSearchResult objects from cached dicts
        results: List[PEDRSearchResult] = []
        for r in cached_results:
            results.append(
                PEDRSearchResult(
                    chunk_id=r.get("chunk_id", ""),
                    content=r.get("content", ""),
                    document_id=r.get("document_id"),
                    project_id=r.get("project_id"),
                    rrf_score=float(r.get("rrf_score") or r.get("score") or 0.0),
                    rrf_rank=int(r.get("rrf_rank") or 0),
                    layer_ranks=r.get("layer_ranks", {}),
                    layer_scores=r.get("layer_scores", {}),
                    urn=r.get("urn"),
                    confidence=float(r.get("confidence") or 0.5),
                    criticality=float(r.get("criticality") or 0.5),
                    element_type=r.get("element_type"),
                    query_intent=r.get("query_intent"),
                    quality_score=float(r.get("quality_score") or 1.0),
                    quality_status=r.get("quality_status"),
                    quality_gates_passed=int(r.get("quality_gates_passed") or 0),
                    contributing_layers=r.get("contributing_layers", []),
                    chunk_index=r.get("chunk_index"),
                    source_type=r.get("source_type"),
                )
            )

        # Build metadata for cache hit
        # Use cached values for intent/type detection if available
        first_result = cached_results[0] if cached_results else {}
        metadata = PEDRMetadata(
            query=query,
            intent=first_result.get("query_intent", "unknown"),
            intent_confidence=0.0,  # Not re-computed on cache hit
            detected_type=first_result.get("element_type"),
            type_confidence=0.0,  # Not re-computed on cache hit
            layers_used=[],  # Not applicable for cache hits
            layer_weights={},
            timings=timings,
            total_candidates=len(results),
            result_count=len(results),
            cache_hit=True,
            cache_stats=cache_stats,
        )

        return PEDRSearchResponse(results=results, metadata=metadata)


# Singleton instance
_pedr_orchestrator: Optional[PEDRSearchOrchestrator] = None


def get_pedr_orchestrator() -> PEDRSearchOrchestrator:
    """Return singleton PEDR orchestrator.

    Note: This returns a basic orchestrator without search providers.
    Use create_pedr_orchestrator() for a fully functional instance.
    """
    global _pedr_orchestrator
    if _pedr_orchestrator is None:
        _pedr_orchestrator = PEDRSearchOrchestrator()
    return _pedr_orchestrator


def create_pedr_orchestrator(
    *,
    lexical_search: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    semantic_search: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    config: Optional[PEDRConfig] = None,
) -> PEDRSearchOrchestrator:
    """Create a fully configured PEDR orchestrator.

    This factory function wires up the orchestrator with actual search
    providers from the existing services.

    Args:
        lexical_search: Keyword search callable.
        semantic_search: Semantic search callable.
        config: Optional PEDR configuration.

    Returns:
        Configured PEDRSearchOrchestrator.
    """
    # Import here to avoid circular dependencies
    from app.services.hybrid_search import get_hybrid_search_service
    from app.services.retrieval_service import get_retrieval_service

    hybrid_service = get_hybrid_search_service()
    retrieval_service = get_retrieval_service()

    # Create wrapper for lexical search
    def _lexical_wrapper(
        query: str,
        top_k: int = 20,
        project_id: Optional[str] = None,
        document_id: Optional[str] = None,
        source_type: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        from app.services.faceted_search import FacetFilters

        filters = FacetFilters.from_kwargs(
            project_id=project_id,
            source_type=source_type,
            **{k: v for k, v in kwargs.items() if k in ("document_types", "source_types", "date_from", "date_to", "tags")},
        )
        return hybrid_service._keyword_search(
            query=query,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            filters=filters,
            limit=top_k,
        )

    # Create wrapper for semantic search
    def _semantic_wrapper(
        query: str,
        top_k: int = 20,
        project_id: Optional[str] = None,
        document_id: Optional[str] = None,
        source_type: Optional[str] = None,
        document_types: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        tags: Optional[List[str]] = None,
        hnsw_ef: Optional[int] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        return retrieval_service.search(
            query=query,
            top_k=top_k,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            document_types=document_types,
            source_types=source_types,
            date_from=date_from,
            date_to=date_to,
            tags=tags,
            hnsw_ef=hnsw_ef,
        )

    return PEDRSearchOrchestrator(
        config=config,
        lexical_search=lexical_search or _lexical_wrapper,
        semantic_search=semantic_search or _semantic_wrapper,
    )


__all__ = [
    "PEDRConfig",
    "LayerTimings",
    "PEDRMetadata",
    "PEDRSearchResult",
    "PEDRSearchResponse",
    "PEDRSearchOrchestrator",
    "get_pedr_orchestrator",
    "create_pedr_orchestrator",
    "DEFAULT_LAYER_WEIGHTS",
]
