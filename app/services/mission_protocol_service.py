"""Mission Protocol service APIs for CRUD, YAML import/export, and progress tracking."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.mission import Mission
from app.models.mission_protocol import MissionProtocolDraft
from app.schemas.mission import MissionCreate, MissionUpdate
from app.services.cache_manager import get_cache_manager
from app.services.evidence_linking import EvidenceLinkingService
from app.services.mission_progress import (
    MissionProgressSnapshot,
    derive_status,
    evaluate_progress,
)
from app.services.mission_service import MissionService
from app.services.quality_checks import QualityAutomationRunner
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
        mission_service: MissionService | None = None,
        quality_gate_service: QualityGateService | None = None,
        quality_runner: QualityAutomationRunner | None = None,
    ) -> None:
        self.evidence_service = evidence_service or EvidenceLinkingService()
        self.mission_service = mission_service or MissionService()
        self.quality_gate_service = quality_gate_service or QualityGateService()
        self.quality_runner = quality_runner or QualityAutomationRunner(
            async_enabled=False
        )
        self.cache_manager = get_cache_manager()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def list_missions(
        self, db: Session, *, project_id: UUID | None = None
    ) -> list[Mission]:
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
        """Create a canonical Mission payload through the canonical service."""
        mission = self.mission_service.create_mission(db, payload)
        self._after_write(mission.id)
        return mission

    def create_mission_from_draft(
        self,
        db: Session,
        *,
        project_id: UUID,
        draft: MissionProtocolDraft | dict[str, Any],
        requested_status: str | None = None,
    ) -> Mission:
        """Validate a legacy Mission Protocol draft and map it to canonical fields.

        The complete draft remains round-trippable in ``Mission.context`` while
        identity, objective, criteria, lifecycle, and quality metrics use the
        current Mission columns. Removed ``mission_data``/``quality_gates``/
        ``completion_percentage`` ORM attributes are intentionally not revived.
        """
        protocol = self._ensure_draft(draft)
        report = self.quality_gate_service.evaluate(protocol, db=db)
        snapshot = evaluate_progress(protocol)
        protocol_status = self._determine_status(
            snapshot,
            self._protocol_status(requested_status or protocol.status),
            report,
        )
        mission = self.mission_service.create_mission(
            db,
            self._mission_create_payload(
                project_id=project_id,
                draft=protocol,
                status=self._canonical_status(protocol_status),
            ),
        )
        mission.execution_metadata = self._quality_metadata(
            mission.execution_metadata,
            snapshot,
        )
        self._sync_evidence_links(db, protocol)
        db.commit()
        db.refresh(mission)
        self._after_write(mission.id)
        return mission

    def update_mission(
        self, db: Session, mission_id: UUID, payload: MissionUpdate
    ) -> Mission:
        mission = self.get_mission(db, mission_id)
        source_payload = payload.context if payload.context is not None else mission.context
        draft = self._ensure_draft(source_payload)
        report = self.quality_gate_service.evaluate(
            draft, db=db, mission_uuid=mission.id
        )
        snapshot = evaluate_progress(draft)
        protocol_status = self._determine_status(
            snapshot,
            self._protocol_status(payload.status or mission.status),
            report,
        )

        self._sync_evidence_links(db, draft)
        updated = self.mission_service.update_mission(
            db,
            mission.id,
            MissionUpdate(
                title=self._title(draft),
                objective=self._objective(draft),
                success_criteria=self._success_criteria(draft),
                context=draft.model_dump(mode="json"),
                tags=draft.tags,
                status=self._canonical_status(protocol_status),
                execution_metadata=self._quality_metadata(
                    mission.execution_metadata,
                    snapshot,
                ),
            ),
        )
        self._after_write(updated.id)
        return updated

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
        draft = self._ensure_draft(mission.context)
        return dump_mission_yaml(draft.model_dump(mode="json"))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_draft(
        self, payload: MissionProtocolDraft | dict[str, Any]
    ) -> MissionProtocolDraft:
        if isinstance(payload, MissionProtocolDraft):
            return payload
        if isinstance(payload, dict):
            cache_key = self.cache_manager.mission_validation_key(payload)

            def _loader() -> MissionProtocolDraft:
                return MissionProtocolDraft.model_validate(payload)

            draft, _ = self.cache_manager.cached_value(
                "mission_validation", cache_key, _loader
            )
            return draft
        raise MissionProtocolServiceError(
            "Mission payload must be a MissionProtocolDraft or dict"
        )

    def _merged_quality_gates(
        self,
        snapshot: MissionProgressSnapshot,
        overrides: dict[str, dict[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        merged = deepcopy(snapshot.quality_gates)
        if overrides:
            for key, value in overrides.items():
                merged[key] = value
        return merged

    def _mission_create_payload(
        self,
        *,
        project_id: UUID,
        draft: MissionProtocolDraft,
        status: str,
    ) -> MissionCreate:
        return MissionCreate(
            project_id=project_id,
            mission_id=draft.mission_id,
            title=self._title(draft),
            objective=self._objective(draft),
            success_criteria=self._success_criteria(draft),
            context=draft.model_dump(mode="json"),
            tags=draft.tags,
            metadata={
                "mission_protocol_version": draft.version,
                "mission_protocol_status": draft.status,
            },
            status=status,
        )

    @staticmethod
    def _title(draft: MissionProtocolDraft) -> str:
        title = (draft.title or f"Mission {draft.mission_id}").strip()
        if len(title) < 3:
            title = f"Mission {title}"
        return title[:255]

    @classmethod
    def _objective(cls, draft: MissionProtocolDraft) -> str:
        statement = draft.research_statement
        objective = (
            statement.objective
            if statement is not None
            else draft.summary or cls._title(draft)
        ).strip()
        if len(objective) < 10:
            objective = f"{objective} for {cls._title(draft)}"
        return objective

    @staticmethod
    def _success_criteria(draft: MissionProtocolDraft) -> list[str]:
        statement = draft.research_statement
        if statement is not None and statement.success_metrics:
            return list(statement.success_metrics)
        questions = [question.question.strip() for question in draft.key_questions]
        if questions:
            return questions
        return ["Complete the Mission Protocol quality gates."]

    def _quality_metadata(
        self,
        existing: dict[str, Any] | None,
        snapshot: MissionProgressSnapshot,
    ) -> dict[str, Any]:
        metadata = dict(existing or {})
        metadata.update(
            {
                "completion_percentage": snapshot.completion_percentage,
                "quality_gates": self._merged_quality_gates(snapshot, None),
            }
        )
        return metadata

    @staticmethod
    def _protocol_status(status: str) -> str:
        return {
            "completed": "complete",
            "validation_failed": "review",
        }.get(status, status)

    @staticmethod
    def _canonical_status(status: str) -> str:
        return {
            "complete": "completed",
            "review": "in_progress",
        }.get(status, status)

    def _determine_status(
        self,
        snapshot: MissionProgressSnapshot,
        requested_status: str | None,
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

    def _trigger_quality_automation(self, mission_id: UUID) -> None:
        if self.quality_runner:
            self.quality_runner.schedule(
                mission_id, performed_by="mission_protocol_service"
            )

    def _after_write(self, mission_id: UUID) -> None:
        self._trigger_quality_automation(mission_id)
        mission_id_str = str(mission_id)
        self.cache_manager.invalidate_quality_gates(mission_id_str)
        self.cache_manager.invalidate_mission_validation(mission_id_str)
