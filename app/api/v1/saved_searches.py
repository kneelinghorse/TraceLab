"""Saved search CRUD and execution endpoints."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.security import AuthenticatedUser, require_authenticated_user
from app.models.saved_search import SavedSearch
from app.schemas.rag import RagResponse
from app.schemas.retrieval import RetrievalResponse, RetrievedChunk
from app.schemas.saved_searches import (
    SavedSearchCreateRequest,
    SavedSearchExecuteResponse,
    SavedSearchListResponse,
    SavedSearchResponse,
    SavedSearchUpdateRequest,
)
from app.services.rag_service import get_rag_service
from app.services.retrieval_service import get_retrieval_service
from app.services.saved_search import SavedSearchService, get_saved_search_service
from app.services.search_history import SearchHistoryService, get_search_history_service

router = APIRouter()


@router.get("/saved-searches", response_model=SavedSearchListResponse)
def list_saved_searches(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SavedSearchService = Depends(get_saved_search_service),
) -> SavedSearchListResponse:
    """Return saved searches owned by the authenticated user."""
    entries = service.list_for_owner(current_user.username)
    payload = [SavedSearchResponse.model_validate(entry) for entry in entries]
    return SavedSearchListResponse(items=payload, limit_per_user=service.max_saved_per_user)


@router.post("/saved-searches", response_model=SavedSearchResponse, status_code=status.HTTP_201_CREATED)
def create_saved_search(
    request: SavedSearchCreateRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SavedSearchService = Depends(get_saved_search_service),
) -> SavedSearchResponse:
    """Create a saved search definition."""
    try:
        entry = service.create(
            owner=current_user.username,
            name=request.name,
            description=request.description,
            query_text=request.query_text,
            search_mode=request.search_mode,
            filters=request.filters,
            top_k=request.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SavedSearchResponse.model_validate(entry)


@router.put("/saved-searches/{saved_search_id}", response_model=SavedSearchResponse)
def update_saved_search(
    saved_search_id: UUID,
    request: SavedSearchUpdateRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SavedSearchService = Depends(get_saved_search_service),
) -> SavedSearchResponse:
    """Update saved search metadata."""
    try:
        entry = service.update(
            saved_search_id,
            owner=current_user.username,
            updates=request.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found.")
    return SavedSearchResponse.model_validate(entry)


@router.delete("/saved-searches/{saved_search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_search(
    saved_search_id: UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SavedSearchService = Depends(get_saved_search_service),
) -> Response:
    """Delete a saved search record."""
    deleted = service.delete(saved_search_id, owner=current_user.username)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/saved-searches/{saved_search_id}/execute", response_model=SavedSearchExecuteResponse)
def execute_saved_search(
    saved_search_id: UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SavedSearchService = Depends(get_saved_search_service),
    history_service: SearchHistoryService = Depends(get_search_history_service),
) -> SavedSearchExecuteResponse:
    """Run a saved search and return fresh semantic + RAG payloads."""
    entry = service.get(saved_search_id, owner=current_user.username)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found.")

    filters = dict(entry.filters or {})
    rag_response = _run_rag_pipeline(entry, filters)
    semantic_payload = _run_semantic_pipeline(entry, filters)
    _record_execution(history_service, entry, filters, current_user, rag_response)
    updated_entry = service.mark_used(entry.id, owner=current_user.username) or entry

    return SavedSearchExecuteResponse(
        saved_search=SavedSearchResponse.model_validate(updated_entry),
        rag=rag_response,
        semantic=semantic_payload,
    )


def _run_rag_pipeline(entry: SavedSearch, filters: dict[str, Any]) -> RagResponse:
    rag_service = get_rag_service()
    rag_result = rag_service.run_query(
        query=entry.query_text,
        top_k=entry.top_k,
        project_id=_normalize_string(filters.get("project_id")),
        document_id=_normalize_string(filters.get("document_id")),
        source_type=_normalize_string(filters.get("source_type")),
        document_types=_normalize_sequence(filters.get("document_types")),
        source_types=_normalize_sequence(filters.get("source_types")),
        date_from=_parse_date(filters.get("date_from")),
        date_to=_parse_date(filters.get("date_to")),
        tags=_normalize_sequence(filters.get("tags")),
        search_mode=entry.search_mode,
    )
    return RagResponse.model_validate(rag_result)


def _run_semantic_pipeline(entry: SavedSearch, filters: dict[str, Any]) -> RetrievalResponse:
    retrieval_service = get_retrieval_service()
    semantic_results = retrieval_service.search(
        query=entry.query_text,
        top_k=entry.top_k,
        project_id=_normalize_string(filters.get("project_id")),
        document_id=_normalize_string(filters.get("document_id")),
        source_type=_normalize_string(filters.get("source_type")),
        document_types=_normalize_sequence(filters.get("document_types")) or None,
        source_types=_normalize_sequence(filters.get("source_types")) or None,
        date_from=_parse_date(filters.get("date_from")),
        date_to=_parse_date(filters.get("date_to")),
        tags=_normalize_sequence(filters.get("tags")) or None,
    )
    return RetrievalResponse(results=[RetrievedChunk.model_validate(item) for item in semantic_results])


def _record_execution(
    history_service: SearchHistoryService,
    entry: SavedSearch,
    filters: dict[str, Any],
    user: AuthenticatedUser,
    rag_response: RagResponse,
) -> None:
    try:
        history_service.record_search(
            query=entry.query_text,
            search_mode=rag_response.search_mode,
            filters=filters,
            top_k=entry.top_k,
            result_count=len(rag_response.sources),
            duration_ms=rag_response.latency_ms,
            cache_hit=rag_response.cache.hit,
            executed_by=user.username,
            top_chunks=[chunk.chunk_id for chunk in rag_response.sources[:5] if chunk.chunk_id],
            metadata={"saved_search_id": str(entry.id)},
        )
    except Exception:  # pragma: no cover - defensive logging handled by service
        pass


def _normalize_string(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_sequence(value: Optional[Any]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item or "").strip()]
    text = str(value).strip()
    return [text] if text else []


def _parse_date(value: Optional[Any]) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
