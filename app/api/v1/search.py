"""API endpoints exposing the full RAG search experience, and corpus Q&A for the MCP."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids, authorize_or_403
from app.core.config import settings
from app.core.database import get_db
from app.core.security import ROLE_SERVICE, AuthenticatedUser, require_authenticated_user
from app.models.project import Project
from app.models.usage_record import USAGE_KIND_SEARCH_ASK
from app.schemas.rag import AskRequest, AskResponse, RagQuery, RagResponse
from app.services.corpus_qa import answer_question
from app.services.rag_service import build_empty_scope_result, get_rag_service
from app.services.search_history import SearchHistoryService, get_search_history_service
from app.services.usage_recorder import record_librarian_usage

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/search", response_model=RagResponse)
async def run_rag_search(
    payload: RagQuery,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    history_service: SearchHistoryService = Depends(get_search_history_service),
) -> RagResponse:
    """
    Execute a RAG query and return an answer with citations and supporting chunks.

    The search_mode parameter selects semantic (vector-only), keyword (PostgreSQL
    full-text), or hybrid (weighted combination) retrieval strategies.
    """
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query text must not be empty.")

    allowed_project_ids = accessible_project_ids(current_user, db)
    if allowed_project_ids == [] or (
        allowed_project_ids is not None
        and payload.project_id is not None
        and payload.project_id not in set(allowed_project_ids)
    ):
        result = build_empty_scope_result(search_mode=payload.search_mode)
    else:
        service = get_rag_service()
        query_kwargs: dict[str, Any] = dict(
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
            governance_mode=payload.governance_mode,
            element_type=payload.element_type,
            element_types=payload.element_types,
            auto_detect_type=payload.auto_detect_type,
            type_boost_enabled=payload.type_boost_enabled,
        )
        if allowed_project_ids is not None:
            query_kwargs["allowed_project_ids"] = allowed_project_ids
        result = service.run_query(**query_kwargs)
    response = RagResponse.model_validate(result)
    _log_search_history(
        payload=payload,
        response=response,
        current_user=current_user,
        history_service=history_service,
    )
    return response


@router.post("/search/ask", response_model=AskResponse)
def ask_question(
    payload: AskRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> AskResponse:
    """Answer a question from one project's documents, or refuse (MCP-6, tracelab_search ask).

    The Librarian's answer mode and this route call the same Q&A service (decision
    #543), after loading the project and authorizing it for the caller exactly as
    that mode does: 404, then 403. Every citation opens a chunk the model read;
    no_evidence marks a question the project cannot support.
    """
    project = db.query(Project).filter(Project.id == payload.project_id, Project.deleted_at.is_(None)).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    authorize_or_403(current_user, "read", project, db)
    answer = answer_question(db, current_user, project.id, payload.question, max_tokens=payload.max_tokens)
    for model, usage in answer.usage:
        # METER-0 (decision #522): a durable row for each paid call, per user.
        record_librarian_usage(
            db,
            user_id=current_user.user_id,
            project_id=project.id,
            kind=USAGE_KIND_SEARCH_ASK,
            model=model,
            usage=usage,
            requests=1,
        )
    return AskResponse.model_validate(answer, from_attributes=True)


def _log_search_history(
    *,
    payload: RagQuery,
    response: RagResponse,
    current_user: AuthenticatedUser,
    history_service: SearchHistoryService,
) -> None:
    """Persist search history without impacting the primary request."""
    if settings.rbac_enabled and current_user.role == ROLE_SERVICE:
        return

    filters: dict[str, Any] = {
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
        "governance_mode": payload.governance_mode,
        "element_type": payload.element_type,
        "element_types": payload.element_types or [],
        "auto_detect_type": payload.auto_detect_type,
        "type_boost_enabled": payload.type_boost_enabled,
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
            owner_id=current_user.user_id,
            top_chunks=top_chunks,
            metadata=metadata,
        )
    except Exception as error:  # pragma: no cover - defensive
        logger.warning("Search history logging failed: %s", error)
