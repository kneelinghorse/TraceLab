"""DeepSearch ingestion and worker health endpoints."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.mission_protocol import MissionProtocolDraft
from app.models.project import Project
from app.schemas.deepsearch import (
    AutoLinkingSummary,
    CorrectionQueueInfo,
    DeepSearchIngestRequest,
    DeepSearchIngestResponse,
    WorkerHealthResponse,
)
from app.services.correction_queue import get_correction_queue
from app.services.evidence_auto_linking import EvidenceAutoLinkingService
from app.services.mission_protocol_service import (
    MissionProtocolService,
    MissionProtocolServiceError,
)
from app.services.ownership import default_workspace_id
from app.services.quality_gate_service import QualityGateReport, QualityGateService

logger = logging.getLogger(__name__)

router = APIRouter()

_mission_service = MissionProtocolService()
_quality_service = QualityGateService()
_auto_linker = EvidenceAutoLinkingService()


@router.post(
    "/ingest",
    response_model=DeepSearchIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
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

    try:
        mission = _mission_service.create_mission_from_draft(
            db,
            project_id=project.id,
            draft=draft_payload,
            requested_status=mission_payload.status,
        )
    except MissionProtocolServiceError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    execution_metadata = dict(mission.execution_metadata or {})
    execution_metadata["evidence_linking"] = auto_link_result.as_dict()
    mission.execution_metadata = execution_metadata
    db.add(mission)
    db.commit()
    db.refresh(mission)

    # Queue failed auto-link items for async correction
    correction_info: CorrectionQueueInfo | None = None
    if auto_link_result.failed > 0:
        correction_queue = get_correction_queue()
        evidence_summaries = {
            ev.evidence_id: ev.summary or "" for ev in (mission_payload.evidence or [])
        }
        queued_ids = correction_queue.queue_failed_items(
            mission_uuid=mission.id,
            mission_id=mission_payload.mission_id,
            project_id=mission.project_id,
            result=auto_link_result,
            callback_url=payload.callback_url,
            evidence_summaries=evidence_summaries,
        )
        if queued_ids:
            correction_info = CorrectionQueueInfo(
                queued_count=len(queued_ids),
                correction_ids=queued_ids,
                callback_url=payload.callback_url,
            )

    quality_summary = (mission.execution_metadata or {}).get(
        "quality_gates", report.as_dict()
    )
    response = DeepSearchIngestResponse(
        mission_uuid=mission.id,
        mission_id=mission.mission_id,
        project_id=mission.project_id,
        status=mission.status,
        quality_gates_passed=True,
        quality_gates=quality_summary,
        auto_linking=AutoLinkingSummary(**auto_link_result.as_dict()),
        corrections=correction_info,
    )
    return response


def _resolve_project(db: Session, payload: DeepSearchIngestRequest) -> Project:
    """Determine the target project, creating one when requested."""

    if payload.project_id:
        project = db.query(Project).filter(Project.id == payload.project_id).first()
        if not project:
            raise HTTPException(
                status_code=404, detail=f"Project {payload.project_id} not found"
            )
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
            # Same server-side default-Space assignment as the project CRUD path
            # (T44.4) so DeepSearch-created projects are not left space-less.
            workspace_id=default_workspace_id(db),
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
    auto_linking: dict[str, object],
) -> dict[str, object]:
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


@router.get(
    "/worker/health",
    response_model=WorkerHealthResponse,
    summary="Get DeepSearch worker health",
    description="Proxy endpoint to fetch health status from the DeepSearch worker service.",
)
async def get_worker_health() -> WorkerHealthResponse:
    """Fetch health status from the DeepSearch worker.

    Proxies to the worker's /health endpoint to avoid CORS issues.
    Returns offline status with error message if the worker is unreachable.
    """
    health_url = settings.deepsearch_worker_health_url

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(health_url)

            if response.is_success:
                data = response.json()
                return WorkerHealthResponse(
                    status=data.get("status", "unknown"),
                    uptime_seconds=data.get("uptime_seconds"),
                    missions_processed=data.get("missions_processed", 0),
                    missions_completed=data.get("missions_completed", 0),
                    missions_failed=data.get("missions_failed", 0),
                    current_mission_id=data.get("current_mission_id"),
                    poll_interval=data.get("poll_interval"),
                )
            else:
                logger.warning(
                    "DeepSearch worker health check failed: HTTP %d",
                    response.status_code,
                )
                return WorkerHealthResponse(
                    status="offline",
                    error=f"Worker returned HTTP {response.status_code}",
                )

    except httpx.TimeoutException:
        logger.warning("DeepSearch worker health check timed out")
        return WorkerHealthResponse(
            status="offline",
            error="Connection timed out",
        )

    except httpx.RequestError as e:
        logger.warning("DeepSearch worker health check failed: %s", str(e))
        return WorkerHealthResponse(
            status="offline",
            error=f"Connection error: {str(e)}",
        )
