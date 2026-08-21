"""FastAPI routes providing semantic retrieval over embedded chunks."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids
from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.schemas.retrieval import RetrievalQuery, RetrievalResponse, RetrievedChunk
from app.services.retrieval_service import get_retrieval_service

router = APIRouter()


@router.post("/search", response_model=RetrievalResponse)
async def search_chunks(
    payload: RetrievalQuery,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RetrievalResponse:
    """
    Execute a semantic search across embedded chunks.

    Returns ranked chunks with metadata, applying optional project/document filters.
    """
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query text must not be empty.")

    allowed_project_ids = accessible_project_ids(current_user, db)
    service = get_retrieval_service()
    results = service.search(
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
        allowed_project_ids=allowed_project_ids,
    )
    chunk_models = [RetrievedChunk.model_validate(result) for result in results]
    return RetrievalResponse(results=chunk_models)
