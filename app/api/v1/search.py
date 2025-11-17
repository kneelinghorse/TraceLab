"""API endpoints exposing the full RAG search experience."""
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.rag import RagQuery, RagResponse
from app.services.rag_service import get_rag_service
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.services.search_history import SearchHistoryService, get_search_history_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/search", response_model=RagResponse)
async def run_rag_search(
    payload: RagQuery,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    history_service: SearchHistoryService = Depends(get_search_history_service),
) -> RagResponse:
    """
    Execute a RAG query and return an answer with citations and supporting chunks.

    The search_mode parameter selects semantic (vector-only), keyword (PostgreSQL
    full-text), or hybrid (weighted combination) retrieval strategies.
    """
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query text must not be empty.")

    service = get_rag_service()
    result = service.run_query(
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
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        search_mode=payload.search_mode,
        min_quality_gates=payload.min_quality_gates,
        status_filters=payload.status,
        allow_pii=payload.allow_pii,
    )
    response = RagResponse.model_validate(result)
    _log_search_history(
        payload=payload,
        response=response,
        current_user=current_user,
        history_service=history_service,
    )
    return response


def _log_search_history(
    *,
    payload: RagQuery,
    response: RagResponse,
    current_user: AuthenticatedUser,
    history_service: SearchHistoryService,
) -> None:
    """Persist search history without impacting the primary request."""
    filters: Dict[str, Any] = {
        "project_id": str(payload.project_id) if payload.project_id else None,
        "document_id": str(payload.document_id) if payload.document_id else None,
        "document_types": payload.document_types or [],
        "source_types": payload.source_types or [],
        "source_type": payload.source_type,
        "tags": payload.tags or [],
        "date_from": payload.date_from.isoformat() if payload.date_from else None,
        "date_to": payload.date_to.isoformat() if payload.date_to else None,
        "min_quality_gates": payload.min_quality_gates,
        "status": payload.status or [],
        "allow_pii": payload.allow_pii,
    }
    cache = (
        response.cache.model_dump()
        if hasattr(response.cache, "model_dump")
        else response.cache.dict()
    )
    top_chunks = [chunk.chunk_id for chunk in response.sources[:5] if chunk.chunk_id]
    metadata = {
        "latency_ms": response.latency_ms,
        "quality_score": response.quality.composite_score,
        "routing_model": response.routing.selected_model,
    }
    try:
        history_service.record_search(
            query=payload.query,
            search_mode=response.search_mode,
            filters=filters,
            top_k=payload.top_k,
            result_count=len(response.sources),
            duration_ms=response.latency_ms,
            cache_hit=cache.get("hit", False),
            executed_by=current_user.username,
            top_chunks=top_chunks,
            metadata=metadata,
        )
    except Exception as error:  # pragma: no cover - defensive
        logger.warning("Search history logging failed: %s", error)
