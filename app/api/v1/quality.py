"""Quality gate status endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.authorization import authorize_or_403
from app.core.database import get_db
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.models.mission_protocol import MissionProtocolDraft
from app.schemas.quality_gates import QualityGateReportResponse, QualityGateStatus
from app.services.cache_manager import get_cache_manager
from app.services.mission_protocol_service import (
    MissionNotFoundError,
    MissionProtocolService,
    MissionProtocolServiceError,
)
from app.services.quality_gate_service import QualityGateService

router = APIRouter()
_mission_service = MissionProtocolService()
_quality_service = QualityGateService()
_cache_manager = get_cache_manager()


def _http_error(exc: MissionProtocolServiceError) -> HTTPException:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if isinstance(exc, MissionNotFoundError)
        else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=status_code, detail=str(exc))


@router.get("/missions/{mission_id}/quality", response_model=QualityGateReportResponse)
def mission_quality_status(
    mission_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> QualityGateReportResponse:
    # Authorize on EVERY request, before (and independent of) the response cache —
    # a cache hit must not bypass the per-resource check.
    try:
        mission_for_authz = _mission_service.get_mission(db, mission_id)
    except MissionProtocolServiceError as exc:
        raise _http_error(exc) from exc
    authorize_or_403(user, "read", mission_for_authz, db)

    cache_key = _cache_manager.quality_gate_key(str(mission_id))

    def _loader() -> QualityGateReportResponse:
        try:
            mission = _mission_service.get_mission(db, mission_id)
        except MissionProtocolServiceError as exc:  # pragma: no cover - thin wrapper
            raise _http_error(exc) from exc

        protocol_data = (
            mission.context
            if isinstance(mission.context, dict) and "mission_id" in mission.context
            else {}
        )
        payload = (
            MissionProtocolDraft.model_validate(protocol_data)
            if protocol_data
            else MissionProtocolDraft(
                mission_id=mission.mission_id or "unknown",
                title=mission.title,
            )
        )
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

    response, _ = _cache_manager.cached_value("quality_gates", cache_key, _loader)
    return response
