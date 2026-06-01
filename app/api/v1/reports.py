"""Report CRUD and synthesis endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.authorization import accessible_filter, authorize_or_403
from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.schemas.report import (
    CitationSchema,
    DeleteResponse,
    ReportCreate,
    ReportDetailResponse,
    ReportListItem,
    ReportListResponse,
    ReportResponse,
    ReportSourceSchema,
    ReportUpdate,
)
from app.services.report_service import ReportService, get_report_service

router = APIRouter()


def _build_report_response(report, citations: list) -> ReportResponse:
    """Build ReportResponse from model and citations."""
    return ReportResponse(
        id=report.id,
        title=report.title,
        content=report.content,
        citations=[CitationSchema(**c) for c in citations],
        tokens_used=report.tokens_used,
        status=report.status,
        created_at=report.created_at,
    )


def _build_report_detail(report) -> ReportDetailResponse:
    """Build detailed report response with sources."""
    sources = [
        ReportSourceSchema(
            id=s.id,
            report_id=s.report_id,
            source_type=s.source_type,
            source_id=s.source_id,
            added_at=s.added_at,
        )
        for s in (report.sources or [])
    ]
    return ReportDetailResponse(
        id=report.id,
        title=report.title,
        content=report.content,
        citations=[],  # Citations not stored, only at creation time
        tokens_used=report.tokens_used,
        status=report.status,
        created_at=report.created_at,
        project_id=report.project_id,
        report_type=report.report_type,
        prompt=report.prompt,
        chunk_count=report.chunk_count,
        sources=sources,
        updated_at=report.updated_at,
    )


def _build_list_item(report) -> ReportListItem:
    """Build list item from report model."""
    return ReportListItem(
        id=report.id,
        title=report.title,
        status=report.status,
        report_type=report.report_type,
        tokens_used=report.tokens_used,
        chunk_count=report.chunk_count,
        project_id=report.project_id,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    request: ReportCreate,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: ReportService = Depends(get_report_service),
) -> ReportResponse:
    """Create a new report by synthesizing content from a collection or chunks.

    Either collection_id OR chunk_ids must be provided.
    """
    if not request.collection_id and not request.chunk_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either collection_id or chunk_ids must be provided.",
        )

    try:
        report, citations = service.create_report(
            title=request.title,
            collection_id=request.collection_id,
            chunk_ids=request.chunk_ids,
            project_id=request.project_id,
            prompt=request.prompt,
            output_format=request.format,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return _build_report_response(report, citations)


@router.get("", response_model=ReportListResponse)
def list_reports(
    project_id: UUID | None = Query(default=None, description="Filter by project"),
    report_status: str | None = Query(
        default=None,
        alias="status",
        description="Filter by status (draft, final)",
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: ReportService = Depends(get_report_service),
) -> ReportListResponse:
    """List reports with optional filtering and pagination.

    With RBAC enabled, non-privileged callers see only reports they own or whose
    owning project is in a Space they belong to (T47.3).
    """
    from app.models.report import Report

    reports, total = service.list_reports(
        project_id=project_id,
        status=report_status,
        page=page,
        page_size=page_size,
        access_filter=accessible_filter(current_user, Report, db),
    )
    items = [_build_list_item(r) for r in reports]
    return ReportListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{report_id}", response_model=ReportDetailResponse)
def get_report(
    report_id: UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: ReportService = Depends(get_report_service),
    db: Session = Depends(get_db),
) -> ReportDetailResponse:
    """Get a single report with its sources."""
    report = service.get_report(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )
    authorize_or_403(current_user, "read", report, db)
    return _build_report_detail(report)


@router.get("/{report_id}/export")
def export_report(
    report_id: UUID,
    format: str = Query(default="md", description="Export format: md, json, or txt"),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: ReportService = Depends(get_report_service),
    db: Session = Depends(get_db),
) -> Response:
    """Export a report as markdown, JSON, or plain text."""
    import json as json_lib

    if format not in ("md", "json", "txt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format must be one of: md, json, txt",
        )

    report = service.get_report(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )
    authorize_or_403(current_user, "read", report, db)

    safe_title = report.title.replace(" ", "-").replace("/", "-")[:80]

    if format == "json":
        detail = _build_report_detail(report)
        content = json_lib.dumps(detail.model_dump(mode="json"), indent=2)
        media_type = "application/json"
        filename = f"{safe_title}.json"
    elif format == "txt":
        content = f"{report.title}\n{'=' * len(report.title)}\n\n{report.content}"
        media_type = "text/plain"
        filename = f"{safe_title}.txt"
    else:  # md
        content = f"# {report.title}\n\n{report.content}"
        media_type = "text/markdown"
        filename = f"{safe_title}.md"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/{report_id}", response_model=ReportDetailResponse)
def update_report(
    report_id: UUID,
    request: ReportUpdate,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: ReportService = Depends(get_report_service),
    db: Session = Depends(get_db),
) -> ReportDetailResponse:
    """Update report title or status."""
    existing = service.get_report(report_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )
    authorize_or_403(current_user, "update", existing, db)

    updates = request.model_dump(exclude_unset=True)
    report = service.update_report(report_id, updates=updates)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )
    # Reload to get sources
    report = service.get_report(report_id)
    return _build_report_detail(report)


@router.delete("/{report_id}", response_model=DeleteResponse)
def delete_report(
    report_id: UUID,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
    service: ReportService = Depends(get_report_service),
    db: Session = Depends(get_db),
) -> DeleteResponse:
    """Delete a report and its sources."""
    existing = service.get_report(report_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )
    authorize_or_403(current_user, "delete", existing, db)
    deleted = service.delete_report(report_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )
    return DeleteResponse(success=True)
