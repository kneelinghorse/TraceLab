"""Automated quality check API endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.quality import QualityCheckRead
from app.schemas.quality_automation import (
    QualityAutomationHistoryResponse,
    QualityAutomationRunRequest,
    QualityAutomationRunResponse,
)
from app.services.mission_protocol_service import (
    MissionNotFoundError,
    MissionProtocolService,
    MissionProtocolServiceError,
)
from app.services.quality_checks import QualityAutomationService, QualityCheckRepository

router = APIRouter()
_mission_service = MissionProtocolService()
_automation_service = QualityAutomationService()
_repository = QualityCheckRepository()


def _raise_http_error(error: MissionProtocolServiceError) -> None:
    status_code = status.HTTP_404_NOT_FOUND if isinstance(error, MissionNotFoundError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.post("/run", response_model=QualityAutomationRunResponse, status_code=status.HTTP_201_CREATED)
def run_quality_automation(
    payload: QualityAutomationRunRequest,
    db: Session = Depends(get_db),
) -> QualityAutomationRunResponse:
    """Execute all automated quality checks immediately and return their audit trail entries."""
    try:
        mission = _mission_service.get_mission(db, payload.mission_id)
    except MissionProtocolServiceError as exc:
        _raise_http_error(exc)
    performed_by = payload.performed_by or "quality_automation_api"
    records = _automation_service.run_for_mission(db, mission, performed_by=performed_by)
    db.commit()
    return QualityAutomationRunResponse(
        mission_id=mission.id,
        checks=[QualityCheckRead.model_validate(record) for record in records],
    )


@router.get("/history/{mission_id}", response_model=QualityAutomationHistoryResponse)
def quality_automation_history(
    mission_id: UUID,
    db: Session = Depends(get_db),
    limit: int = 100,
) -> QualityAutomationHistoryResponse:
    """Return previously recorded automated quality checks for a mission."""
    try:
        _mission_service.get_mission(db, mission_id)
    except MissionProtocolServiceError as exc:
        _raise_http_error(exc)
    history = _repository.history_for_mission(db, mission_id, limit=limit)
    return QualityAutomationHistoryResponse(
        mission_id=mission_id,
        history=[QualityCheckRead.model_validate(item) for item in history],
    )
