"""PEDR Unified Search API endpoint.

POST /api/v1/pedr/search - Execute PEDR search across all 5 layers with RRF fusion.

This is the primary search interface for TraceLab, replacing/complementing the
legacy RAG search endpoint with full Protocol-Enhanced Deep Research capabilities.

Supports two rerank modes (B19.4):
- full: Standard semantic search across entire corpus (default)
- hybrid: FTS-first with semantic reranking (<300ms target latency)
"""
import asyncio
import logging
import time
from functools import lru_cache
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthenticatedUser, require_authenticated_user
from app.schemas.pedr_search import (
    PEDRSearchRequest,
    PEDRSearchResponse,
    PEDRSearchResult,
    PEDRSearchMetadata,
    PEDRLayerTimings,
)
from app.services.pedr import QualityFilters, get_quality_scoring_service
from app.services.pedr.hybrid_rerank import get_hybrid_reranker
from app.services.pedr.relational import get_relational_service
from app.services.pedr.search_orchestrator import create_pedr_orchestrator

router = APIRouter()
logger = logging.getLogger(__name__)
INTERNAL_ERROR_DETAIL = "Search failed due to an internal error."


@lru_cache(maxsize=1)
def _get_pedr_orchestrator():
    """Reuse one orchestrator instance across requests."""
    return create_pedr_orchestrator()


@router.post("/pedr/search", response_model=PEDRSearchResponse)
async def pedr_search(
    payload: PEDRSearchRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> PEDRSearchResponse:
    """Execute PEDR unified search across all 5 layers.

    PEDR (Protocol-Enhanced Deep Research) search combines:
    - Lexical layer: PostgreSQL full-text search
    - Semantic layer: Qdrant vector similarity
    - Syntactic layer: Element type detection and filtering
    - Pragmatic layer: Query intent classification
    - Governance layer: Quality gates and PII handling

    Results are fused using Reciprocal Rank Fusion (RRF) for robust ranking.

    Supports two rerank modes (B19.4):
    - full: Standard 5-layer PEDR search (default)
    - hybrid: FTS-first with semantic reranking (<300ms target)

    Args:
        payload: PEDR search request parameters

    Returns:
        PEDRSearchResponse with ranked results and execution metadata
    """
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query text must not be empty.")

    try:
        # Use hybrid reranker for "hybrid" mode (B19.4)
        if payload.rerank_mode == "hybrid":
            return await _execute_hybrid_search(payload, current_user)

        # Standard PEDR search for "full" mode
        orchestrator = _get_pedr_orchestrator()

        # Build layer weights dict if provided
        layer_weights = None
        if payload.layer_weights:
            layer_weights = {
                "lexical": payload.layer_weights.lexical,
                "semantic": payload.layer_weights.semantic,
                "syntactic": payload.layer_weights.syntactic,
                "pragmatic": payload.layer_weights.pragmatic,
                "governance": payload.layer_weights.governance,
            }

        # Execute PEDR search
        result = await asyncio.to_thread(
            orchestrator.search,
            query=payload.query,
            top_k=payload.top_k,
            project_id=str(payload.project_id) if payload.project_id else None,
            document_id=str(payload.document_id) if payload.document_id else None,
            source_type=payload.source_type,
            source_origin=payload.source_origin,
            document_types=payload.document_types,
            source_types=payload.source_types,
            date_from=payload.date_from,
            date_to=payload.date_to,
            tags=payload.tags,
            hnsw_ef=payload.hnsw_ef,
            include_embeddings=payload.include_embeddings,
            element_type=payload.element_type,
            element_types=list(payload.element_types) if payload.element_types else None,
            auto_detect_type=payload.auto_detect_type,
            type_boost_enabled=payload.type_boost_enabled,
            intent_boost_enabled=payload.intent_boost_enabled,
            min_quality_gates=payload.min_quality_gates,
            status_filters=payload.status_filters,
            allow_pii=payload.allow_pii,
            governance_mode=payload.governance_mode,
            enable_lexical=payload.enable_lexical,
            enable_semantic=payload.enable_semantic,
            enable_syntactic=payload.enable_syntactic,
            enable_pragmatic=payload.enable_pragmatic,
            enable_governance=payload.enable_governance,
            layer_weights=layer_weights,
            enable_graph=payload.enable_graph,
            graph_depth=payload.graph_depth,
            graph_decay=payload.graph_decay,
            graph_edge_types=payload.graph_edge_types,
            graph_weight=payload.graph_weight,
        )

        # Apply graph expansion if requested
        relational_ms = 0.0
        if payload.include_related:
            t0 = time.perf_counter()
            relational_service = get_relational_service()
            for search_result in result.results:
                if search_result.urn:
                    try:
                        expansion = relational_service.get_related(
                            search_result.urn,
                            max_depth=1,
                            limit=payload.max_related_per_result,
                        )
                        # Store as dict for serialization
                        search_result.related_entities = [
                            e.to_dict() for e in expansion.related_entities
                        ]
                    except Exception as e:
                        logger.warning(
                            "Failed to expand relations for %s: %s",
                            search_result.urn,
                            e,
                        )
                        search_result.related_entities = []
                else:
                    search_result.related_entities = []
            relational_ms = (time.perf_counter() - t0) * 1000
            result.metadata.timings.relational_ms = relational_ms

        # Convert internal response to Pydantic models
        response = _convert_to_response(
            result,
            include_related=payload.include_related,
            rerank_mode="full",
        )

        logger.info(
            "PEDR search completed: query=%r, mode=full, results=%d, latency=%.1fms, relational=%.1fms, user=%s",
            payload.query[:50],
            len(response.results),
            response.metadata.timings.total_ms,
            relational_ms,
            current_user.username,
        )

        return response

    except ValueError as e:
        logger.warning("PEDR search validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("PEDR search failed: %s", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL)


async def _execute_hybrid_search(
    payload: PEDRSearchRequest,
    current_user: AuthenticatedUser,
) -> PEDRSearchResponse:
    """Execute hybrid FTS+semantic rerank search (B19.4).

    This provides faster search latency (<300ms target) by:
    1. Using PostgreSQL FTS to retrieve candidate pool
    2. Reranking candidates using semantic similarity

    Args:
        payload: Search request parameters.
        current_user: Authenticated user.

    Returns:
        PEDRSearchResponse with hybrid search results.
    """
    reranker = get_hybrid_reranker()

    hybrid_result = await asyncio.to_thread(
        reranker.search,
        query=payload.query,
        top_k=payload.top_k,
        candidate_pool=payload.candidate_pool,
        mode="hybrid",
        project_id=str(payload.project_id) if payload.project_id else None,
        document_id=str(payload.document_id) if payload.document_id else None,
        source_type=payload.source_type,
        source_origin=payload.source_origin,
        hnsw_ef=payload.hnsw_ef,
        include_embeddings=payload.include_embeddings,
    )

    governance_ms = 0.0
    hybrid_payloads = hybrid_result.results
    if payload.enable_governance:
        t0 = time.perf_counter()
        quality_service = get_quality_scoring_service()
        quality_filters = QualityFilters(
            min_quality_gates=payload.min_quality_gates,
            statuses=tuple(payload.status_filters or ()),
            allow_pii=payload.allow_pii,
            governance_mode=payload.governance_mode,
        )
        hybrid_payloads = await asyncio.to_thread(
            quality_service.apply,
            hybrid_payloads,
            filters=quality_filters,
        )
        hybrid_payloads = sorted(
            hybrid_payloads,
            key=lambda item: float(
                item.get("score")
                or item.get("combined_score")
                or item.get("semantic_score")
                or item.get("fts_score")
                or 0.0
            ),
            reverse=True,
        )[: payload.top_k]
        governance_ms = (time.perf_counter() - t0) * 1000

    # Build response from hybrid results
    results = []
    for i, r in enumerate(hybrid_payloads, start=1):
        result = PEDRSearchResult(
            chunk_id=r.get("chunk_id", ""),
            content=r.get("content", ""),
            document_id=r.get("document_id"),
            project_id=r.get("project_id"),
            rrf_score=float(r.get("score") or r.get("semantic_score") or 0.0),
            rrf_rank=i,
            layer_ranks={"fts": i, "semantic": i},  # Simplified for hybrid mode
            layer_scores={
                "fts": float(r.get("fts_score") or 0.0),
                "semantic": float(r.get("semantic_score") or 0.0),
            },
            urn=None,  # URN generation skipped in hybrid mode for speed
            confidence=0.5,
            criticality=0.5,
            element_type=None,
            query_intent=None,
            quality_score=float(r.get("quality_score") or 1.0),
            quality_status=r.get("quality_status"),
            quality_gates_passed=int(r.get("quality_gates_passed") or 0),
            contributing_layers=["fts", "semantic"] + (["governance"] if payload.enable_governance else []),
            chunk_index=r.get("chunk_index"),
            source_type=r.get("source_type"),
            source_origin=r.get("source_origin"),
            score=float(r.get("score") or r.get("semantic_score") or 0.0),
            combined_score=float(r.get("combined_score") or r.get("semantic_score") or 0.0),
            embedding=r.get("embedding"),
            related_entities=None,
        )
        results.append(result)

    # Build timings from hybrid result
    timings = PEDRLayerTimings(
        lexical_ms=hybrid_result.timings.fts_ms,
        semantic_ms=hybrid_result.timings.embedding_ms + hybrid_result.timings.rerank_ms,
        graph_ms=0.0,
        syntactic_ms=0.0,
        pragmatic_ms=0.0,
        governance_ms=governance_ms,
        fusion_ms=0.0,
        relational_ms=0.0,
        total_ms=hybrid_result.timings.total_ms + governance_ms,
    )

    metadata = PEDRSearchMetadata(
        query=payload.query,
        intent="search",
        intent_confidence=0.0,
        detected_type=None,
        type_confidence=0.0,
        layers_used=["fts", "semantic"] + (["governance"] if payload.enable_governance else []),
        layer_weights={"fts": 0.0, "semantic": 1.0, "governance": 0.0},
        timings=timings,
        graph_enabled=False,
        graph_candidates_expanded=None,
        total_candidates=hybrid_result.fts_candidates_count,
        result_count=len(results),
        rerank_mode="hybrid",
        hybrid_fallback_used=hybrid_result.fallback_used,
    )

    response = PEDRSearchResponse(results=results, metadata=metadata)

    logger.info(
        "PEDR search completed: query=%r, mode=hybrid, results=%d, "
        "fts_candidates=%d, latency=%.1fms (fts=%.1fms, rerank=%.1fms), "
        "fallback=%s, user=%s",
        payload.query[:50],
        len(results),
        hybrid_result.fts_candidates_count,
        hybrid_result.timings.total_ms,
        hybrid_result.timings.fts_ms,
        hybrid_result.timings.rerank_ms,
        hybrid_result.fallback_used,
        current_user.username,
    )

    return response


def _convert_to_response(
    internal_result: Any,
    *,
    include_related: bool = False,
    rerank_mode: str = "full",
) -> PEDRSearchResponse:
    """Convert internal PEDRSearchResponse to Pydantic schema."""
    # The internal result is already well-structured, just need to map to Pydantic

    results = []
    for r in internal_result.results:
        result = PEDRSearchResult(
            chunk_id=r.chunk_id,
            content=r.content,
            document_id=r.document_id,
            project_id=r.project_id,
            rrf_score=r.rrf_score,
            rrf_rank=r.rrf_rank,
            layer_ranks=r.layer_ranks,
            layer_scores=r.layer_scores,
            urn=r.urn,
            confidence=r.confidence,
            criticality=r.criticality,
            element_type=r.element_type,
            query_intent=r.query_intent,
            quality_score=r.quality_score,
            quality_status=r.quality_status,
            quality_gates_passed=r.quality_gates_passed,
            contributing_layers=r.contributing_layers,
            chunk_index=r.chunk_index,
            source_type=r.source_type,
            source_origin=r.source_origin,
            embedding=r.embedding,
            score=r.rrf_score,
            combined_score=r.rrf_score,
            related_entities=r.related_entities if include_related else None,
        )
        results.append(result)

    metadata = internal_result.metadata
    timings = PEDRLayerTimings(
        lexical_ms=metadata.timings.lexical_ms,
        semantic_ms=metadata.timings.semantic_ms,
        graph_ms=metadata.timings.graph_ms,
        syntactic_ms=metadata.timings.syntactic_ms,
        pragmatic_ms=metadata.timings.pragmatic_ms,
        governance_ms=metadata.timings.governance_ms,
        fusion_ms=metadata.timings.fusion_ms,
        relational_ms=metadata.timings.relational_ms,
        total_ms=metadata.timings.total_ms,
    )

    response_metadata = PEDRSearchMetadata(
        query=metadata.query,
        intent=metadata.intent,
        intent_confidence=metadata.intent_confidence,
        detected_type=metadata.detected_type,
        type_confidence=metadata.type_confidence,
        layers_used=metadata.layers_used,
        layer_weights=metadata.layer_weights,
        timings=timings,
        graph_enabled=metadata.graph_enabled,
        graph_candidates_expanded=metadata.graph_candidates_expanded,
        total_candidates=metadata.total_candidates,
        result_count=metadata.result_count,
        rerank_mode=rerank_mode,
        hybrid_fallback_used=False,
    )

    return PEDRSearchResponse(results=results, metadata=response_metadata)


__all__ = ["router"]
