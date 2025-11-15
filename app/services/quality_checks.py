"""Quality automation orchestration and persistence helpers."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Sequence
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.mission import Mission
from app.models.mission_protocol import MissionProtocolDraft
from app.models.quality import QualityCheck
from app.services.bias_detection import BiasDetector
from app.services.cache_manager import get_cache_manager
from app.services.methodology_rigor import MethodologyRigorChecker
from app.services.quality_automation_models import QualityAutomationCheckResult
from app.services.synthesis_analyzer import SynthesisAnalyzer
from app.services.traceability_validator import TraceabilityValidator

logger = logging.getLogger(__name__)


class QualityCheckRepository:
    """Persistence helpers for quality audit trail entries."""

    def create_records(
        self,
        db: Session,
        mission: Mission,
        results: Sequence[QualityAutomationCheckResult],
        *,
        performed_by: str,
    ) -> List[QualityCheck]:
        records: List[QualityCheck] = []
        for result in results:
            record = QualityCheck(
                entity_type="mission",
                entity_id=mission.id,
                check_type=result.check_type,
                status=result.status,
                details=result.to_details(),
                recommendations=result.recommendations or None,
                performed_by=performed_by,
                performed_at=result.evaluated_at.replace(tzinfo=None),
            )
            db.add(record)
            records.append(record)
        db.flush()
        return records

    def history_for_mission(
        self,
        db: Session,
        mission_id: UUID,
        *,
        limit: int = 200,
    ) -> List[QualityCheck]:
        return (
            db.query(QualityCheck)
            .filter(QualityCheck.entity_type == "mission", QualityCheck.entity_id == mission_id)
            .order_by(QualityCheck.performed_at.desc())
            .limit(limit)
            .all()
        )

    def latest_for_mission(self, db: Session, mission_id: UUID) -> List[QualityCheck]:
        subquery = (
            db.query(
                QualityCheck.check_type,
                func.max(QualityCheck.performed_at).label("max_performed_at"),
            )
            .filter(QualityCheck.entity_type == "mission", QualityCheck.entity_id == mission_id)
            .group_by(QualityCheck.check_type)
            .subquery()
        )
        return (
            db.query(QualityCheck)
            .join(
                subquery,
                (QualityCheck.check_type == subquery.c.check_type)
                & (QualityCheck.performed_at == subquery.c.max_performed_at),
            )
            .filter(QualityCheck.entity_type == "mission", QualityCheck.entity_id == mission_id)
            .all()
        )


class _QualityAutomationTelemetry:
    """Append automation events to telemetry/events/quality-automation.jsonl."""

    def __init__(self, path: Path | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.path = path or (repo_root / "telemetry" / "events" / "quality-automation.jsonl")

    def __call__(self, record: QualityCheck, result: QualityAutomationCheckResult) -> None:  # pragma: no cover - simple IO
        payload = {
            "ts": result.evaluated_at.isoformat().replace("+00:00", "Z"),
            "entity_type": record.entity_type,
            "entity_id": str(record.entity_id),
            "check_type": record.check_type,
            "status": record.status,
            "summary": result.summary,
            "metrics": result.metrics,
            "recommendations": result.recommendations,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class QualityAutomationService:
    """Coordinate detectors and persist the resulting audit trail."""

    def __init__(
        self,
        *,
        bias_detector: BiasDetector | None = None,
        traceability_validator: TraceabilityValidator | None = None,
        methodology_checker: MethodologyRigorChecker | None = None,
        synthesis_analyzer: SynthesisAnalyzer | None = None,
        repository: QualityCheckRepository | None = None,
        telemetry_sink: _QualityAutomationTelemetry | None = None,
    ) -> None:
        self.bias_detector = bias_detector or BiasDetector()
        self.traceability_validator = traceability_validator or TraceabilityValidator()
        self.methodology_checker = methodology_checker or MethodologyRigorChecker()
        self.synthesis_analyzer = synthesis_analyzer or SynthesisAnalyzer()
        self.repository = repository or QualityCheckRepository()
        self.telemetry_sink = telemetry_sink or _QualityAutomationTelemetry()
        self.cache_manager = get_cache_manager()

    def evaluate(self, db: Session, *, mission: Mission) -> List[QualityAutomationCheckResult]:
        payload = MissionProtocolDraft.model_validate(mission.mission_data)
        if not payload.project_id and mission.project_id:
            payload.project_id = str(mission.project_id)

        documents: List[Document] = (
            list(db.query(Document).filter(Document.project_id == mission.project_id).all())
            if mission.project_id
            else []
        )

        results: List[QualityAutomationCheckResult] = [
            self.bias_detector.evaluate(payload),
            self.traceability_validator.evaluate(payload, db),
            self.methodology_checker.evaluate(mission=payload, db=db, documents=documents),
            self.synthesis_analyzer.evaluate(payload),
        ]
        return results

    def run_for_mission(
        self,
        db: Session,
        mission: Mission,
        *,
        performed_by: str = "quality_automation",
    ) -> List[QualityCheck]:
        results = self.evaluate(db, mission=mission)
        records = self.repository.create_records(db, mission, results, performed_by=performed_by)
        for record, result in zip(records, results):
            self.telemetry_sink(record, result)
        if mission.id:
            self.cache_manager.invalidate_quality_gates(str(mission.id))
        return records


class QualityAutomationRunner:
    """Background runner that executes automation checks per mission."""

    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        service: QualityAutomationService | None = None,
        async_enabled: bool = False,
    ) -> None:
        self.session_factory = session_factory
        self.service = service or QualityAutomationService()
        self.async_enabled = async_enabled
        self._executor: ThreadPoolExecutor | None = ThreadPoolExecutor(max_workers=1) if async_enabled else None

    def schedule(self, mission_id: UUID, *, performed_by: str = "quality_automation") -> None:
        if self.async_enabled and self._executor:
            self._executor.submit(self._execute, mission_id, performed_by)
        else:
            self._execute(mission_id, performed_by)

    def _execute(self, mission_id: UUID, performed_by: str) -> None:
        session = self.session_factory()
        try:
            mission = session.query(Mission).filter(Mission.id == mission_id).one_or_none()
            if not mission:
                return
            self.service.run_for_mission(session, mission, performed_by=performed_by)
            session.commit()
        except Exception:  # pragma: no cover - defensive logging
            session.rollback()
            logger.exception("Quality automation runner failed for mission %s", mission_id)
        finally:
            session.close()


__all__ = [
    "QualityAutomationRunner",
    "QualityAutomationService",
    "QualityCheckRepository",
]
