"""Mission Protocol service APIs for CRUD, YAML import/export, and progress tracking."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.mission import Mission
from app.models.mission_protocol import MissionProtocolDraft
from app.schemas.mission import MissionCreate, MissionUpdate
from app.services.cache_manager import get_cache_manager
from app.services.evidence_linking import EvidenceLinkingService
from app.services.mission_progress import MissionProgressSnapshot, derive_status, evaluate_progress
from app.services.quality_gate_service import QualityGateReport, QualityGateService
from app.services.quality_checks import QualityAutomationRunner
from app.services.yaml_handler import dump_mission_yaml, load_mission_yaml


class MissionProtocolServiceError(RuntimeError):
    """Raised when mission protocol operations fail."""


class MissionNotFoundError(MissionProtocolServiceError):
    """Raised when a mission could not be located."""


# Status mapping from MissionProtocolDraft statuses to Mission model statuses
_PROTOCOL_STATUS_MAP = {
    "complete": "completed",
    "in_progress": "in_progress",
    "review": "in_progress",
    "draft": "draft",
}


def _map_protocol_status(protocol_status: Optional[str]) -> str:
    """Map MissionProtocolDraft status literals to Mission model status literals."""
    if not protocol_status:
        return "draft"
    return _PROTOCOL_STATUS_MAP.get(protocol_status, protocol_status)


class MissionProtocolService:
    """Encapsulates Mission Protocol CRUD + YAML workflows."""

    def __init__(
        self,
        *,
        evidence_service: EvidenceLinkingService | None = None,
        quality_gate_service: QualityGateService | None = None,
        quality_runner: QualityAutomationRunner | None = None,
    ) -> None:
        self.evidence_service = evidence_service or EvidenceLinkingService()
        self.quality_gate_service = quality_gate_service or QualityGateService()
        self.quality_runner = quality_runner or QualityAutomationRunner(async_enabled=False)
        self.cache_manager = get_cache_manager()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def list_missions(self, db: Session, *, project_id: Optional[UUID] = None) -> List[Mission]:
        query = db.query(Mission)
        if project_id:
            query = query.filter(Mission.project_id == project_id)
        return query.order_by(Mission.created_at.desc()).all()

    def get_mission(self, db: Session, mission_id: UUID) -> Mission:
        mission = db.query(Mission).filter(Mission.id == mission_id).one_or_none()
        if not mission:
            raise MissionNotFoundError(f"Mission {mission_id} not found")
        return mission

    def create_mission_from_draft(
        self,
        db: Session,
        *,
        project_id: UUID,
        draft: Union[MissionProtocolDraft, Dict[str, Any]],
        requested_status: Optional[str] = None,
    ) -> Mission:
        """Create a mission from a MissionProtocolDraft.

        This is the primary entry point for protocol-based mission creation.
        Maps draft fields to Mission model explicit columns.
        """
        if not project_id:
            raise MissionProtocolServiceError("project_id is required to create a mission")

        draft = self._ensure_draft(draft)
        report = self.quality_gate_service.evaluate(draft, db=db)
        snapshot = evaluate_progress(draft)
        status = self._determine_status(snapshot, requested_status, report)
        mapped_status = _map_protocol_status(status)

        # Extract objective from research_statement or summary
        objective = ""
        if draft.research_statement and draft.research_statement.objective:
            objective = draft.research_statement.objective
        elif draft.summary:
            objective = draft.summary
        else:
            objective = draft.title or f"Mission {draft.mission_id}"

        # Extract success criteria from key_questions
        success_criteria = []
        if draft.key_questions:
            success_criteria = [kq.question for kq in draft.key_questions if kq.question]
        if not success_criteria:
            success_criteria = ["Complete mission protocol"]

        # Store quality gates and full protocol in context for reference
        quality_gates = self._merged_quality_gates(snapshot, None)
        protocol_data = draft.model_dump(mode="json")

        mission = Mission(
            project_id=project_id,
            mission_id=draft.mission_id,
            title=draft.title or f"Mission {draft.mission_id}",
            objective=objective,
            success_criteria=success_criteria,
            context=protocol_data,
            tags=draft.tags or [],
            status=mapped_status,
            execution_metadata={
                "quality_gates": quality_gates,
                "completion_percentage": snapshot.completion_percentage,
            },
        )
        db.add(mission)
        self._sync_evidence_links(db, draft)
        db.commit()
        db.refresh(mission)
        self._trigger_quality_automation(mission.id)
        mission_id_str = str(mission.id)
        self.cache_manager.invalidate_quality_gates(mission_id_str)
        self.cache_manager.invalidate_mission_validation(mission_id_str)
        return mission

    def create_mission(self, db: Session, payload: MissionCreate) -> Mission:
        """Create a mission from a MissionCreate payload.

        Supports both explicit-field payloads (from API) and protocol draft payloads.
        """
        if not payload.project_id:
            raise MissionProtocolServiceError("project_id is required to create a mission")

        # If payload has mission_data (protocol draft), use the draft path
        mission_data = getattr(payload, "mission_data", None)
        if mission_data is not None:
            return self.create_mission_from_draft(
                db,
                project_id=payload.project_id,
                draft=mission_data,
                requested_status=payload.status,
            )

        # Otherwise use explicit fields from the payload
        report = None
        snapshot = None
        status = payload.status or "draft"

        mission = Mission(
            project_id=payload.project_id,
            mission_id=payload.mission_id,
            title=payload.title,
            objective=payload.objective,
            success_criteria=payload.success_criteria,
            context=payload.context or {},
            deliverables=payload.deliverables or [],
            research_phases=payload.research_phases or {},
            tags=payload.tags or [],
            mission_metadata=payload.metadata or {},
            research_depth=payload.research_depth,
            status=status,
            created_by=payload.created_by,
        )
        db.add(mission)
        db.commit()
        db.refresh(mission)
        self._trigger_quality_automation(mission.id)
        mission_id_str = str(mission.id)
        self.cache_manager.invalidate_quality_gates(mission_id_str)
        self.cache_manager.invalidate_mission_validation(mission_id_str)
        return mission

    def update_mission(self, db: Session, mission_id: UUID, payload: MissionUpdate) -> Mission:
        mission = self.get_mission(db, mission_id)

        # If payload has mission_data (protocol draft), use draft path
        mission_data = getattr(payload, "mission_data", None)
        if mission_data is not None:
            draft = self._ensure_draft(mission_data)
        elif mission.context and isinstance(mission.context, dict) and "mission_id" in mission.context:
            # Reconstruct draft from stored context (protocol data)
            draft = self._ensure_draft(mission.context)
        else:
            # No draft available - apply simple field updates
            if payload.title is not None:
                mission.title = payload.title
            if payload.objective is not None:
                mission.objective = payload.objective
            if payload.success_criteria is not None:
                mission.success_criteria = payload.success_criteria
            if payload.status is not None:
                mission.status = payload.status
            if payload.tags is not None:
                mission.tags = payload.tags
            db.commit()
            db.refresh(mission)
            return mission

        report = self.quality_gate_service.evaluate(draft, db=db, mission_uuid=mission.id)
        snapshot = evaluate_progress(draft)

        # Update Mission fields from draft
        mission.context = draft.model_dump(mode="json")
        quality_gates = self._merged_quality_gates(snapshot, getattr(payload, "quality_gates", None))
        mission.execution_metadata = {
            **(mission.execution_metadata or {}),
            "quality_gates": quality_gates,
            "completion_percentage": snapshot.completion_percentage,
        }
        mission.status = _map_protocol_status(
            self._determine_status(snapshot, payload.status or mission.status, report)
        )

        self._sync_evidence_links(db, draft)
        db.commit()
        db.refresh(mission)
        self._trigger_quality_automation(mission.id)
        mission_id_str = str(mission.id)
        self.cache_manager.invalidate_quality_gates(mission_id_str)
        self.cache_manager.invalidate_mission_validation(mission_id_str)
        return mission

    def delete_mission(self, db: Session, mission_id: UUID) -> None:
        mission = self.get_mission(db, mission_id)
        db.delete(mission)
        db.commit()
        mission_id_str = str(mission_id)
        self.cache_manager.invalidate_quality_gates(mission_id_str)
        self.cache_manager.invalidate_mission_validation(mission_id_str)

    # ------------------------------------------------------------------
    # YAML helpers
    # ------------------------------------------------------------------
    def import_mission_yaml(
        self,
        db: Session,
        *,
        project_id: UUID,
        yaml_text: str,
        promote_to_complete: bool = False,
    ) -> Mission:
        payload = load_mission_yaml(yaml_text, promote=promote_to_complete)
        draft = MissionProtocolDraft.model_validate(payload.model_dump())
        return self.create_mission_from_draft(
            db,
            project_id=project_id,
            draft=draft,
            requested_status=draft.status,
        )

    def export_mission_yaml(self, db: Session, mission_id: UUID) -> str:
        mission = self.get_mission(db, mission_id)
        # Use stored protocol data from context if available
        protocol_data = mission.context if isinstance(mission.context, dict) and "mission_id" in mission.context else mission.to_mission_protocol()
        return dump_mission_yaml(protocol_data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_draft(self, payload: MissionProtocolDraft | Dict[str, Any]) -> MissionProtocolDraft:
        if isinstance(payload, MissionProtocolDraft):
            return payload
        if isinstance(payload, dict):
            cache_key = self.cache_manager.mission_validation_key(payload)

            def _loader() -> MissionProtocolDraft:
                return MissionProtocolDraft.model_validate(payload)

            draft, _ = self.cache_manager.cached_value("mission_validation", cache_key, _loader)
            return draft
        raise MissionProtocolServiceError("Mission payload must be a MissionProtocolDraft or dict")

    def _merged_quality_gates(
        self,
        snapshot: MissionProgressSnapshot,
        overrides: Optional[Dict[str, Dict[str, Any]]],
    ) -> Dict[str, Dict[str, Any]]:
        merged = deepcopy(snapshot.quality_gates)
        if overrides:
            for key, value in overrides.items():
                merged[key] = value
        return merged

    def _determine_status(
        self,
        snapshot: MissionProgressSnapshot,
        requested_status: Optional[str],
        report: QualityGateReport,
    ) -> str:
        status = derive_status(snapshot, requested_status)
        if report.all_passed():
            return status

        failing = ", ".join(report.failing_gates()) or "quality gates"
        normalized_request = (requested_status or "").strip().lower()

        if normalized_request in {"complete", "review", "completed"}:
            raise MissionProtocolServiceError(
                f"Cannot transition mission to {normalized_request}: failing gates ({failing})."
            )

        if status in ("complete", "completed"):
            return "review"
        return status

    def _sync_evidence_links(self, db: Session, draft: MissionProtocolDraft) -> None:
        if not draft.evidence:
            return
        evidence_payloads = [item.model_dump() for item in draft.evidence]
        self.evidence_service.sync_from_evidence(db, evidence_payloads)

    def _trigger_quality_automation(self, mission_id: UUID) -> None:
        if self.quality_runner:
            self.quality_runner.schedule(mission_id, performed_by="mission_protocol_service")
