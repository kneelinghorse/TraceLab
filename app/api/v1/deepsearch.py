"""DeepSearch ingestion endpoints."""
from __future__ import annotations

from typing import Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.mission_protocol import MissionProtocolDraft
from app.models.project import Project
from app.schemas.deepsearch import (
    AutoLinkingSummary,
    DeepSearchIngestRequest,
    DeepSearchIngestResponse,
)
from app.schemas.mission import MissionCreate
from app.services.evidence_auto_linking import EvidenceAutoLinkingService
from app.services.mission_protocol_service import (
    MissionProtocolService,
    MissionProtocolServiceError,
)
from app.services.quality_gate_service import QualityGateReport, QualityGateService

router = APIRouter()

_mission_service = MissionProtocolService()
_quality_service = QualityGateService()
_auto_linker = EvidenceAutoLinkingService()


@router.post("/ingest", response_model=DeepSearchIngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_deepsearch_payload(
    payload: DeepSearchIngestRequest,
    db: Session = Depends(get_db),
) -> DeepSearchIngestResponse:
    """Accept MissionProtocolComplete JSON payloads from DeepSearch agents."""

    project = _resolve_project(db, payload)
    mission_payload = payload.mission.model_copy(deep=True)
    auto_link_result = _auto_linker.link_evidence(
        db,
        mission_payload,
        project_id=project.id if project else None,
        similarity_threshold=payload.similarity_threshold,
    )

    draft_payload = MissionProtocolDraft.model_validate(mission_payload.model_dump())
    report = _quality_service.evaluate(draft_payload, db=db)
    if not report.all_passed():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_quality_failure_payload(report, auto_link_result.as_dict()),
        )

    mission_create = MissionCreate(
        project_id=project.id if project else None,
        mission_data=draft_payload,
        status=mission_payload.status,
    )

    try:
        mission = _mission_service.create_mission(db, mission_create)
    except MissionProtocolServiceError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    mission.evidence_linking_metadata = auto_link_result.as_dict()
    db.add(mission)
    db.commit()
    db.refresh(mission)

    quality_summary = mission.quality_gates or report.as_dict()
    response = DeepSearchIngestResponse(
        mission_uuid=mission.id,
        mission_id=mission.mission_data.get("mission_id") if isinstance(mission.mission_data, Dict) else mission_payload.mission_id,
        project_id=mission.project_id,
        status=mission.status,
        quality_gates_passed=True,
        quality_gates=quality_summary,
        auto_linking=AutoLinkingSummary(**auto_link_result.as_dict()),
    )
    return response


def _resolve_project(db: Session, payload: DeepSearchIngestRequest) -> Project:
    """Determine the target project, creating one when requested."""

    if payload.project_id:
        project = db.query(Project).filter(Project.id == payload.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {payload.project_id} not found")
        return project

    if payload.auto_create_project:
        project_name = (payload.project_name or "").strip()
        if not project_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="project_name is required when auto_create_project is true",
            )
        project = Project(
            name=project_name,
            description="DeepSearch auto-created project",
            status="active",
        )
        db.add(project)
        db.flush()
        return project

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="project_id is required unless auto_create_project is true",
    )


def _quality_failure_payload(
    report: QualityGateReport,
    auto_linking: Dict[str, object],
) -> Dict[str, object]:
    """Shape error payload for quality gate failures."""

    failing = report.failing_gates()
    return {
        "success": False,
        "error": {
            "code": "QUALITY_GATE_FAILURE",
            "message": "Mission validation failed - quality gates not passed",
            "details": {
                "failing_gates": failing,
                "quality_gates": report.as_dict(),
                "mission_id": report.protocol_mission_id,
                "auto_linking": auto_linking,
            },
        },
    }
