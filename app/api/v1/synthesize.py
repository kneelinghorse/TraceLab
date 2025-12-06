"""Synthesize endpoint for LLM-powered summaries with citations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import AuthenticatedUser, require_authenticated_user
from app.schemas.synthesis import (
    CitationInfo,
    SynthesizeRequest,
    SynthesizeResponse,
)
from app.services.synthesis import SynthesisService, get_synthesis_service

router = APIRouter()


@router.post("/synthesize", response_model=SynthesizeResponse)
def synthesize(
    request: SynthesizeRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: SynthesisService = Depends(get_synthesis_service),
) -> SynthesizeResponse:
    """Generate an LLM-powered summary from a collection or set of chunks.

    This endpoint powers the synthesis workflow where agents collect relevant
    chunks during research, then call synthesize to generate a summary report
    with proper citations back to the original sources.

    Either `collection_id` or `chunk_ids` must be provided (not both).

    - **collection_id**: Synthesize all chunks in a collection
    - **chunk_ids**: Synthesize specific chunks by their UUIDs
    - **prompt**: Custom instruction (default varies by format)
    - **format**: Output style - "summary", "report", or "bullets"

    Returns markdown content with inline citations [1], [2], etc., plus a
    citations list mapping numbers to source chunks.
    """
    try:
        result = service.synthesize(
            collection_id=request.collection_id,
            chunk_ids=request.chunk_ids,
            prompt=request.prompt,
            output_format=request.format,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        # OpenAI SDK not available or API key not set
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Synthesis failed: {exc}",
        ) from exc

    # Map result to response schema
    citations = [
        CitationInfo(
            chunk_id=c["chunk_id"],
            document_name=c.get("document_name"),
            excerpt=c.get("excerpt", ""),
        )
        for c in result.get("citations", [])
    ]

    return SynthesizeResponse(
        content=result["content"],
        citations=citations,
        tokens_used=result.get("tokens_used", 0),
        truncated=result.get("truncated", False),
        chunk_count=result.get("chunk_count", 0),
    )
