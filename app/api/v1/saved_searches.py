"""Saved search CRUD and execution endpoints."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids
from app.core.config import settings
from app.core.database import get_db
from app.core.security import ROLE_SERVICE, AuthenticatedUser, require_authenticated_user
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
from app.services.rag_service import build_empty_scope_result, get_rag_service
from app.services.retrieval_service import get_retrieval_service
from app.services.saved_search import SavedSearchService, get_saved_search_service
from app.services.search_history import SearchHistoryService, get_search_history_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/saved-searches", response_model=SavedSearchListResponse)
def list_saved_searches(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SavedSearchService = Depends(get_saved_search_service),
) -> SavedSearchListResponse:
    """Return saved searches owned by the authenticated user."""
    if settings.rbac_enabled and current_user.role == ROLE_SERVICE:
        return SavedSearchListResponse(
            items=[], limit_per_user=service.max_saved_per_user
        )
    entries = service.list_for_owner(
        current_user.user_id,
        legacy_owner=_legacy_artifact_owner(current_user),
    )
    payload = [SavedSearchResponse.model_validate(entry) for entry in entries]
    return SavedSearchListResponse(
        items=payload, limit_per_user=service.max_saved_per_user
    )


@router.post(
    "/saved-searches",
    response_model=SavedSearchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_saved_search(
    request: SavedSearchCreateRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SavedSearchService = Depends(get_saved_search_service),
) -> SavedSearchResponse:
    """Create a saved search definition."""
    if settings.rbac_enabled and current_user.role == ROLE_SERVICE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Service principals cannot create saved searches.",
        )
    try:
        entry = service.create(
            owner_id=current_user.user_id,
            owner=current_user.username,
            legacy_owner=_legacy_artifact_owner(current_user),
            name=request.name,
            description=request.description,
            query_text=request.query_text,
            search_mode=request.search_mode,
            filters=request.filters,
            top_k=request.top_k,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return SavedSearchResponse.model_validate(entry)


@router.put("/saved-searches/{saved_search_id}", response_model=SavedSearchResponse)
def update_saved_search(
    saved_search_id: UUID,
    request: SavedSearchUpdateRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SavedSearchService = Depends(get_saved_search_service),
) -> SavedSearchResponse:
    """Update saved search metadata."""
    if settings.rbac_enabled and current_user.role == ROLE_SERVICE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found."
        )
    try:
        entry = service.update(
            saved_search_id,
            owner_id=current_user.user_id,
            legacy_owner=_legacy_artifact_owner(current_user),
            updates=request.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found."
        )
    return SavedSearchResponse.model_validate(entry)


@router.delete(
    "/saved-searches/{saved_search_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_saved_search(
    saved_search_id: UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SavedSearchService = Depends(get_saved_search_service),
) -> Response:
    """Delete a saved search record."""
    if settings.rbac_enabled and current_user.role == ROLE_SERVICE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found."
        )
    deleted = service.delete(
        saved_search_id,
        owner_id=current_user.user_id,
        legacy_owner=_legacy_artifact_owner(current_user),
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found."
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/saved-searches/{saved_search_id}/execute",
    response_model=SavedSearchExecuteResponse,
)
def execute_saved_search(
    saved_search_id: UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: SavedSearchService = Depends(get_saved_search_service),
    history_service: SearchHistoryService = Depends(get_search_history_service),
) -> SavedSearchExecuteResponse:
    """Run a saved search and return fresh semantic + RAG payloads."""
    if settings.rbac_enabled and current_user.role == ROLE_SERVICE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found."
        )
    allowed_project_ids = accessible_project_ids(current_user, db)
    legacy_owner = _legacy_artifact_owner(current_user)
    entry = service.get(
        saved_search_id,
        current_user.user_id,
        legacy_owner=legacy_owner,
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found."
        )

    filters = dict(entry.filters or {})
    rag_response = _run_rag_pipeline(entry, filters, allowed_project_ids)
    semantic_payload = _run_semantic_pipeline(
        entry, filters, allowed_project_ids
    )
    _record_execution(history_service, entry, filters, current_user, rag_response)
    updated_entry = (
        service.mark_used(
            entry.id,
            owner_id=current_user.user_id,
            legacy_owner=legacy_owner,
        )
        or entry
    )

    return SavedSearchExecuteResponse(
        saved_search=SavedSearchResponse.model_validate(updated_entry),
        rag=rag_response,
        semantic=semantic_payload,
    )


def _run_rag_pipeline(
    entry: SavedSearch,
    filters: dict[str, Any],
    allowed_project_ids: list[UUID] | None,
) -> RagResponse:
    if _scope_is_empty(filters, allowed_project_ids):
        return RagResponse.model_validate(
            build_empty_scope_result(search_mode=entry.search_mode)
        )

    rag_service = get_rag_service()
    query_kwargs: dict[str, Any] = dict(
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
    if allowed_project_ids is not None:
        query_kwargs["allowed_project_ids"] = allowed_project_ids
    rag_result = rag_service.run_query(**query_kwargs)
    return RagResponse.model_validate(rag_result)


def _run_semantic_pipeline(
    entry: SavedSearch,
    filters: dict[str, Any],
    allowed_project_ids: list[UUID] | None,
) -> RetrievalResponse:
    if _scope_is_empty(filters, allowed_project_ids):
        return RetrievalResponse(results=[])

    retrieval_service = get_retrieval_service()
    query_kwargs: dict[str, Any] = dict(
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
    if allowed_project_ids is not None:
        query_kwargs["allowed_project_ids"] = allowed_project_ids
    semantic_results = retrieval_service.search(**query_kwargs)
    return RetrievalResponse(
        results=[RetrievedChunk.model_validate(item) for item in semantic_results]
    )


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
            owner_id=user.user_id,
            top_chunks=[
                chunk.chunk_id for chunk in rag_response.sources[:5] if chunk.chunk_id
            ],
            metadata={"saved_search_id": str(entry.id)},
        )
    except Exception:  # pragma: no cover - defensive
        logger.warning("Saved-search history logging failed")


def _legacy_artifact_owner(user: AuthenticatedUser) -> str | None:
    """Preserve label-owned legacy rows only while RBAC is disabled."""
    return user.username if not settings.rbac_enabled else None


def _scope_is_empty(
    filters: dict[str, Any], allowed_project_ids: list[UUID] | None
) -> bool:
    """Fail closed before constructing provider-backed service singletons."""
    if allowed_project_ids is None:
        return False
    if not allowed_project_ids:
        return True
    project_id = _normalize_string(filters.get("project_id"))
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
