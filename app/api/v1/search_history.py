"""Search history endpoints for listing and replaying queries."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids
from app.core.config import settings
from app.core.database import get_db
from app.core.security import ROLE_SERVICE, AuthenticatedUser, require_authenticated_user
from app.models.search_history import SearchHistory
from app.schemas.rag import RagResponse
from app.schemas.retrieval import RetrievalResponse, RetrievedChunk
from app.schemas.search_history import (
    SearchHistoryEntry,
    SearchHistoryListResponse,
    SearchReplayResponse,
)
from app.services.rag_service import build_empty_scope_result, get_rag_service
from app.services.retrieval_service import get_retrieval_service
from app.services.search_history import SearchHistoryService, get_search_history_service

router = APIRouter()


@router.get("/search/history", response_model=SearchHistoryListResponse)
def list_search_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: SearchHistoryService = Depends(get_search_history_service),
) -> SearchHistoryListResponse:
    """Return the most recent search entries plus retention metadata."""
    if settings.rbac_enabled and current_user.role == ROLE_SERVICE:
        return SearchHistoryListResponse(
            entries=[], retention=service.retention_policy()
        )

    allowed_project_ids = accessible_project_ids(current_user, db)
    owner_scope = _artifact_owner_scope(current_user, allowed_project_ids)
    rows = service.list_history(limit=limit, owner_id=owner_scope)
    visible_chunks = service.visible_top_chunks(
        rows, allowed_project_ids=allowed_project_ids
    )
    entries = [
        _serialize_entry(
            item,
            visible_top_chunks=visible_chunks[item.id],
            scoped=allowed_project_ids is not None,
        )
        for item in rows
    ]
    return SearchHistoryListResponse(
        entries=entries, retention=service.retention_policy()
    )


@router.delete("/search/history")
def clear_search_history(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: SearchHistoryService = Depends(get_search_history_service),
) -> dict[str, int]:
    """Delete all stored search history entries."""
    if settings.rbac_enabled and current_user.role == ROLE_SERVICE:
        return {"deleted": 0}
    allowed_project_ids = accessible_project_ids(current_user, db)
    deleted = service.clear_history(
        owner_id=_artifact_owner_scope(current_user, allowed_project_ids)
    )
    return {"deleted": deleted}


@router.post("/search/replay/{history_id}", response_model=SearchReplayResponse)
async def replay_search(
    history_id: UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    history_service: SearchHistoryService = Depends(get_search_history_service),
) -> SearchReplayResponse:
    """Replay a recorded search and return fresh semantic + RAG responses."""
    if settings.rbac_enabled and current_user.role == ROLE_SERVICE:
        raise HTTPException(status_code=404, detail="Search history entry not found.")

    allowed_project_ids = accessible_project_ids(current_user, db)
    owner_scope = _artifact_owner_scope(current_user, allowed_project_ids)
    entry = history_service.get_entry(history_id, owner_id=owner_scope)
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

    rag_kwargs: dict[str, Any] = dict(
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
    semantic_kwargs: dict[str, Any] = dict(
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
    if _scope_is_empty(project_id, allowed_project_ids):
        rag_payload = RagResponse.model_validate(
            build_empty_scope_result(search_mode=entry.search_mode)
        )
        semantic_payload = RetrievalResponse(results=[])
    else:
        if allowed_project_ids is not None:
            rag_kwargs["allowed_project_ids"] = allowed_project_ids
            semantic_kwargs["allowed_project_ids"] = allowed_project_ids
        rag_result = get_rag_service().run_query(**rag_kwargs)
        rag_payload = RagResponse.model_validate(rag_result)
        semantic_results = get_retrieval_service().search(**semantic_kwargs)
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
        owner_id=current_user.user_id,
        top_chunks=[
            chunk.chunk_id for chunk in rag_payload.sources[:5] if chunk.chunk_id
        ],
        metadata=metadata,
    )

    visible_chunks = history_service.visible_top_chunks(
        [entry], allowed_project_ids=allowed_project_ids
    )

    return SearchReplayResponse(
        entry=_serialize_entry(
            entry,
            visible_top_chunks=visible_chunks[entry.id],
            scoped=allowed_project_ids is not None,
        ),
        rag=rag_payload,
        semantic=semantic_payload,
    )


def _serialize_entry(
    entry: SearchHistory,
    *,
    visible_top_chunks: list[str] | None = None,
    scoped: bool = False,
) -> SearchHistoryEntry:
    """Convert ORM entries into API models while exposing metadata payload."""
    top_chunks = (
        list(visible_top_chunks or [])
        if scoped
        else list(entry.top_chunks or [])
    )
    result_count = (
        min(max(0, int(entry.result_count or 0)), len(top_chunks))
        if scoped
        else entry.result_count
    )
    return SearchHistoryEntry(
        id=entry.id,
        query_text=entry.query_text,
        search_mode=entry.search_mode,
        filters=entry.filters or {},
        result_count=result_count,
        top_k=entry.top_k,
        duration_ms=entry.duration_ms,
        cache_hit=entry.cache_hit,
        owner_id=entry.owner_id,
        user_label=entry.user_label,
        metadata=entry.metadata_payload or {},
        top_chunks=top_chunks,
        created_at=entry.created_at,
    )


def _artifact_owner_scope(
    user: AuthenticatedUser, allowed_project_ids: list[UUID] | None
) -> UUID | None:
    """Return ``None`` only for the privileged/RBAC-off global path."""
    return None if allowed_project_ids is None else user.user_id


def _scope_is_empty(
    project_id: str | None, allowed_project_ids: list[UUID] | None
) -> bool:
    """Fail closed before constructing provider-backed service singletons."""
    if allowed_project_ids is None:
        return False
    if not allowed_project_ids:
        return True
    if project_id is None:
        return False
    try:
        return UUID(project_id) not in set(allowed_project_ids)
    except (TypeError, ValueError, AttributeError):
        return True


def _normalize_string(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_sequence(value: Any | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
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
