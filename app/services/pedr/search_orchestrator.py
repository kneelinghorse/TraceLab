"""PEDR Search Orchestrator - coordinates all 6 search layers with RRF fusion.

This module implements the unified PEDR search orchestration, combining:
1. Lexical layer (PostgreSQL full-text search)
2. Semantic layer (Qdrant vector search)
3. Graph layer (graph expansion from retrieval seeds)
4. Syntactic layer (type detection and filtering)
5. Pragmatic layer (intent classification)
6. Governance layer (quality scoring and PII handling)

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
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from app.core.config import settings
from app.services.pedr.fusion import (
    LayerResult,
    RRFFusion,
    get_rrf_fusion,
)
from app.services.pedr.graph_layer import (
    GraphLayerConfig,
    GraphLayerService,
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

GRAPH_TELEMETRY_ENV = "PEDR_GRAPH_TELEMETRY_ENABLED"
GRAPH_TELEMETRY_PATH = Path("cmos/telemetry/events/sprint-26-graph-telemetry.jsonl")

BASE_LAYER_WEIGHTS = {
    "lexical": 0.25,
    "semantic": 0.35,
    "syntactic": 0.15,
    "pragmatic": 0.10,
    "governance": 0.15,
}

DEFAULT_GRAPH_WEIGHT = 0.08


def _build_default_layer_weights(graph_weight: float) -> Dict[str, float]:
    scale = max(0.0, 1.0 - graph_weight)
    weights = {layer: weight * scale for layer, weight in BASE_LAYER_WEIGHTS.items()}
    weights["graph"] = graph_weight
    return weights


# Default layer weights for RRF (sum to 1.0 for interpretability)
DEFAULT_LAYER_WEIGHTS = _build_default_layer_weights(DEFAULT_GRAPH_WEIGHT)


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
    enable_graph: bool = False

    # Search parameters
    top_k_per_layer: int = 20  # Fetch more per layer, fuse down to top_k
    result_multiplier: int = field(
        default_factory=lambda: max(1, settings.pedr_candidate_multiplier),
    )

    # Quality filters
    min_quality_gates: Optional[int] = None
    status_filters: Optional[Tuple[str, ...]] = None
    allow_pii: bool = True
    governance_mode: str = "strict"

    # Syntactic layer
    auto_detect_type: bool = True
    type_boost_enabled: bool = True
    element_type: Optional[str] = None
    element_types: Optional[Tuple[str, ...]] = None

    # Pragmatic layer
    intent_boost_enabled: bool = True

    # Graph layer
    graph_weight: float = DEFAULT_GRAPH_WEIGHT
    graph_depth: int = 1
    graph_decay: float = 0.7
    graph_edge_types: Optional[Tuple[str, ...]] = None
    graph_top_k_seeds: int = 5


@dataclass
class LayerTimings:
    """Timing information for each search layer."""

    lexical_ms: float = 0.0
    semantic_ms: float = 0.0
    graph_ms: float = 0.0
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
    graph_enabled: bool = False
    graph_candidates_expanded: Optional[int] = None
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
    source_origin: Optional[str] = None

    # Embedding vector (populated when include_embeddings=True)
    embedding: Optional[List[float]] = None

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
            "source_origin": self.source_origin,
            "score": self.rrf_score,  # Alias for compatibility
            "combined_score": self.rrf_score,
        }
        if self.embedding is not None:
            result["embedding"] = self.embedding
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
                "graph_ms": self.metadata.timings.graph_ms,
                "syntactic_ms": self.metadata.timings.syntactic_ms,
                "pragmatic_ms": self.metadata.timings.pragmatic_ms,
                "governance_ms": self.metadata.timings.governance_ms,
                "fusion_ms": self.metadata.timings.fusion_ms,
                "relational_ms": self.metadata.timings.relational_ms,
                "total_ms": self.metadata.timings.total_ms,
            },
            "graph_enabled": self.metadata.graph_enabled,
            "graph_candidates_expanded": self.metadata.graph_candidates_expanded,
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
    3. Graph expansion (graph adjacency traversal)
    4. Syntactic processing (type detection/filtering)
    5. Pragmatic processing (intent classification)
    6. Governance scoring (quality gates, PII)

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
        graph_service: Optional[GraphLayerService] = None,
        # External search providers (injected)
        lexical_search: Optional[Callable[..., List[Dict[str, Any]]]] = None,
        semantic_search: Optional[Callable[..., List[Dict[str, Any]]]] = None,
        telemetry_enabled: Optional[bool] = None,
        telemetry_path: Optional[Path | str] = None,
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
            telemetry_enabled: Enable graph telemetry logging.
            telemetry_path: Optional override path for graph telemetry JSONL.
        """
        self.config = config or PEDRConfig()
        self.syntactic_service = syntactic_service or get_syntactic_service()
        self.pragmatic_service = pragmatic_service or get_pragmatic_service()
        self.quality_service = quality_service or get_quality_scoring_service()
        self.semantic_protocol = semantic_protocol or get_semantic_protocol()
        self.rrf_fusion = rrf_fusion or get_rrf_fusion()
        self.graph_service = graph_service or GraphLayerService()
        self.telemetry_enabled = (
            telemetry_enabled
            if telemetry_enabled is not None
            else _telemetry_enabled_from_env()
        )
        self.telemetry_path = Path(telemetry_path) if telemetry_path else GRAPH_TELEMETRY_PATH

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
        source_origin: Optional[str] = None,
        document_types: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        tags: Optional[List[str]] = None,
        hnsw_ef: Optional[int] = None,
        include_embeddings: bool = False,
        # PEDR-specific parameters
        element_type: Optional[str] = None,
        element_types: Optional[List[str]] = None,
        auto_detect_type: Optional[bool] = None,
        type_boost_enabled: Optional[bool] = None,
        intent_boost_enabled: Optional[bool] = None,
        min_quality_gates: Optional[int] = None,
        status_filters: Optional[List[str]] = None,
        allow_pii: Optional[bool] = None,
        governance_mode: Optional[str] = None,
        # Layer control
        enable_lexical: Optional[bool] = None,
        enable_semantic: Optional[bool] = None,
        enable_syntactic: Optional[bool] = None,
        enable_pragmatic: Optional[bool] = None,
        enable_governance: Optional[bool] = None,
        enable_graph: Optional[bool] = None,
        layer_weights: Optional[Dict[str, float]] = None,
        graph_weight: Optional[float] = None,
        graph_depth: Optional[int] = None,
        graph_decay: Optional[float] = None,
        graph_edge_types: Optional[List[str]] = None,
        graph_top_k_seeds: Optional[int] = None,
    ) -> PEDRSearchResponse:
        """Execute PEDR unified search across all layers.

        Args:
            query: Natural language search query.
            top_k: Number of results to return.
            project_id: Filter by project UUID.
            document_id: Filter by document UUID.
            source_type: Filter by source type.
            source_origin: Filter by source origin (upload, synthesized, imported).
            document_types: Filter by document types.
            source_types: Filter by source types.
            date_from: Filter documents from this date.
            date_to: Filter documents up to this date.
            tags: Filter by tags (OR semantics).
            hnsw_ef: HNSW ef override for semantic search.
            include_embeddings: Include embedding vectors in results (for RAG context compression).
            element_type: Single element type filter.
            element_types: Multiple element type filters.
            auto_detect_type: Auto-detect element type from query.
            type_boost_enabled: Enable type-based score boost.
            intent_boost_enabled: Enable intent-based score boost.
            min_quality_gates: Minimum passing quality gates.
            status_filters: Allowed mission statuses.
            allow_pii: Allow PII-flagged content.
            governance_mode: Governance behavior (strict, soft, warn).
            enable_*: Layer enablement overrides.
            enable_graph: Enable graph expansion layer.
            layer_weights: Custom layer weights for RRF.
            graph_weight: Weight for graph layer in RRF fusion.
            graph_depth: Maximum graph traversal depth.
            graph_decay: Score decay per hop in graph traversal.
            graph_edge_types: Optional edge types to include (None = all).
            graph_top_k_seeds: Number of top retrieval results to use as graph seeds.

        Returns:
            PEDRSearchResponse with fused results and metadata.
        """
        start_time = time.perf_counter()
        timings = LayerTimings()
        graph_layer_result = None
        fusion_output = None

        # Merge config with runtime overrides (used for cache keys and execution)
        config = self._merge_config(
            element_type=element_type,
            element_types=element_types,
            auto_detect_type=auto_detect_type,
            type_boost_enabled=type_boost_enabled,
            intent_boost_enabled=intent_boost_enabled,
            min_quality_gates=min_quality_gates,
            status_filters=status_filters,
            allow_pii=allow_pii,
            governance_mode=governance_mode,
            enable_lexical=enable_lexical,
            enable_semantic=enable_semantic,
            enable_syntactic=enable_syntactic,
            enable_pragmatic=enable_pragmatic,
            enable_governance=enable_governance,
            enable_graph=enable_graph,
            layer_weights=layer_weights,
            graph_weight=graph_weight,
            graph_depth=graph_depth,
            graph_decay=graph_decay,
            graph_edge_types=graph_edge_types,
            graph_top_k_seeds=graph_top_k_seeds,
        )
        effective_layer_weights = self._resolve_layer_weights(
            config=config,
            graph_weight_override=graph_weight,
        )

        # Build cache filter key from all search parameters
        from app.core.config import settings as app_settings

        cache_filters = {
            "project_id": project_id,
            "document_id": document_id,
            "source_type": source_type,
            "source_origin": source_origin,
            "document_types": tuple(document_types) if document_types else None,
            "source_types": tuple(source_types) if source_types else None,
            "date_from": str(date_from) if date_from else None,
            "date_to": str(date_to) if date_to else None,
            "tags": tuple(tags) if tags else None,
            "element_type": element_type,
            "element_types": tuple(element_types) if element_types else None,
            "include_embeddings": include_embeddings,
            "min_quality_gates": config.min_quality_gates,
            "status_filters": tuple(config.status_filters or ()),
            "allow_pii": config.allow_pii,
            "governance_mode": config.governance_mode,
            "enable_graph": config.enable_graph,
            "graph_weight": effective_layer_weights.get("graph"),
            "graph_depth": config.graph_depth,
            "graph_decay": config.graph_decay,
            "graph_edge_types": config.graph_edge_types,
            "graph_top_k_seeds": config.graph_top_k_seeds,
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
                    graph_enabled=config.enable_graph,
                )

        # Cache miss - execute full search pipeline

        # Phase 1: Pre-analysis (syntactic and pragmatic)
        t0 = time.perf_counter()
        syntactic_filters = self._analyze_syntactic(query, config)
        timings.syntactic_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        pragmatic_filters = self._analyze_pragmatic(query, config)
        timings.pragmatic_ms = (time.perf_counter() - t0) * 1000

        # Phase 2: Execute retrieval layers
        layer_results: List[LayerResult] = []
        lexical_results: List[Dict[str, Any]] = []
        semantic_results: List[Dict[str, Any]] = []
        graph_candidates_expanded: Optional[int] = None
        fetch_multiplier = max(1, config.result_multiplier)
        fetch_count = max(top_k, config.top_k_per_layer) * fetch_multiplier

        search_params = {
            "query": query,
            "top_k": fetch_count,
            "project_id": project_id,
            "document_id": document_id,
            "source_type": source_type,
            "source_origin": source_origin,
            "document_types": document_types,
            "source_types": source_types,
            "date_from": date_from,
            "date_to": date_to,
            "tags": tags,
            "hnsw_ef": hnsw_ef,
            "include_embeddings": include_embeddings,
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
                            weight=effective_layer_weights.get(
                                "lexical",
                                BASE_LAYER_WEIGHTS["lexical"],
                            ),
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
                            weight=effective_layer_weights.get(
                                "semantic",
                                BASE_LAYER_WEIGHTS["semantic"],
                            ),
                            latency_ms=timings.semantic_ms,
                        )
                    )
            except Exception as e:
                logger.warning("Semantic search failed: %s", e)
                timings.semantic_ms = (time.perf_counter() - t0) * 1000

        # Graph layer (between retrieval and fusion)
        if config.enable_graph and self.graph_service:
            t0 = time.perf_counter()
            try:
                seed_results = _interleave_results(lexical_results, semantic_results)
                graph_layer = self.graph_service.expand_from_results(
                    seed_results,
                    top_k=config.graph_top_k_seeds,
                    config=GraphLayerConfig(
                        max_depth=config.graph_depth,
                        decay_factor=config.graph_decay,
                        allowed_edge_types=config.graph_edge_types,
                    ),
                )
                graph_layer_result = graph_layer
                timings.graph_ms = graph_layer.latency_ms or (
                    (time.perf_counter() - t0) * 1000
                )
                graph_layer.weight = effective_layer_weights.get(
                    "graph",
                    config.graph_weight,
                )
                layer_results.append(graph_layer)
                graph_candidates_expanded = int(
                    (graph_layer.metadata or {}).get("total_candidates") or 0
                )
                _log_graph_layer_metrics(graph_layer)
            except Exception as e:
                logger.warning("Graph search failed: %s", e)
                timings.graph_ms = (time.perf_counter() - t0) * 1000
                graph_candidates_expanded = 0

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
                governance_mode=config.governance_mode,
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
            layer_weights=dict(effective_layer_weights),
            timings=timings,
            graph_enabled=config.enable_graph,
            graph_candidates_expanded=graph_candidates_expanded,
            total_candidates=len(fused_results),
            result_count=len(final_results),
            cache_hit=False,
            cache_stats=cache_stats,
        )

        response = PEDRSearchResponse(results=final_results, metadata=metadata)

        if (
            self.telemetry_enabled
            and graph_layer_result is not None
            and fusion_output is not None
        ):
            _emit_graph_telemetry(
                query=query,
                config=config,
                layer_weights=effective_layer_weights,
                graph_layer=graph_layer_result,
                fusion_output=fusion_output,
                final_results=final_results,
                timings=timings,
                graph_candidates_expanded=graph_candidates_expanded,
                telemetry_path=self.telemetry_path,
            )

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
        layer_weights = dict(base.layer_weights)
        override_weights = overrides.get("layer_weights")
        if override_weights is not None:
            layer_weights.update(override_weights)
        return PEDRConfig(
            layer_weights=layer_weights,
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
            enable_graph=(
                overrides.get("enable_graph")
                if overrides.get("enable_graph") is not None
                else base.enable_graph
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
            governance_mode=(
                overrides.get("governance_mode")
                if overrides.get("governance_mode") is not None
                else base.governance_mode
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
            graph_weight=(
                overrides.get("graph_weight")
                if overrides.get("graph_weight") is not None
                else base.graph_weight
            ),
            graph_depth=(
                overrides.get("graph_depth")
                if overrides.get("graph_depth") is not None
                else base.graph_depth
            ),
            graph_decay=(
                overrides.get("graph_decay")
                if overrides.get("graph_decay") is not None
                else base.graph_decay
            ),
            graph_edge_types=(
                tuple(overrides.get("graph_edge_types"))
                if overrides.get("graph_edge_types") is not None
                else base.graph_edge_types
            ),
            graph_top_k_seeds=(
                overrides.get("graph_top_k_seeds")
                if overrides.get("graph_top_k_seeds") is not None
                else base.graph_top_k_seeds
            ),
        )

    def _resolve_layer_weights(
        self,
        *,
        config: PEDRConfig,
        graph_weight_override: Optional[float],
    ) -> Dict[str, float]:
        weights = dict(DEFAULT_LAYER_WEIGHTS)
        weights.update(config.layer_weights)

        if config.enable_graph:
            if graph_weight_override is not None:
                weights["graph"] = config.graph_weight
            else:
                weights.setdefault("graph", config.graph_weight)
        else:
            weights["graph"] = 0.0

        enabled_layers = {
            "lexical": config.enable_lexical,
            "semantic": config.enable_semantic,
            "syntactic": config.enable_syntactic,
            "pragmatic": config.enable_pragmatic,
            "governance": config.enable_governance,
            "graph": config.enable_graph,
        }

        normalized: Dict[str, float] = {}
        total = 0.0
        for layer, enabled in enabled_layers.items():
            weight = float(weights.get(layer, 0.0))
            if not enabled:
                weight = 0.0
            normalized[layer] = weight
            total += weight

        if total > 0:
            normalized = {layer: weight / total for layer, weight in normalized.items()}

        return normalized

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
                    source_origin=r.get("source_origin"),
                    embedding=r.get("embedding"),
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
        graph_enabled: bool = False,
        graph_candidates_expanded: Optional[int] = None,
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
                    source_origin=r.get("source_origin"),
                    embedding=r.get("embedding"),
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
            graph_enabled=graph_enabled,
            graph_candidates_expanded=graph_candidates_expanded,
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
        source_origin: Optional[str] = None,
        document_types: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        tags: Optional[List[str]] = None,
        hnsw_ef: Optional[int] = None,
        include_embeddings: bool = False,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        return retrieval_service.search(
            query=query,
            top_k=top_k,
            project_id=project_id,
            document_id=document_id,
            source_type=source_type,
            source_origin=source_origin,
            document_types=document_types,
            source_types=source_types,
            date_from=date_from,
            date_to=date_to,
            tags=tags,
            hnsw_ef=hnsw_ef,
            include_embeddings=include_embeddings,
        )

    return PEDRSearchOrchestrator(
        config=config,
        lexical_search=lexical_search or _lexical_wrapper,
        semantic_search=semantic_search or _semantic_wrapper,
    )


def _interleave_results(*result_sets: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    combined: List[Dict[str, Any]] = []
    max_len = max((len(results) for results in result_sets), default=0)
    for idx in range(max_len):
        for results in result_sets:
            if idx < len(results):
                combined.append(results[idx])
    return combined


def _log_graph_layer_metrics(graph_layer: LayerResult) -> None:
    metadata = graph_layer.metadata or {}
    total_candidates = metadata.get("total_candidates")
    seed_count = metadata.get("seed_count")
    cache_hits = int(metadata.get("cache_hits", 0) or 0)
    cache_misses = int(metadata.get("cache_misses", 0) or 0)
    cache_total = cache_hits + cache_misses
    cache_hit_rate = (cache_hits / cache_total) if cache_total > 0 else None

    if total_candidates is None and cache_total == 0:
        return

    cache_hit_rate_text = "n/a"
    if cache_hit_rate is not None:
        cache_hit_rate_text = f"{cache_hit_rate:.2f}"

    logger.debug(
        "Graph layer expanded %s candidates from %s seeds in %.2fms (adjacency cache hit rate %s)",
        total_candidates if total_candidates is not None else 0,
        seed_count if seed_count is not None else 0,
        graph_layer.latency_ms,
        cache_hit_rate_text,
    )


def _telemetry_enabled_from_env() -> bool:
    value = os.getenv(GRAPH_TELEMETRY_ENV, "1").strip().lower()
    return value not in {"0", "false", "no"}


def _summarize_scores(scores: Sequence[float]) -> Dict[str, float]:
    values = [float(value) for value in scores if value is not None]
    if not values:
        return {}
    values.sort()
    count = len(values)
    mid = count // 2
    if count % 2 == 1:
        median = values[mid]
    else:
        median = (values[mid - 1] + values[mid]) / 2
    p90_index = int(0.9 * (count - 1))
    return {
        "min": round(values[0], 6),
        "max": round(values[-1], 6),
        "avg": round(sum(values) / count, 6),
        "p50": round(median, 6),
        "p90": round(values[p90_index], 6),
    }


def _compute_graph_impact(
    results: Sequence[PEDRSearchResult],
    *,
    graph_weight: float,
    rrf_k: int,
) -> Dict[str, Any]:
    total = len(results)
    if total == 0:
        return {
            "results_with_graph": 0,
            "result_share": 0.0,
            "rank_stats": {},
            "rrf_contribution_stats": {},
            "rrf_contribution_share_stats": {},
            "top_5_with_graph": 0,
            "top_5_share": 0.0,
        }

    graph_ranks: List[float] = []
    graph_contribs: List[float] = []
    graph_shares: List[float] = []

    for result in results:
        rank = (result.layer_ranks or {}).get("graph", 0)
        if rank > 0:
            contrib = graph_weight * (1.0 / (rrf_k + rank))
            graph_contribs.append(contrib)
            graph_ranks.append(float(result.rrf_rank))
            if result.rrf_score:
                graph_shares.append(contrib / result.rrf_score)

    top_n = min(5, total)
    top_5_with_graph = sum(
        1
        for result in results[:top_n]
        if (result.layer_ranks or {}).get("graph", 0) > 0
    )
    return {
        "results_with_graph": len(graph_ranks),
        "result_share": round(len(graph_ranks) / total, 4),
        "rank_stats": _summarize_scores(graph_ranks),
        "rrf_contribution_stats": _summarize_scores(graph_contribs),
        "rrf_contribution_share_stats": _summarize_scores(graph_shares),
        "top_5_with_graph": top_5_with_graph,
        "top_5_share": round(top_5_with_graph / top_n, 4) if top_n > 0 else 0.0,
    }


def _emit_graph_telemetry(
    *,
    query: str,
    config: PEDRConfig,
    layer_weights: Dict[str, float],
    graph_layer: LayerResult,
    fusion_output: Any,
    final_results: Sequence[PEDRSearchResult],
    timings: LayerTimings,
    graph_candidates_expanded: Optional[int],
    telemetry_path: Path,
) -> None:
    metadata = graph_layer.metadata or {}
    cache_hits = int(metadata.get("cache_hits") or 0)
    cache_misses = int(metadata.get("cache_misses") or 0)
    cache_total = cache_hits + cache_misses
    cache_hit_rate = (
        round(cache_hits / cache_total, 4) if cache_total > 0 else None
    )
    graph_weight = float(layer_weights.get("graph", config.graph_weight))

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "pedr_graph_telemetry",
        "query": query,
        "graph": {
            "depth": config.graph_depth,
            "decay": config.graph_decay,
            "edge_types": list(config.graph_edge_types or ()),
            "top_k_seeds": config.graph_top_k_seeds,
            "weight": graph_weight,
            "seed_count": metadata.get("seed_count"),
            "seed_score_stats": metadata.get("seed_score_stats", {}),
            "depth_stats": metadata.get("depth_stats", {}),
            "edge_type_usage": metadata.get("edge_type_usage", {}),
            "total_candidates": metadata.get("total_candidates"),
            "graph_candidates_expanded": graph_candidates_expanded,
            "cache": {
                "hits": cache_hits,
                "misses": cache_misses,
                "hit_rate": cache_hit_rate,
            },
        },
        "rrf": {
            "k": config.rrf_k,
            "layers_used": fusion_output.layers_used,
            "total_unique": fusion_output.total_unique,
            "fusion_latency_ms": fusion_output.fusion_latency_ms,
            "layer_weights": dict(layer_weights),
            "telemetry": fusion_output.telemetry,
        },
        "ranking": {
            "final_result_count": len(final_results),
            "graph_impact": _compute_graph_impact(
                final_results,
                graph_weight=graph_weight,
                rrf_k=config.rrf_k,
            ),
        },
        "timings": {
            "graph_ms": timings.graph_ms,
            "fusion_ms": timings.fusion_ms,
            "total_ms": timings.total_ms,
        },
    }

    try:
        telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        with telemetry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except Exception as exc:  # pragma: no cover - telemetry best effort
        logger.warning("Failed to write graph telemetry: %s", exc)


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
