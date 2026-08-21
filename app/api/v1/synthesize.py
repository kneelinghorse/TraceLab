"""Synthesize endpoint for LLM-powered summaries with citations."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids, authorize_or_403
from app.core.database import SessionLocal, get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.models.collection import Collection
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.schemas.synthesis import (
    CitationInfo,
    SynthesisCacheStatsResponse,
    SynthesizeRequest,
    SynthesizeResponse,
)
from app.services.ownership import default_workspace_id
from app.services.synthesis import SynthesisService, get_synthesis_service
from app.services.synthesis_cache import (
    SynthesisCacheService,
    get_synthesis_cache_service,
)

logger = logging.getLogger(__name__)
router = APIRouter()

SynthesisServiceFactory = Callable[[], SynthesisService]


def get_synthesis_service_factory() -> SynthesisServiceFactory:
    """Return the service constructor without initializing its LLM client."""
    return get_synthesis_service


def _create_report_from_synthesis(
    *,
    title: str,
    content: str,
    output_format: str,
    prompt: str | None,
    tokens_used: int,
    chunk_count: int,
    collection_id: UUID | None,
    chunk_ids: list[UUID] | None,
    project_id: UUID | None,
    owner_id: UUID | None,
) -> UUID:
    """Create a Report record from synthesis results.

    This reuses the synthesis content directly (no second LLM call).
    Returns the report UUID.

    owner_id (the caller) + workspace_id (default Space) are set so a project-less
    report is visible to its own creator once rbac_enabled is on (T48.4 parity) —
    a NULL-project report has no Space-inheritance fallback, so owner_id is its only
    non-admin access path.
    """
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    session = SessionLocal()
    try:
        report = Report(
            project_id=str(project_id) if project_id else None,
            title=title,
            report_type=output_format,
            prompt=prompt,
            content=content,
            content_hash=content_hash,
            status="draft",
            tokens_used=tokens_used,
            chunk_count=chunk_count,
            owner_id=owner_id,
            workspace_id=default_workspace_id(session),
        )
        session.add(report)
        session.flush()  # Get report.id

        # Record sources
        if collection_id:
            source = ReportSource(
                report_id=report.id,
                source_type="collection",
                source_id=str(collection_id),
            )
            session.add(source)

        if chunk_ids:
            for chunk_id in chunk_ids:
                source = ReportSource(
                    report_id=report.id,
                    source_type="chunk",
                    source_id=str(chunk_id),
                )
                session.add(source)

        session.commit()
        report_id = report.id
        return UUID(str(report_id))

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.post("/synthesize", response_model=SynthesizeResponse)
def synthesize(
    request: SynthesizeRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service_factory: SynthesisServiceFactory = Depends(
        get_synthesis_service_factory
    ),
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
    - **save_as_report**: If true, persist the synthesis as a report
    - **report_title**: Title for the report (required if save_as_report=true)
    - **project_id**: Project to associate the report with (optional)

    Returns markdown content with inline citations [1], [2], etc., plus a
    citations list mapping numbers to source chunks.

    **Caching**: Results are cached by content hash. Identical requests return
    instantly from cache, saving API costs and time.

    **Save as Report**: When `save_as_report=true`, the synthesis result is
    automatically saved as a report. The response includes `report_id` with
    the UUID of the created report. This simplifies the workflow by combining
    synthesis and report creation into a single API call.
    """
    project_scope = accessible_project_ids(current_user, db)
    if request.collection_id is not None and project_scope is not None:
        collection = db.get(Collection, request.collection_id)
        if collection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found.",
            )
        authorize_or_403(current_user, "read", collection, db)

    if (
        request.save_as_report
        and request.project_id is not None
        and project_scope is not None
    ):
        project = db.get(Project, request.project_id)
        if project is None or project.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )
        authorize_or_403(current_user, "create", project, db)

    if project_scope == []:
        result = SynthesisService._empty_result(include_effective_chunk_ids=True)
    else:
        try:
            service = service_factory()
            if project_scope is None:
                result = service.synthesize(
                    collection_id=request.collection_id,
                    chunk_ids=request.chunk_ids,
                    prompt=request.prompt,
                    output_format=request.format,
                )
            else:
                result = service.synthesize(
                    collection_id=request.collection_id,
                    chunk_ids=request.chunk_ids,
                    prompt=request.prompt,
                    output_format=request.format,
                    accessible_project_ids=project_scope,
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
            document_id=c.get("document_id"),
            excerpt=c.get("excerpt", ""),
        )
        for c in result.get("citations", [])
    ]

    # Optionally save as report
    report_id: UUID | None = None
    if request.save_as_report and request.report_title:
        try:
            report_id = _create_report_from_synthesis(
                title=request.report_title,
                content=result["content"],
                output_format=request.format,
                prompt=request.prompt,
                tokens_used=result.get("tokens_used", 0),
                chunk_count=result.get("chunk_count", 0),
                collection_id=request.collection_id,
                chunk_ids=[
                    chunk_id if isinstance(chunk_id, UUID) else UUID(chunk_id)
                    for chunk_id in result.get(
                        "effective_chunk_ids", request.chunk_ids or []
                    )
                ],
                project_id=request.project_id,
                owner_id=current_user.user_id,
            )
            logger.info(f"Synthesis saved as report {report_id}")
        except Exception as exc:
            logger.error(f"Failed to save synthesis as report: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Synthesis succeeded but report creation failed: {exc}",
            ) from exc

    return SynthesizeResponse(
        content=result["content"],
        citations=citations,
        tokens_used=result.get("tokens_used", 0),
        truncated=result.get("truncated", False),
        chunk_count=result.get("chunk_count", 0),
        cache_hit=result.get("cache_hit", False),
        cache_id=result.get("cache_id"),
        report_id=report_id,
    )


@router.get("/synthesis/cache/stats", response_model=SynthesisCacheStatsResponse)
def get_synthesis_cache_stats(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    cache_service: SynthesisCacheService = Depends(get_synthesis_cache_service),
) -> SynthesisCacheStatsResponse:
    """Get synthesis cache statistics.

    Returns aggregated stats about the synthesis cache including:
    - Total cached entries
    - Total cache hits
    - Tokens saved by caching
    - Top hit entries

    Useful for monitoring cache efficiency and cost savings.
    """
    try:
        stats = cache_service.get_stats()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve cache stats: {exc}",
        ) from exc

    return SynthesisCacheStatsResponse(
        total_entries=stats.get("total_entries", 0),
        total_hits=stats.get("total_hits", 0),
        total_tokens_cached=stats.get("total_tokens_cached", 0),
        total_tokens_saved=stats.get("total_tokens_saved", 0),
        last_hit_at=stats.get("last_hit_at"),
        oldest_entry=stats.get("oldest_entry"),
        top_entries=stats.get("top_entries", []),
    )
