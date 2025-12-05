"""Mission Protocol API endpoints."""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.mission import MissionCreate, MissionRead, MissionUpdate
from app.schemas.mission_protocol import (
    MissionExportResponse,
    MissionImportRequest,
    MissionImportResponse,
)
from app.services.mission_protocol_service import (
    MissionNotFoundError,
    MissionProtocolService,
    MissionProtocolServiceError,
)
from app.services.quality_checks import QualityAutomationRunner
from app.services.report_export import ReportExportError, ReportExportService

logger = logging.getLogger(__name__)

router = APIRouter()
_quality_runner = QualityAutomationRunner(async_enabled=True)
_service = MissionProtocolService(quality_runner=_quality_runner)
_report_export_service = ReportExportService()


def _mission_read(instance) -> MissionRead:
    return MissionRead.model_validate(instance)


def _raise_http_error(error: MissionProtocolServiceError) -> None:
    status_code = status.HTTP_404_NOT_FOUND if isinstance(error, MissionNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.get("/", response_model=List[MissionRead])
def list_missions(
    project_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
) -> List[MissionRead]:
    try:
        missions = _service.list_missions(db, project_id=project_id)
        return [_mission_read(mission) for mission in missions]
    except SQLAlchemyError as exc:
        logger.exception("Database error listing missions")
        error_str = str(exc)
        if "evidence_linking_metadata" in error_str:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database schema mismatch: missing 'evidence_linking_metadata' column. Run 'alembic upgrade head' to apply migrations.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {error_str[:200]}",
        ) from exc
    except ValidationError as exc:
        logger.exception("Validation error serializing missions")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data validation error: {str(exc)[:200]}",
        ) from exc


@router.post("/", response_model=MissionRead, status_code=status.HTTP_201_CREATED)
def create_mission(payload: MissionCreate, db: Session = Depends(get_db)) -> MissionRead:
    try:
        mission = _service.create_mission(db, payload)
        return _mission_read(mission)
    except MissionProtocolServiceError as exc:
        _raise_http_error(exc)
    except SQLAlchemyError as exc:
        logger.exception("Database error creating mission")
        error_str = str(exc)
        if "evidence_linking_metadata" in error_str:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database schema mismatch: missing 'evidence_linking_metadata' column. Run 'alembic upgrade head' to apply migrations.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {error_str[:200]}",
        ) from exc
    except ValidationError as exc:
        logger.exception("Validation error serializing mission")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data validation error: {str(exc)[:200]}",
        ) from exc
    # This return is here to satisfy type checker - the try block returns or raises
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error")


@router.get("/{mission_id}", response_model=MissionRead)
def get_mission(mission_id: UUID, db: Session = Depends(get_db)) -> MissionRead:
    try:
        mission = _service.get_mission(db, mission_id)
    except MissionProtocolServiceError as exc:
        _raise_http_error(exc)
    return _mission_read(mission)


@router.put("/{mission_id}", response_model=MissionRead)
def update_mission(
    mission_id: UUID,
    payload: MissionUpdate,
    db: Session = Depends(get_db),
) -> MissionRead:
    try:
        mission = _service.update_mission(db, mission_id, payload)
    except MissionProtocolServiceError as exc:
        _raise_http_error(exc)
    return _mission_read(mission)


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_mission(mission_id: UUID, db: Session = Depends(get_db)) -> Response:
    try:
        _service.delete_mission(db, mission_id)
    except MissionProtocolServiceError as exc:
        _raise_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/import", response_model=MissionImportResponse, status_code=status.HTTP_201_CREATED)
def import_mission_yaml(request: MissionImportRequest, db: Session = Depends(get_db)) -> MissionImportResponse:
    try:
        mission = _service.import_mission_yaml(
            db,
            project_id=request.project_id,
            yaml_text=request.yaml_text,
            promote_to_complete=request.promote_to_complete,
        )
    except MissionProtocolServiceError as exc:
        _raise_http_error(exc)
    return MissionImportResponse(mission=_mission_read(mission), promoted=request.promote_to_complete)


@router.get("/{mission_id}/export")
def export_mission(
    mission_id: UUID,
    format: str = Query("yaml", pattern=r"^(yaml|md|pdf|docx)$"),
    db: Session = Depends(get_db),
):
    normalized_format = format.lower()
    if normalized_format == "yaml":
        try:
            yaml_text = _service.export_mission_yaml(db, mission_id)
        except MissionProtocolServiceError as exc:
            _raise_http_error(exc)
        return MissionExportResponse(mission_id=mission_id, yaml_text=yaml_text)

    try:
        mission = _service.get_mission(db, mission_id)
    except MissionProtocolServiceError as exc:
        _raise_http_error(exc)

    try:
        result = _report_export_service.export(
            mission.mission_data,
            format=normalized_format,
            completion_percentage=mission.completion_percentage,
        )
    except ReportExportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    headers = {"Content-Disposition": f'attachment; filename="{result.filename}"'}
    return Response(content=result.content, media_type=result.media_type, headers=headers)
