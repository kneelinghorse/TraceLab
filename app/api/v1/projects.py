"""Project read endpoints (list/detail)."""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.pagination import PaginatedResponse
from app.schemas.project import ProjectRead
from app.services.cache_manager import get_cache_manager
from app.services.project_query_service import ProjectQueryService

router = APIRouter()
_service = ProjectQueryService()
_cache_manager = get_cache_manager()


@router.get("", response_model=PaginatedResponse[ProjectRead])
def list_projects(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        ProjectQueryService.DEFAULT_PAGE_SIZE,
        ge=1,
        le=ProjectQueryService.MAX_PAGE_SIZE,
        description="Results per page",
    ),
    search: Optional[str] = Query(None, min_length=1, max_length=200, description="Case-insensitive substring match"),
    db: Session = Depends(get_db),
):
    """Return paginated projects ordered by creation time."""
    cache_key = _cache_manager.project_metadata_key(
        kind="list",
        search=search,
        page=page,
        page_size=page_size,
    )

    def _loader() -> Dict[str, Any]:
        projects, meta = _service.list_projects(db, page=page, page_size=page_size, search=search)
        resources = [ProjectRead.model_validate(project) for project in projects]
        return {"data": resources, "pagination": meta}

    response, _ = _cache_manager.cached_value("project_metadata", cache_key, _loader)
    return response


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: UUID, db: Session = Depends(get_db)) -> ProjectRead:
    """Return a single project record."""
    cache_key = _cache_manager.project_metadata_key(kind="detail", identifier=str(project_id))

    def _loader() -> ProjectRead:
        project = _service.get_project(db, project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return ProjectRead.model_validate(project)

    result, _ = _cache_manager.cached_value("project_metadata", cache_key, _loader)
    return result
