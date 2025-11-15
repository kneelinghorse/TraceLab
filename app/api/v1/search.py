"""API endpoints exposing the full RAG search experience."""
from fastapi import APIRouter, HTTPException

from app.schemas.rag import RagQuery, RagResponse
from app.services.rag_service import get_rag_service

router = APIRouter()


@router.post("/search", response_model=RagResponse)
async def run_rag_search(payload: RagQuery) -> RagResponse:
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
        hnsw_ef=payload.hnsw_ef,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        search_mode=payload.search_mode,
    )
    return RagResponse.model_validate(result)
