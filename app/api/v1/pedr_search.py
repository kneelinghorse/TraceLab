"""PEDR Unified Search API endpoint.

POST /api/v1/pedr/search - Execute PEDR search across all 5 layers with RRF fusion.

This is the primary search interface for TraceLab, replacing/complementing the
legacy RAG search endpoint with full Protocol-Enhanced Deep Research capabilities.
"""
import logging
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
from app.services.pedr.search_orchestrator import create_pedr_orchestrator

router = APIRouter()
logger = logging.getLogger(__name__)


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

    Args:
        payload: PEDR search request parameters

    Returns:
        PEDRSearchResponse with ranked results and execution metadata
    """
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query text must not be empty.")

    try:
        # Create orchestrator with wired search providers
        orchestrator = create_pedr_orchestrator()

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
        result = orchestrator.search(
            query=payload.query,
            top_k=payload.top_k,
            project_id=str(payload.project_id) if payload.project_id else None,
            document_id=str(payload.document_id) if payload.document_id else None,
            source_type=payload.source_type,
            document_types=payload.document_types,
            source_types=payload.source_types,
            date_from=payload.date_from,
            date_to=payload.date_to,
            tags=payload.tags,
            hnsw_ef=payload.hnsw_ef,
            element_type=payload.element_type,
            element_types=list(payload.element_types) if payload.element_types else None,
            auto_detect_type=payload.auto_detect_type,
            type_boost_enabled=payload.type_boost_enabled,
            intent_boost_enabled=payload.intent_boost_enabled,
            min_quality_gates=payload.min_quality_gates,
            status_filters=payload.status_filters,
            allow_pii=payload.allow_pii,
            enable_lexical=payload.enable_lexical,
            enable_semantic=payload.enable_semantic,
            enable_syntactic=payload.enable_syntactic,
            enable_pragmatic=payload.enable_pragmatic,
            enable_governance=payload.enable_governance,
            layer_weights=layer_weights,
        )

        # Convert internal response to Pydantic models
        response = _convert_to_response(result)

        logger.info(
            "PEDR search completed: query=%r, results=%d, latency=%.1fms, user=%s",
            payload.query[:50],
            len(response.results),
            response.metadata.timings.total_ms,
            current_user.username,
        )

        return response

    except ValueError as e:
        logger.warning("PEDR search validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("PEDR search failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


def _convert_to_response(
    internal_result: Any,
) -> PEDRSearchResponse:
    """Convert internal PEDRSearchResponse to Pydantic schema."""
    # The internal result is already well-structured, just need to map to Pydantic

    results = []
    for r in internal_result.results:
        results.append(
            PEDRSearchResult(
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
                score=r.rrf_score,
                combined_score=r.rrf_score,
            )
        )

    metadata = internal_result.metadata
    timings = PEDRLayerTimings(
        lexical_ms=metadata.timings.lexical_ms,
        semantic_ms=metadata.timings.semantic_ms,
        syntactic_ms=metadata.timings.syntactic_ms,
        pragmatic_ms=metadata.timings.pragmatic_ms,
        governance_ms=metadata.timings.governance_ms,
        fusion_ms=metadata.timings.fusion_ms,
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
        total_candidates=metadata.total_candidates,
        result_count=metadata.result_count,
    )

    return PEDRSearchResponse(results=results, metadata=response_metadata)


__all__ = ["router"]
