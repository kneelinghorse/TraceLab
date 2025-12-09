"""Project CRUD endpoints (list/detail/create/update/stats)."""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.schemas.pagination import PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectRead, ProjectStats, ProjectUpdate
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


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
) -> ProjectRead:
    """Create a new project."""
    project = _service.create_project(db, data)
    # Invalidate list cache
    _cache_manager.invalidate_project_metadata()
    return ProjectRead.model_validate(project)


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
) -> ProjectRead:
    """Update an existing project."""
    project = _service.update_project(db, project_id, data)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    # Invalidate caches
    _cache_manager.invalidate_project_metadata(str(project_id))
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    confirm: bool = Query(
        False,
        description="Must be true to confirm deletion. WARNING: This deletes all "
        "associated documents, chunks, insights, and missions.",
    ),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> None:
    """Delete a project and all associated data.

    Requires authentication and explicit confirmation via confirm=true query parameter.
    This is a destructive operation that CASCADE deletes:
    - All documents in the project
    - All chunks from those documents
    - All insights derived from the project
    - All missions associated with the project
    """
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project deletion requires confirm=true query parameter. "
            "WARNING: This will delete ALL documents, chunks, insights, and missions in this project.",
        )
    deleted = _service.delete_project(db, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    # Invalidate caches
    _cache_manager.invalidate_project_metadata(str(project_id))


@router.get("/{project_id}/stats", response_model=ProjectStats)
def get_project_stats(
    project_id: UUID,
    db: Session = Depends(get_db),
) -> ProjectStats:
    """Get aggregated statistics for a project."""
    cache_key = _cache_manager.project_metadata_key(kind="stats", identifier=str(project_id))

    def _loader() -> ProjectStats:
        stats = _service.get_project_stats(db, project_id)
        if not stats:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return stats

    result, _ = _cache_manager.cached_value("project_metadata", cache_key, _loader)
    return result
