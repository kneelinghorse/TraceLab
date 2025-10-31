"""FastAPI routes providing semantic retrieval over embedded chunks."""
from fastapi import APIRouter, HTTPException

from app.schemas.retrieval import RetrievalQuery, RetrievalResponse, RetrievedChunk
from app.services.retrieval_service import get_retrieval_service

router = APIRouter()


@router.post("/search", response_model=RetrievalResponse)
async def search_chunks(payload: RetrievalQuery) -> RetrievalResponse:
    """
    Execute a semantic search across embedded chunks.
    
    Returns ranked chunks with metadata, applying optional project/document filters.
    """
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query text must not be empty.")
    
    service = get_retrieval_service()
    results = service.search(
        query=payload.query,
        top_k=payload.top_k,
        project_id=str(payload.project_id) if payload.project_id else None,
        document_id=str(payload.document_id) if payload.document_id else None,
        source_type=payload.source_type,
        hnsw_ef=payload.hnsw_ef,
    )
    chunk_models = [RetrievedChunk.model_validate(result) for result in results]
    return RetrievalResponse(results=chunk_models)
