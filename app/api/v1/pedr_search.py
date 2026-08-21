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
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids
from app.core.database import get_db
from app.core.mission_events import (
    MissionEventType,
    emit_pedr_layer_event,
)
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.schemas.pedr_search import (
    PEDRLayerTimings,
    PEDRSearchMetadata,
    PEDRSearchRequest,
    PEDRSearchResponse,
    PEDRSearchResult,
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
    db: Session = Depends(get_db),
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
        allowed_project_ids = accessible_project_ids(current_user, db)
        if allowed_project_ids == [] or (
            allowed_project_ids is not None
            and payload.project_id is not None
            and payload.project_id not in set(allowed_project_ids)
        ):
            return _empty_search_response(payload)

        # Use hybrid reranker for "hybrid" mode (B19.4)
        if payload.rerank_mode == "hybrid":
            return await _execute_hybrid_search(
                payload,
                current_user,
                allowed_project_ids=allowed_project_ids,
            )

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
        search_kwargs = dict(
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
            element_types=list(payload.element_types)
            if payload.element_types
            else None,
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
        if allowed_project_ids is not None:
            search_kwargs["allowed_project_ids"] = allowed_project_ids
        result = await asyncio.to_thread(orchestrator.search, **search_kwargs)

        # Defense in depth: providers are scoped before retrieval, and the API
        # still fails closed if a provider returns an out-of-scope payload.
        if allowed_project_ids is not None and not getattr(
            result, "scope_verified", False
        ):
            result.results = _resolve_graph_result_projects(result.results, db)
        unfiltered_result_count = len(result.results)
        result.results = _filter_results_by_scope(
            result.results,
            allowed_project_ids,
            project_id=payload.project_id,
            document_id=payload.document_id,
        )
        result.metadata.result_count = len(result.results)
        if len(result.results) != unfiltered_result_count:
            result.metadata.total_candidates = len(result.results)

        # Apply graph expansion if requested
        relational_ms = 0.0
        if payload.include_related:
            t0 = time.perf_counter()
            relational_service = get_relational_service()
            for search_result in result.results:
                if search_result.urn:
                    try:
                        related_kwargs: dict[str, Any] = {
                            "max_depth": 1,
                            "limit": payload.max_related_per_result,
                        }
                        if allowed_project_ids is not None:
                            related_kwargs["allowed_project_ids"] = allowed_project_ids
                        expansion = relational_service.get_related(
                            search_result.urn,
                            **related_kwargs,
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
        unfiltered_response_count = len(response.results)
        response.results = _filter_results_by_scope(
            response.results,
            allowed_project_ids,
            project_id=payload.project_id,
            document_id=payload.document_id,
        )
        response.metadata.result_count = len(response.results)
        if len(response.results) != unfiltered_response_count:
            response.metadata.total_candidates = len(response.results)

        logger.info(
            "PEDR search completed: query=%r, mode=full, results=%d, latency=%.1fms, relational=%.1fms, user=%s",
            payload.query[:50],
            len(response.results),
            response.metadata.timings.total_ms,
            relational_ms,
            current_user.username,
        )

        emit_pedr_layer_event(
            event_type=MissionEventType.PEDR_SEARCH_COMPLETED,
            layer="fusion",
            duration_ms=response.metadata.timings.total_ms,
            result_count=response.metadata.result_count,
        )

        return response

    except ValueError as e:
        logger.warning("PEDR search validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("PEDR search failed: %s", e)
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from e


async def _execute_hybrid_search(
    payload: PEDRSearchRequest,
    current_user: AuthenticatedUser,
    *,
    allowed_project_ids: list[UUID] | None = None,
) -> PEDRSearchResponse:
    """Execute hybrid FTS+semantic rerank search (B19.4).

    This provides faster search latency (<300ms target) by:
    1. Using PostgreSQL FTS to retrieve candidate pool
    2. Reranking candidates using semantic similarity

    Args:
        payload: Search request parameters.
        current_user: Authenticated user.
        allowed_project_ids: Request-local readable project scope.

    Returns:
        PEDRSearchResponse with hybrid search results.
    """
    reranker = get_hybrid_reranker()

    search_kwargs = dict(
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
    if allowed_project_ids is not None:
        search_kwargs["allowed_project_ids"] = allowed_project_ids
    hybrid_result = await asyncio.to_thread(reranker.search, **search_kwargs)

    governance_ms = 0.0
    hybrid_payloads = _filter_results_by_scope(
        hybrid_result.results,
        allowed_project_ids,
        project_id=payload.project_id,
        document_id=payload.document_id,
    )
    authorized_candidates = len(hybrid_payloads)
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
            contributing_layers=["fts", "semantic"]
            + (["governance"] if payload.enable_governance else []),
            chunk_index=r.get("chunk_index"),
            source_type=r.get("source_type"),
            source_origin=r.get("source_origin"),
            score=float(r.get("score") or r.get("semantic_score") or 0.0),
            combined_score=float(
                r.get("combined_score") or r.get("semantic_score") or 0.0
            ),
            embedding=r.get("embedding"),
            related_entities=None,
        )
        results.append(result)

    # Build timings from hybrid result
    timings = PEDRLayerTimings(
        lexical_ms=hybrid_result.timings.fts_ms,
        semantic_ms=hybrid_result.timings.embedding_ms
        + hybrid_result.timings.rerank_ms,
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
        layers_used=["fts", "semantic"]
        + (["governance"] if payload.enable_governance else []),
        layer_weights={"fts": 0.0, "semantic": 1.0, "governance": 0.0},
        timings=timings,
        graph_enabled=False,
        graph_candidates_expanded=None,
        total_candidates=(
            hybrid_result.fts_candidates_count
            if allowed_project_ids is None
            else authorized_candidates
        ),
        result_count=len(results),
        rerank_mode="hybrid",
        hybrid_fallback_used=hybrid_result.fallback_used,
    )

    response = PEDRSearchResponse(results=results, metadata=metadata)
    unfiltered_response_count = len(response.results)
    response.results = _filter_results_by_scope(
        response.results,
        allowed_project_ids,
        project_id=payload.project_id,
        document_id=payload.document_id,
    )
    response.metadata.result_count = len(response.results)
    if len(response.results) != unfiltered_response_count:
        response.metadata.total_candidates = len(response.results)

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


def _filter_results_by_scope(
    results: list[Any],
    allowed_project_ids: list[UUID] | None,
    *,
    project_id: UUID | None = None,
    document_id: UUID | None = None,
) -> list[Any]:
    """Fail closed on payloads outside authorization and explicit filters."""
    if allowed_project_ids is None:
        return results

    allowed = {str(allowed_id) for allowed_id in allowed_project_ids}
    filtered: list[Any] = []
    for result in results:
        result_project_id = (
            result.get("project_id")
            if isinstance(result, dict)
            else getattr(result, "project_id", None)
        )
        result_document_id = (
            result.get("document_id")
            if isinstance(result, dict)
            else getattr(result, "document_id", None)
        )
        if (
            result_project_id is None or str(result_project_id) not in allowed
        ):
            continue
        if project_id is not None and str(result_project_id) != str(project_id):
            continue
        if document_id is not None and str(result_document_id) != str(document_id):
            continue
        filtered.append(result)
    return filtered


def _resolve_graph_result_projects(results: list[Any], db: Session) -> list[Any]:
    """Resolve scoped graph chunks against authoritative document ownership."""
    parsed_chunk_ids: dict[int, str] = {}
    valid_chunk_ids: dict[str, UUID] = {}
    for index, result in enumerate(results):
        if "graph" not in (getattr(result, "contributing_layers", None) or ()):
            continue
        chunk_id = getattr(result, "chunk_id", None)
        try:
            parsed_chunk_id = UUID(str(chunk_id))
        except (TypeError, ValueError):
            continue
        canonical_chunk_id = str(parsed_chunk_id)
        parsed_chunk_ids[index] = canonical_chunk_id
        valid_chunk_ids[canonical_chunk_id] = parsed_chunk_id

    if not valid_chunk_ids:
        return [
            result
            for result in results
            if "graph"
            not in (getattr(result, "contributing_layers", None) or ())
        ]

    try:
        rows = db.execute(
            select(
                DocumentChunk.id.label("chunk_id"),
                DocumentChunk.document_id.label("document_id"),
                Document.project_id.label("project_id"),
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                DocumentChunk.id.in_(list(valid_chunk_ids.values())),
                Document.deleted_at.is_(None),
            )
        ).all()
    except Exception as exc:
        logger.warning("Failed to resolve graph result project scope: %s", exc)
        return [
            result
            for result in results
            if "graph"
            not in (getattr(result, "contributing_layers", None) or ())
        ]

    resolved: dict[str, tuple[str, str]] = {}
    for row in rows:
        mapping = row._mapping
        resolved[str(mapping["chunk_id"])] = (
            str(mapping["document_id"]),
            str(mapping["project_id"]),
        )

    filtered: list[Any] = []
    for index, result in enumerate(results):
        if "graph" not in (getattr(result, "contributing_layers", None) or ()):
            filtered.append(result)
            continue
        chunk_id = parsed_chunk_ids.get(index)
        identifiers = resolved.get(chunk_id) if chunk_id is not None else None
        if identifiers is None:
            continue
        resolved_document_id, resolved_project_id = identifiers
        claimed_document_id = getattr(result, "document_id", None)
        claimed_project_id = getattr(result, "project_id", None)
        if (
            claimed_document_id is not None
            and str(claimed_document_id) != resolved_document_id
        ):
            continue
        if (
            claimed_project_id is not None
            and str(claimed_project_id) != resolved_project_id
        ):
            continue
        result.document_id = resolved_document_id
        result.project_id = resolved_project_id
        filtered.append(result)
    return filtered


def _empty_search_response(payload: PEDRSearchRequest) -> PEDRSearchResponse:
    """Return a normal empty 200 response for an empty authorization intersection."""
    timings = PEDRLayerTimings(
        lexical_ms=0.0,
        semantic_ms=0.0,
        graph_ms=0.0,
        syntactic_ms=0.0,
        pragmatic_ms=0.0,
        governance_ms=0.0,
        fusion_ms=0.0,
        relational_ms=0.0,
        total_ms=0.0,
    )
    metadata = PEDRSearchMetadata(
        query=payload.query,
        intent="search",
        intent_confidence=0.0,
        detected_type=None,
        type_confidence=0.0,
        layers_used=[],
        layer_weights={},
        timings=timings,
        graph_enabled=payload.enable_graph,
        graph_candidates_expanded=0 if payload.enable_graph else None,
        total_candidates=0,
        result_count=0,
        rerank_mode=payload.rerank_mode,
        hybrid_fallback_used=False,
    )
    return PEDRSearchResponse(results=[], metadata=metadata)


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
