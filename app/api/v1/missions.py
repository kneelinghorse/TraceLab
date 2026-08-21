"""Missions CRUD API endpoints.

Provides full CRUD operations for missions with:
- Status and project filtering on list endpoint
- Pagination support
- Proper Pydantic schema validation
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authorization import (
    accessible_filter,
    authorize_or_403,
    authorize_service_or_403,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.mission_events import emit_mission_status_change
from app.core.security import (
    AuthenticatedUser,
    require_authenticated_principal,
    require_authenticated_user,
)
from app.schemas.evidence_ledger import (
    DeepSearchEvidenceRequest,
    DeepSearchEvidenceResponse,
)
from app.schemas.mission import (
    MissionContractPreviewResponse,
    MissionCreate,
    MissionErrorResponse,
    MissionLintErrorDetail,
    MissionResponse,
    MissionStatusResponse,
    MissionSubmitResponse,
    MissionUpdate,
    ReportPromotionResponse,
)
from app.schemas.pagination import PaginatedResponse
from app.services.auto_ingest import is_document_search_ready
from app.services.deepsearch_preview_client import (
    ContractPreviewError,
)
from app.services.deepsearch_preview_client import (
    preview_mission_contract as _call_deepsearch_preview,
)
from app.services.evidence_ledger import (
    DeepSearchEvidenceConflictError,
    DeepSearchEvidenceNotFoundError,
    DeepSearchEvidenceValidationError,
    EvidenceLedgerService,
    get_evidence_ledger_service,
)
from app.services.mission_linter import lint_mission_for_submit
from app.services.mission_service import (
    MissionNotFoundError,
    MissionService,
    MissionSubmissionStateError,
    MissionValidationError,
    validate_mission_submission_state,
)
from app.services.result_materialization import (
    DocumentMaterializationState,
    MissionResultMaterializationService,
    normalize_materialization_error_categories,
)

logger = logging.getLogger(__name__)

router = APIRouter()
service_router = APIRouter()
_service = MissionService()


def _to_response(mission) -> MissionResponse:
    """Convert Mission ORM instance to MissionResponse schema.

    Handles the field mapping between model and schema.
    """
    # Get project name if project relationship is loaded
    project_name = None
    if mission.project_id and mission.project:
        project_name = mission.project.name

    # constraints fallback: old missions stored constraints inside context.
    # MissionResponse has its own field_validator for this, but it only fires
    # with from_attributes mode — since we're constructing MissionResponse
    # explicitly here, resolve the fallback up-front.
    resolved_constraints = mission.constraints
    if not resolved_constraints and isinstance(mission.context, dict):
        legacy = mission.context.get("constraints")
        if legacy:
            resolved_constraints = legacy

    return MissionResponse(
        id=mission.id,
        project_id=mission.project_id,
        project_name=project_name,
        mission_id=mission.mission_id,
        title=mission.title,
        objective=mission.objective,
        success_criteria=mission.success_criteria or [],
        context=mission.context or {},
        deliverables=mission.deliverables or [],
        research_phases=mission.research_phases or {},
        tags=mission.tags or [],
        metadata=mission.mission_metadata or {},  # Map mission_metadata -> metadata
        # Mission-authoring fields (T40.1/T40.2).
        background=mission.background,
        focus=mission.focus,
        references=mission.references,
        required_entities=mission.required_entities,
        excluded_entities=mission.excluded_entities,
        expected_output_schema=mission.expected_output_schema,
        coverage_thresholds=mission.coverage_thresholds,
        validation_thresholds=mission.validation_thresholds,
        deliverable_format=mission.deliverable_format,
        max_loops=mission.max_loops,
        min_loops=mission.min_loops,
        constraints=resolved_constraints,
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


def _get_mission_by_id_or_mission_id(db: Session, mission_id_str: str):
    """Resolve mission by UUID or human-readable mission_id."""
    try:
        return _service.get_mission(db, UUID(mission_id_str))
    except (ValueError, MissionNotFoundError):
        pass
    return _service.get_mission_by_mission_id(db, mission_id_str)


def _build_actionable_detail(
    *,
    message: str,
    mission=None,
    suggestion: str | None = None,
    current_status: str | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {"message": message}
    if mission is not None:
        detail["mission_id"] = mission.mission_id
        detail["uuid"] = str(mission.id)
    if suggestion:
        detail["suggestion"] = suggestion
    if current_status:
        detail["current_status"] = current_status
    return detail


def _submit_existing_mission(
    *,
    db: Session,
    mission,
) -> MissionSubmitResponse:
    """Validate and queue an existing mission for DeepSearch."""
    if not mission.project_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=_build_actionable_detail(
                message="Mission must have project_id set before submission.",
                mission=mission,
                suggestion=f"Use PATCH /api/v1/missions/{mission.id} to set project_id first.",
            ),
        )

    if not mission.success_criteria or len(mission.success_criteria) == 0:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=_build_actionable_detail(
                message="Mission must have at least one success criterion before submission.",
                mission=mission,
                suggestion=f"Use PATCH /api/v1/missions/{mission.id} to add success_criteria.",
            ),
        )

    try:
        validate_mission_submission_state(mission)
    except MissionSubmissionStateError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=_build_actionable_detail(
                message=str(exc),
                mission=mission,
                suggestion=exc.suggestion,
                current_status=mission.status,
            ),
        ) from exc

    # Submit-time lint gate (T40.3). Hard errors block submit with 422;
    # warnings ride along with the success response so authors can triage.
    lint_result = lint_mission_for_submit(mission)
    if lint_result.has_errors:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=MissionLintErrorDetail(
                errors=[v.to_dict() for v in lint_result.errors],  # type: ignore[arg-type]
                warnings=[v.to_dict() for v in lint_result.warnings],  # type: ignore[arg-type]
            ).model_dump(),
        )

    deepsearch_mode = getattr(settings, "deepsearch_mode", "worker").lower()
    update_data = MissionUpdate(status="queued")
    updated_mission = _service.update_mission(db, mission.id, update_data)

    message = (
        "Mission queued for DeepSearch worker."
        if deepsearch_mode == "worker"
        else "Mission submitted to DeepSearch via HTTP."
    )

    logger.info(
        "Mission %s submitted (mode=%s)",
        updated_mission.mission_id,
        deepsearch_mode,
    )

    emit_mission_status_change(
        mission_id=updated_mission.mission_id or str(updated_mission.id),
        title=updated_mission.title or "Untitled",
        new_status="queued",
        previous_status=mission.status,
    )

    return MissionSubmitResponse(
        status="queued",
        mode=deepsearch_mode,
        mission_id=updated_mission.mission_id,
        uuid=updated_mission.id,
        message=message,
        job_id=updated_mission.deepsearch_job_id,
        warnings=[v.to_dict() for v in lint_result.warnings],  # type: ignore[arg-type]
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
    status: str | None = Query(
        None,
        description="Filter by mission status (draft, queued, in_progress, completed, blocked, cancelled, validation_failed)",
    ),
    project_id: UUID | None = Query(
        None,
        description="Filter by project UUID",
    ),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> PaginatedResponse[MissionResponse]:
    """List missions with optional filtering and pagination.

    - **page**: Page number (1-indexed, default 1)
    - **page_size**: Results per page (1-100, default 20)
    - **status**: Filter by mission status
    - **project_id**: Filter by project UUID

    With RBAC enabled, non-privileged callers see only missions they own or whose
    owning project is in a Space they belong to (T47.3).
    """
    from app.models.mission import Mission

    try:
        missions, meta = _service.list_missions(
            db,
            page=page,
            page_size=page_size,
            status=status,
            project_id=project_id,
            access_filter=accessible_filter(user, Mission, db),
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


@router.get(
    "/{mission_id}",
    response_model=MissionResponse,
    summary="Get mission by UUID or mission_id",
    responses={
        404: {
            "description": "Mission not found",
            "model": MissionErrorResponse,
        },
    },
)
def get_mission(
    mission_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> MissionResponse:
    """Get a mission by UUID or human-readable mission_id.

    - **mission_id**: UUID or mission_id (e.g. `B16.1`)
    """
    try:
        mission = _get_mission_by_id_or_mission_id(db, mission_id)
        authorize_or_403(user, "read", mission, db)
        return _to_response(mission)
    except MissionNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=_build_actionable_detail(
                message=str(exc),
                suggestion="Check mission_id spelling or query GET /api/v1/missions to list available missions.",
            ),
        ) from exc
    except HTTPException:
        # authorize_or_403's 403 (and any other HTTP error) must propagate
        # unchanged, not be re-wrapped as 500 by the catch-all below.
        raise
    except Exception as exc:
        logger.exception("Error getting mission")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting mission: {str(exc)[:200]}",
        ) from exc


@router.get(
    "/{mission_id}/status",
    response_model=MissionStatusResponse,
    summary="Get lightweight mission lifecycle and result-readiness state",
)
def get_mission_status(
    mission_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> MissionStatusResponse:
    """Poll mission progress without returning large results or worker proofs."""
    try:
        mission = _get_mission_by_id_or_mission_id(db, mission_id)
    except MissionNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=_build_actionable_detail(
                message=str(exc),
                suggestion="Check mission_id spelling or list missions via GET /api/v1/missions.",
            ),
        ) from exc

    authorize_or_403(user, "read", mission, db)

    metadata = mission.execution_metadata or {}
    raw_progress = metadata.get("progress_percent")
    progress_percent = None
    if (
        isinstance(raw_progress, int | float)
        and not isinstance(raw_progress, bool)
        and 0 <= raw_progress <= 100
    ):
        progress_percent = int(raw_progress)

    raw_phase = metadata.get("current_phase")
    current_phase = raw_phase if isinstance(raw_phase, str) else None

    document_ids: list[UUID] = []
    has_invalid_document_ids = False
    for value in mission.result_document_ids or []:
        try:
            document_ids.append(UUID(str(value)))
        except (TypeError, ValueError):
            has_invalid_document_ids = True
    search_ready = False
    if document_ids:
        from app.models.document import Document

        documents = (
            db.query(Document)
            .filter(
                Document.id.in_(document_ids),
                Document.deleted_at.is_(None),
            )
            .all()
        )
        search_ready = (
            not has_invalid_document_ids
            and len(documents) == len(set(document_ids))
            and all(is_document_search_ready(document) for document in documents)
        )

    is_terminal_result = mission.status in {"completed", "validation_failed"}
    document_state = MissionResultMaterializationService.document_materialization_state(
        db, mission
    )
    document_pending = (
        document_state is DocumentMaterializationState.NEEDS
    )
    report_pending = MissionResultMaterializationService.report_needs_materialization(
        db, mission
    )
    materialization_pending = is_terminal_result and (
        document_pending or report_pending
    )
    raw_materialization = metadata.get("result_materialization")
    materialization_state = (
        raw_materialization if isinstance(raw_materialization, dict) else {}
    )
    raw_materialization_status = materialization_state.get("status")
    materialization_status = (
        raw_materialization_status
        if isinstance(raw_materialization_status, str)
        else None
    )
    raw_materialization_attempts = materialization_state.get("attempt_count")
    materialization_attempt_count = (
        raw_materialization_attempts
        if isinstance(raw_materialization_attempts, int)
        and not isinstance(raw_materialization_attempts, bool)
        and raw_materialization_attempts >= 0
        else 0
    )
    raw_materialization_errors = materialization_state.get("error_categories")
    error_categories: list[str] = []
    materialization_error = None
    if isinstance(raw_materialization_errors, list) and raw_materialization_errors:
        error_categories = normalize_materialization_error_categories(
            raw_materialization_errors
        )
        materialization_error = error_categories[0] if error_categories else None

    if is_terminal_result:
        if document_state is DocumentMaterializationState.BLOCKED_TOMBSTONE:
            materialization_status = (
                "failed" if error_categories else "blocked_soft_deleted"
            )
        elif not error_categories and (document_pending or report_pending):
            materialization_status = "pending"
        elif materialization_status == "blocked_soft_deleted":
            materialization_status = "ready"

    return MissionStatusResponse(
        id=mission.id,
        mission_id=mission.mission_id,
        status=mission.status,
        progress_percent=progress_percent,
        current_phase=current_phase,
        queued_at=mission.queued_at,
        started_at=mission.started_at,
        completed_at=mission.completed_at,
        error_message=mission.error_message,
        deepsearch_job_id=mission.deepsearch_job_id,
        deepsearch_attempt_count=mission.deepsearch_attempt_count or 0,
        lease_expires_at=mission.deepsearch_lease_expires_at,
        result_document_ids=document_ids,
        result_report_id=mission.result_report_id,
        materialization_pending=materialization_pending,
        materialization_status=materialization_status,
        materialization_attempt_count=materialization_attempt_count,
        materialization_error=materialization_error,
        search_ready=search_ready,
    )


@router.post(
    "", response_model=MissionResponse, status_code=http_status.HTTP_201_CREATED
)
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
        if (
            "UNIQUE constraint failed" in str(exc)
            or "duplicate key" in str(exc).lower()
        ):
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=f"Mission with mission_id '{data.mission_id}' already exists",
            ) from exc
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating mission: {str(exc)[:200]}",
        ) from exc


@router.post(
    "/create-and-submit",
    response_model=MissionSubmitResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create and submit a mission in one request",
    responses={
        400: {
            "description": "Validation or submission precondition failed",
            "model": MissionErrorResponse,
        },
        409: {
            "description": "mission_id already exists",
            "model": MissionErrorResponse,
        },
    },
)
def create_and_submit_mission(
    data: MissionCreate,
    db: Session = Depends(get_db),
) -> MissionSubmitResponse:
    """Create a mission and immediately queue it for DeepSearch execution."""
    try:
        mission = _service.create_mission(db, data)
        submit_response = _submit_existing_mission(db=db, mission=mission)
        submit_response.message = (
            f"Mission created and {submit_response.message.lower()}"
        )
        return submit_response
    except HTTPException:
        raise
    except MissionValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=_build_actionable_detail(
                message=str(exc),
                suggestion="Review request payload fields and retry.",
            ),
        ) from exc
    except Exception as exc:
        logger.exception("Error creating and submitting mission")
        if (
            "UNIQUE constraint failed" in str(exc)
            or "duplicate key" in str(exc).lower()
        ):
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=_build_actionable_detail(
                    message=f"Mission with mission_id '{data.mission_id}' already exists.",
                    mission=None,
                    suggestion=f"Use GET /api/v1/missions/{data.mission_id} or choose a new mission_id.",
                ),
            ) from exc
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating and submitting mission: {str(exc)[:200]}",
        ) from exc


@router.patch("/{mission_id}", response_model=MissionResponse)
def update_mission(
    mission_id: UUID,
    data: MissionUpdate,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> MissionResponse:
    """Update an existing mission.

    All fields are optional - only provided fields will be updated.

    When status transitions to 'completed' with result_protocol, auto-creates a Report.

    - **mission_id**: The mission's UUID (not the human-readable mission_id)
    """
    try:
        # Get current mission state before update
        old_mission = _service.get_mission(db, mission_id)
        authorize_or_403(user, "update", old_mission, db)
        old_status = old_mission.status
        old_has_report = old_mission.result_report_id is not None

        # T41.5: re-parenting requires the target project to exist. Validate
        # here so we can return a clean 404 instead of a FK-violation 500.
        if data.project_id is not None and data.project_id != old_mission.project_id:
            from app.models.project import Project

            target = db.query(Project).filter(Project.id == data.project_id).first()
            if target is None:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=_build_actionable_detail(
                        message=(
                            f"Cannot re-parent mission to project {data.project_id} "
                            "— project does not exist."
                        ),
                        suggestion="List existing projects via GET /api/v1/projects to find a valid project_id.",
                    ),
                )

        mission = _service.update_mission(db, mission_id, data)

        # Emit status change event
        if data.status and data.status != old_status:
            emit_mission_status_change(
                mission_id=mission.mission_id or str(mission.id),
                title=mission.title or "Untitled",
                new_status=data.status,
                previous_status=old_status,
            )

        # Auto-create report if transitioning to completed with result_protocol
        # and no report exists yet
        if (
            data.status == "completed"
            and old_status != "completed"
            and mission.result_protocol
            and mission.project_id
            and not old_has_report
            and not mission.result_report_id
        ):
            try:
                from app.services.auto_report import AutoReportService

                auto_report_service = AutoReportService()
                report = auto_report_service.create_report_from_protocol(
                    db=db,
                    mission=mission,
                    protocol=mission.result_protocol,
                )
                logger.info(
                    "Auto-created report %s for mission %s on completion",
                    report.id,
                    mission.mission_id,
                )
                # Refresh to get the updated result_report_id
                db.refresh(mission)
            except Exception as report_exc:
                # Log but don't fail the update - mission is already completed
                logger.warning(
                    "Auto-report creation failed for mission %s: %s",
                    mission.mission_id,
                    str(report_exc),
                )

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
    except HTTPException:
        # T41.5: re-parent target-project-not-found raises HTTPException(404)
        # inside the try; bubble it up cleanly instead of letting the generic
        # handler below wrap it as 500.
        raise
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
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> Response:
    """Delete a mission.

    - **mission_id**: The mission's UUID (not the human-readable mission_id)
    """
    try:
        mission = _service.get_mission(db, mission_id)
        authorize_or_403(user, "delete", mission, db)
        _service.delete_mission(db, mission_id)
        return Response(status_code=http_status.HTTP_204_NO_CONTENT)
    except MissionNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except HTTPException:
        # authorize_or_403's 403 must propagate, not be re-wrapped as 500.
        raise
    except Exception as exc:
        logger.exception("Error deleting mission")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting mission: {str(exc)[:200]}",
        ) from exc


@router.get("/{mission_id}/export", summary="Export mission as YAML or Markdown")
def export_mission(
    mission_id: str,
    format: str = Query(default="yaml", description="Export format: yaml or md"),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Export a mission in the requested format."""
    from fastapi.responses import PlainTextResponse

    from app.services.mission_protocol_service import MissionProtocolService

    try:
        mission = _get_mission_by_id_or_mission_id(db, mission_id)
    except MissionNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    authorize_or_403(user, "read", mission, db)

    protocol_service = MissionProtocolService()
    if format == "md":
        lines = [
            f"# {mission.title}",
            "",
            f"**Mission ID:** {mission.mission_id}",
            f"**Status:** {mission.status}",
            "",
            "## Objective",
            mission.objective or "",
            "",
            "## Success Criteria",
        ]
        for criterion in mission.success_criteria or []:
            lines.append(f"- {criterion}")
        if mission.tags:
            lines.append("")
            lines.append("## Tags")
            lines.append(", ".join(mission.tags))
        content = "\n".join(lines)
        return PlainTextResponse(content, media_type="text/markdown")

    yaml_content = protocol_service.export_mission_yaml(db, mission.id)
    return PlainTextResponse(yaml_content, media_type="text/yaml")


@router.post(
    "/import",
    status_code=http_status.HTTP_201_CREATED,
    summary="Import mission from YAML",
)
def import_mission(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
):
    """Import a mission from a YAML payload."""
    from app.services.mission_protocol_service import MissionProtocolService

    project_id = payload.get("project_id")
    yaml_text = payload.get("yaml_text", "")
    promote = payload.get("promote_to_complete", False)

    if not project_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="project_id is required",
        )

    protocol_service = MissionProtocolService()
    try:
        mission = protocol_service.import_mission_yaml(
            db,
            project_id=UUID(project_id),
            yaml_text=yaml_text,
            promote_to_complete=promote,
        )
        return {"mission": _to_response(mission).model_dump(mode="json")}
    except Exception as exc:
        logger.exception("Error importing mission YAML")
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/{mission_id}/submit",
    response_model=MissionSubmitResponse,
    summary="Submit mission by UUID or mission_id",
    responses={
        400: {
            "description": "Submission precondition failed",
            "model": MissionErrorResponse,
        },
        404: {
            "description": "Mission not found",
            "model": MissionErrorResponse,
        },
    },
)
def submit_mission(
    mission_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> MissionSubmitResponse:
    """Submit a mission for DeepSearch execution.

    Sets the mission status to 'queued' so the DeepSearch worker can pick it up.

    Validates:
    - Mission exists
    - Mission is associated with a project
    - Mission has at least one success criterion
    - Mission is not already queued or in progress

    - **mission_id**: UUID or mission_id (e.g. `B16.1`)
    """
    try:
        mission = _get_mission_by_id_or_mission_id(db, mission_id)
        authorize_or_403(user, "submit", mission, db)
        return _submit_existing_mission(db=db, mission=mission)

    except MissionNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=_build_actionable_detail(
                message=str(exc),
                suggestion="Check mission_id spelling or query GET /api/v1/missions to list available missions.",
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error submitting mission")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting mission: {str(exc)[:200]}",
        ) from exc


@router.get(
    "/{mission_id}/contract-preview",
    response_model=MissionContractPreviewResponse,
    summary="Preview the compiled DeepSearch contract for a mission (T40.4)",
    responses={
        404: {"description": "Mission not found", "model": MissionErrorResponse},
        502: {"description": "Upstream DeepSearch preview call failed"},
    },
)
def contract_preview(
    mission_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> MissionContractPreviewResponse:
    """Compile a structural mission preview using TraceLab's pinned vendor.

    No outbound request is made. The response discloses the compiler revision
    and fidelity so authors can distinguish this structural preview from the
    newer DeepSearch runtime until cross-repo golden parity is restored. No
    mission-state change is made.
    """
    try:
        mission = _get_mission_by_id_or_mission_id(db, mission_id)
    except MissionNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=_build_actionable_detail(
                message=str(exc),
                suggestion="Check the mission_id spelling or list missions via GET /api/v1/missions.",
            ),
        ) from exc
    authorize_or_403(user, "read", mission, db)

    try:
        preview = _call_deepsearch_preview(mission)
    except ContractPreviewError as exc:
        # Upstream HTTP errors (4xx from DeepSearch) surface with the same
        # status so authors see the compiler's own validation feedback.
        if exc.status_code and 400 <= exc.status_code < 500:
            raise HTTPException(
                status_code=exc.status_code,
                detail={
                    "message": "DeepSearch preview rejected the mission.",
                    "upstream_status": exc.status_code,
                    "upstream_detail": exc.detail,
                },
            ) from exc
        # Everything else = transport / config / server-side upstream issue.
        logger.exception("Contract preview failed for mission %s", mission_id)
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": str(exc),
                "upstream_status": exc.status_code,
                "upstream_detail": exc.detail,
            },
        ) from exc

    return MissionContractPreviewResponse(
        mission_id=mission.mission_id,
        mission_uuid=mission.id,
        project_id=mission.project_id,
        **preview.to_dict(),
    )


@router.post("/{mission_id}/promote-report", response_model=ReportPromotionResponse)
def promote_mission_report(
    mission_id: UUID,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> ReportPromotionResponse:
    """Promote a mission's report/markdown to a searchable document.

    Takes the mission's result_report OR result_markdown and creates a new document
    from its content, running it through the chunking and embedding pipeline so
    synthesized research feeds back into future searches.

    Validates:
    - Mission exists
    - Mission status is 'completed'
    - Mission has result_report_id OR result_markdown
    - Content has not already been promoted

    - **mission_id**: The mission's UUID
    """
    from app.models.report import Report
    from app.services.report_promotion import (
        ReportAlreadyPromotedError,
        ReportPromotionError,
        get_report_promotion_service,
    )

    try:
        # Get mission
        mission = _service.get_mission(db, mission_id)
        authorize_or_403(user, "promote", mission, db)

        # Validate mission is completed
        if mission.status != "completed":
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Mission must be completed to promote report (current status: {mission.status})",
            )

        # Validate mission has promotable content (report OR markdown)
        if not mission.result_report_id and not mission.result_markdown:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Mission has no result report or markdown to promote",
            )

        promotion_service = get_report_promotion_service()

        # Check if already promoted (either via report or markdown)
        from app.models.document import Document

        existing_doc = (
            db.query(Document).filter(Document.source_mission_id == mission.id).first()
        )
        if existing_doc:
            raise ReportAlreadyPromotedError(
                f"Mission {mission.mission_id} has already been promoted to document {existing_doc.id}"
            )

        # Try to promote from report first, fall back to markdown
        if mission.result_report_id:
            report = (
                db.query(Report).filter(Report.id == mission.result_report_id).first()
            )
            if report:
                document = promotion_service.promote_report(db, mission, report)
                logger.info(
                    "Promoted report %s from mission %s to document %s",
                    report.id,
                    mission.mission_id,
                    document.id,
                )
            else:
                # Report ID set but report not found - fall through to markdown
                logger.warning(
                    "Report %s not found for mission %s, falling back to result_markdown",
                    mission.result_report_id,
                    mission.mission_id,
                )
                document = promotion_service.promote_markdown(db, mission)
        else:
            # No report, promote directly from markdown
            document = promotion_service.promote_markdown(db, mission)
            logger.info(
                "Promoted result_markdown from mission %s to document %s",
                mission.mission_id,
                document.id,
            )

        chunk_count = len(document.chunks) if document.chunks else 0
        status = "completed" if document.embedded else "processing"

        return ReportPromotionResponse(
            document_id=document.id,
            document_name=document.name,
            status=status,
            message="Report promoted to document. Processing complete."
            if status == "completed"
            else "Report promoted to document. Processing started.",
            chunk_count=chunk_count,
        )

    except MissionNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ReportAlreadyPromotedError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ReportPromotionError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error promoting mission report")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error promoting report: {str(exc)[:200]}",
        ) from exc


# ---------------------------------------------------------------------------
# Mission log ingestion + retrieval (T39.3)
# ---------------------------------------------------------------------------

class LogEntry(BaseModel):
    level: str = "INFO"
    message: str
    source: str | None = Field(
        default=None,
        validation_alias=AliasChoices("source", "phase"),
    )
    logged_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("logged_at", "ts"),
    )


class LogBatchRequest(BaseModel):
    logs: list[LogEntry] = Field(
        validation_alias=AliasChoices("logs", "entries"),
    )


class LogEntryResponse(BaseModel):
    id: str
    level: str
    message: str
    source: str | None
    logged_at: datetime
    created_at: datetime


@service_router.post(
    "/{mission_id}/logs",
    status_code=http_status.HTTP_201_CREATED,
    summary="Ingest a batch of log records for a mission",
)
def ingest_mission_logs(
    mission_id: UUID,
    payload: LogBatchRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_principal),
) -> dict:
    """Accept a batch of log lines from the DeepSearch runner.

    Called by TracelabLogHandler in the DeepSearch service. This is a
    service-to-service WRITE, so it is gated to a SERVICE PRINCIPAL (role 'service')
    via ``authorize_service_or_403`` (T47.4) instead of the per-user ``authorize()``
    used on the human-facing routes. This closes decision #260(3): a human-auth
    token (any role, including owner/admin) can no longer append/spoof log records
    on an arbitrary mission by id — only the runner's service principal can. The
    gate is a no-op while ``rbac_enabled`` is False, so flip-back stays byte-
    identical and the deployed runner is unaffected until its account is
    provisioned as a service principal ahead of the flip (T47.6 runbook). The
    human-facing READ side (GET .../logs) IS authorize()-gated below.
    """
    authorize_service_or_403(user)

    from app.models.mission_log import MissionLog

    mission = _service.get_mission(db, mission_id)

    now = datetime.utcnow()
    records = [
        MissionLog(
            mission_id=mission.id,
            level=(entry.level or "INFO").upper()[:20],
            message=entry.message,
            source=entry.source,
            logged_at=entry.logged_at or now,
            created_at=now,
        )
        for entry in payload.logs
    ]

    db.add_all(records)
    db.commit()

    return {"accepted": len(records)}


@service_router.post(
    "/{mission_id}/evidence",
    response_model=DeepSearchEvidenceResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Project a completed DeepSearch result into the Evidence Ledger",
    responses={
        http_status.HTTP_200_OK: {
            "description": "Exact replay; returns the original stable entry identifiers.",
            "model": DeepSearchEvidenceResponse,
        }
    },
)
def capture_mission_evidence(
    mission_id: UUID,
    payload: DeepSearchEvidenceRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_principal),
    ledger_service: EvidenceLedgerService = Depends(get_evidence_ledger_service),
) -> DeepSearchEvidenceResponse:
    """Trigger a server-owned, idempotent projection of persisted evidence.

    The service-principal gate deliberately runs before any mission lookup so
    human callers cannot use this trusted write surface as an identifier oracle.
    The request carries only the persisted job correlation key; evidence and
    tenancy fields are derived from the completed mission and its live project.
    """
    authorize_service_or_403(user, enforce_when_disabled=True)
    try:
        result = ledger_service.capture_deepsearch_mission_evidence(
            db,
            mission_id,
            payload.deepsearch_job_id,
        )
    except DeepSearchEvidenceNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DeepSearchEvidenceConflictError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DeepSearchEvidenceValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception(
            "DeepSearch evidence projection failed for mission %s",
            mission_id,
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DeepSearch evidence projection failed",
        ) from exc

    if result.status == "already_processed":
        response.status_code = http_status.HTTP_200_OK
    return DeepSearchEvidenceResponse(
        status=result.status,
        mission_id=result.mission_id,
        deepsearch_job_id=result.deepsearch_job_id,
        session_key=result.session_key,
        entry_ids=result.entry_ids,
        entry_count=result.entry_count,
    )


@router.get(
    "/{mission_id}/logs",
    response_model=list[LogEntryResponse],
    summary="Retrieve recent log records for a mission",
)
def get_mission_logs(
    mission_id: UUID,
    limit: int = Query(default=100, ge=1, le=500, description="Max log lines to return"),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[LogEntryResponse]:
    """Return the most recent log lines for a mission, newest last."""
    from app.models.mission_log import MissionLog

    mission = _service.get_mission(db, mission_id)
    authorize_or_403(user, "read", mission, db)

    logs = (
        db.query(MissionLog)
        .filter(MissionLog.mission_id == mission.id)
        .order_by(MissionLog.logged_at.desc())
        .limit(limit)
        .all()
    )
    logs.reverse()

    return [
        LogEntryResponse(
            id=str(log.id),
            level=log.level,
            message=log.message,
            source=log.source,
            logged_at=log.logged_at,
            created_at=log.created_at,
        )
        for log in logs
    ]
