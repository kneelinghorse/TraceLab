"""Mission Protocol service APIs for CRUD, YAML import/export, and progress tracking."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.mission import Mission
from app.models.mission_protocol import MissionProtocolDraft
from app.schemas.mission import MissionCreate, MissionUpdate
from app.services.evidence_linking import EvidenceLinkingService
from app.services.mission_progress import MissionProgressSnapshot, derive_status, evaluate_progress
from app.services.quality_gate_service import QualityGateReport, QualityGateService
from app.services.yaml_handler import dump_mission_yaml, load_mission_yaml


class MissionProtocolServiceError(RuntimeError):
    """Raised when mission protocol operations fail."""


class MissionNotFoundError(MissionProtocolServiceError):
    """Raised when a mission could not be located."""


class MissionProtocolService:
    """Encapsulates Mission Protocol CRUD + YAML workflows."""

    def __init__(
        self,
        *,
        evidence_service: EvidenceLinkingService | None = None,
        quality_gate_service: QualityGateService | None = None,
    ) -> None:
        self.evidence_service = evidence_service or EvidenceLinkingService()
        self.quality_gate_service = quality_gate_service or QualityGateService()

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

    def create_mission(self, db: Session, payload: MissionCreate) -> Mission:
        if not payload.project_id:
            raise MissionProtocolServiceError("project_id is required to create a mission")

        draft = self._ensure_draft(payload.mission_data)
        report = self.quality_gate_service.evaluate(draft, db=db)
        snapshot = evaluate_progress(draft)
        mission = Mission(
            project_id=payload.project_id,
            mission_data=draft.model_dump(mode="json"),
            quality_gates=self._merged_quality_gates(snapshot, payload.quality_gates),
            status=self._determine_status(snapshot, payload.status, report),
            completion_percentage=snapshot.completion_percentage,
        )
        db.add(mission)
        self._sync_evidence_links(db, draft)
        db.commit()
        db.refresh(mission)
        return mission

    def update_mission(self, db: Session, mission_id: UUID, payload: MissionUpdate) -> Mission:
        mission = self.get_mission(db, mission_id)
        source_payload: MissionProtocolDraft | Dict[str, Any]
        source_payload = payload.mission_data or mission.mission_data
        draft = self._ensure_draft(source_payload)
        report = self.quality_gate_service.evaluate(draft, db=db, mission_uuid=mission.id)
        snapshot = evaluate_progress(draft)

        mission.mission_data = draft.model_dump(mode="json")
        mission.quality_gates = self._merged_quality_gates(snapshot, payload.quality_gates)
        mission.completion_percentage = snapshot.completion_percentage
        mission.status = self._determine_status(snapshot, payload.status or mission.status, report)

        self._sync_evidence_links(db, draft)
        db.commit()
        db.refresh(mission)
        return mission

    def delete_mission(self, db: Session, mission_id: UUID) -> None:
        mission = self.get_mission(db, mission_id)
        db.delete(mission)
        db.commit()

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
        mission_create = MissionCreate(project_id=project_id, mission_data=draft)
        return self.create_mission(db, mission_create)

    def export_mission_yaml(self, db: Session, mission_id: UUID) -> str:
        mission = self.get_mission(db, mission_id)
        return dump_mission_yaml(mission.mission_data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_draft(self, payload: MissionProtocolDraft | Dict[str, Any]) -> MissionProtocolDraft:
        if isinstance(payload, MissionProtocolDraft):
            return payload
        if isinstance(payload, dict):
            return MissionProtocolDraft.model_validate(payload)
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

        if normalized_request in {"complete", "review"}:
            raise MissionProtocolServiceError(
                f"Cannot transition mission to {normalized_request}: failing gates ({failing})."
            )

        if status == "complete":
            return "review"
        return status

    def _sync_evidence_links(self, db: Session, draft: MissionProtocolDraft) -> None:
        if not draft.evidence:
            return
        evidence_payloads = [item.model_dump() for item in draft.evidence]
        self.evidence_service.sync_from_evidence(db, evidence_payloads)
