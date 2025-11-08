"""Quality gate status endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.quality_gates import QualityGateReportResponse, QualityGateStatus
from app.services.mission_protocol_service import (
    MissionNotFoundError,
    MissionProtocolService,
    MissionProtocolServiceError,
)
from app.services.quality_gate_service import QualityGateService
from app.models.mission_protocol import MissionProtocolDraft


router = APIRouter()
_mission_service = MissionProtocolService()
_quality_service = QualityGateService()


def _http_error(exc: MissionProtocolServiceError) -> HTTPException:
    status_code = status.HTTP_404_NOT_FOUND if isinstance(exc, MissionNotFoundError) else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=str(exc))


@router.get("/missions/{mission_id}/quality", response_model=QualityGateReportResponse)
def mission_quality_status(mission_id: UUID, db: Session = Depends(get_db)) -> QualityGateReportResponse:
    try:
        mission = _mission_service.get_mission(db, mission_id)
    except MissionProtocolServiceError as exc:  # pragma: no cover - thin wrapper
        raise _http_error(exc) from exc

    payload = MissionProtocolDraft.model_validate(mission.mission_data)
    report = _quality_service.evaluate(payload, db=db, mission_uuid=mission.id)
    gates = {
        name: QualityGateStatus(
            gate=result.gate,
            status=result.status,
            blocking=result.blocking,
            details=result.details,
            evaluated_at=result.evaluated_at,
            metadata=dict(result.metadata) if result.metadata else None,
        )
        for name, result in report.results.items()
    }

    return QualityGateReportResponse(
        mission_id=mission.id,
        protocol_mission_id=payload.mission_id,
        evaluated_at=report.evaluated_at,
        all_passed=report.all_passed(),
        failing_gates=report.failing_gates(),
        gates=gates,
    )
