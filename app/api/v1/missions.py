"""Missions CRUD API endpoints.

Provides full CRUD operations for missions with:
- Status and project filtering on list endpoint
- Pagination support
- Proper Pydantic schema validation
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.mission import MissionCreate, MissionResponse, MissionUpdate
from app.schemas.pagination import PaginatedResponse
from app.services.mission_service import (
    MissionNotFoundError,
    MissionService,
    MissionValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter()
_service = MissionService()


def _to_response(mission) -> MissionResponse:
    """Convert Mission ORM instance to MissionResponse schema.

    Handles the field mapping between model and schema.
    """
    return MissionResponse(
        id=mission.id,
        project_id=mission.project_id,
        mission_id=mission.mission_id,
        title=mission.title,
        objective=mission.objective,
        success_criteria=mission.success_criteria or [],
        context=mission.context or {},
        deliverables=mission.deliverables or [],
        research_phases=mission.research_phases or {},
        tags=mission.tags or [],
        metadata=mission.mission_metadata or {},  # Map mission_metadata -> metadata
        status=mission.status,
        queued_at=mission.queued_at,
        started_at=mission.started_at,
        completed_at=mission.completed_at,
        deepsearch_job_id=mission.deepsearch_job_id,
        execution_metadata=mission.execution_metadata or {},
        result_document_ids=mission.result_document_ids or [],
        result_report_id=mission.result_report_id,
        result_markdown=mission.result_markdown,
        result_protocol=mission.result_protocol,
        error_message=mission.error_message,
        created_at=mission.created_at,
        updated_at=mission.updated_at,
        created_by=mission.created_by,
    )


@router.get("", response_model=PaginatedResponse[MissionResponse])
def list_missions(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        MissionService.DEFAULT_PAGE_SIZE,
        ge=1,
        le=MissionService.MAX_PAGE_SIZE,
        description="Results per page",
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by mission status (draft, queued, in_progress, completed, blocked, cancelled)",
    ),
    project_id: Optional[UUID] = Query(
        None,
        description="Filter by project UUID",
    ),
    db: Session = Depends(get_db),
) -> PaginatedResponse[MissionResponse]:
    """List missions with optional filtering and pagination.

    - **page**: Page number (1-indexed, default 1)
    - **page_size**: Results per page (1-100, default 20)
    - **status**: Filter by mission status
    - **project_id**: Filter by project UUID
    """
    try:
        missions, meta = _service.list_missions(
            db,
            page=page,
            page_size=page_size,
            status=status,
            project_id=project_id,
        )
        return PaginatedResponse(
            data=[_to_response(m) for m in missions],
            pagination=meta,
        )
    except MissionValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error listing missions")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing missions: {str(exc)[:200]}",
        ) from exc


@router.get("/{mission_id}", response_model=MissionResponse)
def get_mission(
    mission_id: UUID,
    db: Session = Depends(get_db),
) -> MissionResponse:
    """Get a mission by its UUID.

    - **mission_id**: The mission's UUID (not the human-readable mission_id)
    """
    try:
        mission = _service.get_mission(db, mission_id)
        return _to_response(mission)
    except MissionNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error getting mission")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting mission: {str(exc)[:200]}",
        ) from exc


@router.post("", response_model=MissionResponse, status_code=http_status.HTTP_201_CREATED)
def create_mission(
    data: MissionCreate,
    db: Session = Depends(get_db),
) -> MissionResponse:
    """Create a new mission.

    Required fields:
    - **mission_id**: Human-readable identifier (e.g., "B16.1")
    - **title**: Mission title (3-255 characters)
    - **objective**: What the mission aims to achieve
    - **success_criteria**: Array of measurable success conditions (at least 1)

    Optional fields:
    - **project_id**: UUID of project to associate with
    - **context**: Additional context object
    - **deliverables**: Array of expected deliverables
    - **research_phases**: Research phase configuration
    - **tags**: Array of tags for categorization
    - **metadata**: Arbitrary metadata object
    - **status**: Initial status (default: "draft")
    - **created_by**: Agent or user creating the mission
    """
    try:
        mission = _service.create_mission(db, data)
        return _to_response(mission)
    except MissionValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error creating mission")
        # Check for unique constraint violation
        if "UNIQUE constraint failed" in str(exc) or "duplicate key" in str(exc).lower():
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=f"Mission with mission_id '{data.mission_id}' already exists",
            ) from exc
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating mission: {str(exc)[:200]}",
        ) from exc


@router.put("/{mission_id}", response_model=MissionResponse)
def update_mission(
    mission_id: UUID,
    data: MissionUpdate,
    db: Session = Depends(get_db),
) -> MissionResponse:
    """Update an existing mission.

    All fields are optional - only provided fields will be updated.

    - **mission_id**: The mission's UUID (not the human-readable mission_id)
    """
    try:
        mission = _service.update_mission(db, mission_id, data)
        return _to_response(mission)
    except MissionNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except MissionValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error updating mission")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating mission: {str(exc)[:200]}",
        ) from exc


@router.delete("/{mission_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_mission(
    mission_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    """Delete a mission.

    - **mission_id**: The mission's UUID (not the human-readable mission_id)
    """
    try:
        _service.delete_mission(db, mission_id)
        return Response(status_code=http_status.HTTP_204_NO_CONTENT)
    except MissionNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error deleting mission")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting mission: {str(exc)[:200]}",
        ) from exc
