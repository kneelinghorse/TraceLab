"""Search history endpoints for listing and replaying queries."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthenticatedUser, require_authenticated_user
from app.models.search_history import SearchHistory
from app.schemas.rag import RagResponse
from app.schemas.retrieval import RetrievalResponse, RetrievedChunk
from app.schemas.search_history import (
    SearchHistoryEntry,
    SearchHistoryListResponse,
    SearchReplayResponse,
)
from app.services.rag_service import get_rag_service
from app.services.retrieval_service import get_retrieval_service
from app.services.search_history import SearchHistoryService, get_search_history_service

router = APIRouter()


@router.get("/search/history", response_model=SearchHistoryListResponse)
def list_search_history(
    limit: int = Query(20, ge=1, le=100),
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SearchHistoryService = Depends(get_search_history_service),
) -> SearchHistoryListResponse:
    """Return the most recent search entries plus retention metadata."""
    entries = [_serialize_entry(item) for item in service.list_history(limit=limit)]
    return SearchHistoryListResponse(
        entries=entries, retention=service.retention_policy()
    )


@router.delete("/search/history")
def clear_search_history(
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SearchHistoryService = Depends(get_search_history_service),
) -> dict[str, int]:
    """Delete all stored search history entries."""
    deleted = service.clear_history()
    return {"deleted": deleted}


@router.post("/search/replay/{history_id}", response_model=SearchReplayResponse)
async def replay_search(
    history_id: UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    history_service: SearchHistoryService = Depends(get_search_history_service),
) -> SearchReplayResponse:
    """Replay a recorded search and return fresh semantic + RAG responses."""
    entry = history_service.get_entry(history_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Search history entry not found.")

    filters = entry.filters or {}
    project_id = _normalize_string(filters.get("project_id"))
    document_id = _normalize_string(filters.get("document_id"))
    source_type = _normalize_string(filters.get("source_type"))
    document_types = _normalize_sequence(filters.get("document_types"))
    source_types = _normalize_sequence(filters.get("source_types"))
    tags = _normalize_sequence(filters.get("tags"))
    date_from = _parse_date(filters.get("date_from"))
    date_to = _parse_date(filters.get("date_to"))

    rag_service = get_rag_service()
    rag_result = rag_service.run_query(
        query=entry.query_text,
        top_k=entry.top_k,
        project_id=project_id,
        document_id=document_id,
        source_type=source_type,
        document_types=document_types,
        source_types=source_types,
        date_from=date_from,
        date_to=date_to,
        tags=tags,
        search_mode=entry.search_mode,
    )
    rag_payload = RagResponse.model_validate(rag_result)

    retrieval_service = get_retrieval_service()
    semantic_results = retrieval_service.search(
        query=entry.query_text,
        top_k=entry.top_k,
        project_id=project_id,
        document_id=document_id,
        source_type=source_type,
        document_types=document_types,
        source_types=source_types,
        date_from=date_from,
        date_to=date_to,
        tags=tags,
    )
    semantic_payload = RetrievalResponse(
        results=[RetrievedChunk.model_validate(item) for item in semantic_results]
    )

    metadata = dict(entry.metadata_payload or {})
    metadata["replay_of"] = str(entry.id)
    history_service.record_search(
        query=entry.query_text,
        search_mode=rag_payload.search_mode,
        filters=filters,
        top_k=entry.top_k,
        result_count=len(rag_payload.sources),
        duration_ms=rag_payload.latency_ms,
        cache_hit=rag_payload.cache.hit,
        executed_by=current_user.username,
        top_chunks=[
            chunk.chunk_id for chunk in rag_payload.sources[:5] if chunk.chunk_id
        ],
        metadata=metadata,
    )

    return SearchReplayResponse(
        entry=_serialize_entry(entry),
        rag=rag_payload,
        semantic=semantic_payload,
    )


def _serialize_entry(entry: SearchHistory) -> SearchHistoryEntry:
    """Convert ORM entries into API models while exposing metadata payload."""
    return SearchHistoryEntry(
        id=entry.id,
        query_text=entry.query_text,
        search_mode=entry.search_mode,
        filters=entry.filters or {},
        result_count=entry.result_count,
        top_k=entry.top_k,
        duration_ms=entry.duration_ms,
        cache_hit=entry.cache_hit,
        user_label=entry.user_label,
        metadata=entry.metadata_payload or {},
        top_chunks=entry.top_chunks or [],
        created_at=entry.created_at,
    )


def _normalize_string(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_sequence(value: Any | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item or "").strip()]
    text = str(value).strip()
    return [text] if text else []


def _parse_date(value: Any | None) -> date | None:
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
