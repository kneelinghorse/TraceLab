"""Quality gate orchestration and telemetry logging."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.insight import InsightSource
from app.models.mission_protocol import (
    MissionProtocolComplete,
    MissionProtocolDraft,
    QualityCheckpoint,
)
from app.services import quality_gates
from app.services.quality_gates import QualityGateResult

TelemetrySink = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class QualityGateReport:
    """Aggregate results for all quality gates."""

    protocol_mission_id: str
    mission_uuid: UUID | None
    evaluated_at: datetime
    results: MutableMapping[str, QualityGateResult] = field(default_factory=dict)

    def all_passed(self) -> bool:
        return all(result.passed for result in self.results.values())

    def failing_gates(self) -> list[str]:
        return [name for name, result in self.results.items() if not result.passed]

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {name: result.to_dict() for name, result in self.results.items()}

    def to_quality_checkpoints(self) -> list[QualityCheckpoint]:
        checkpoints: list[QualityCheckpoint] = []
        for result in self.results.values():
            checkpoint = QualityCheckpoint(
                gate=result.gate,
                status="pass" if result.passed else "fail",
                notes=result.details,
                validated_by="quality_gate_service",
                validated_at=result.evaluated_at,
            )
            checkpoints.append(checkpoint)
        return checkpoints


class _FileTelemetrySink:
    """Append telemetry events to telemetry/events/quality-gates.jsonl."""

    def __init__(self, path: Path | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.path = path or (repo_root / "telemetry" / "events" / "quality-gates.jsonl")

    def __call__(self, payload: dict[str, Any]) -> None:  # pragma: no cover - simple IO
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class QualityGateService:
    """Evaluate Mission Protocol payloads against blocking quality gates."""

    def __init__(
        self,
        *,
        evidence_threshold: int = 1,
        telemetry_sink: TelemetrySink | None = None,
    ) -> None:
        self.evidence_threshold = max(1, evidence_threshold)
        self.telemetry_sink = telemetry_sink or _FileTelemetrySink()

    def evaluate(
        self,
        payload: MissionProtocolDraft | MissionProtocolComplete | dict[str, Any],
        *,
        db: Session | None = None,
        mission_uuid: UUID | None = None,
    ) -> QualityGateReport:
        mission = self._coerce_payload(payload)
        traceability_counts = self._load_traceability_counts(db, mission)

        results: dict[str, QualityGateResult] = {}
        results["research_statement"] = (
            quality_gates.check_research_statement_completeness(mission)
        )
        results["evidence_links"] = quality_gates.check_evidence_links(
            mission,
            min_sources_per_insight=self.evidence_threshold,
        )
        results["contradictions_resolved"] = (
            quality_gates.check_contradictions_resolved(mission)
        )
        results["synthesis_quality"] = quality_gates.check_synthesis_quality(mission)
        results["traceability"] = quality_gates.check_source_traceability(
            mission,
            expected_links=traceability_counts,
        )

        report = QualityGateReport(
            protocol_mission_id=mission.mission_id,
            mission_uuid=mission_uuid,
            evaluated_at=datetime.now(UTC),
            results=results,
        )

        mission.quality_checkpoints = report.to_quality_checkpoints()
        self._emit_telemetry(report)
        return report

    def _emit_telemetry(self, report: QualityGateReport) -> None:
        for name, result in report.results.items():
            payload = {
                "ts": result.evaluated_at.isoformat().replace("+00:00", "Z"),
                "mission_id": report.protocol_mission_id,
                "mission_uuid": str(report.mission_uuid)
                if report.mission_uuid
                else None,
                "gate": name,
                "status": result.status,
                "details": result.details,
                "metadata": dict(result.metadata) if result.metadata else None,
            }
            self.telemetry_sink(payload)

    @staticmethod
    def _coerce_payload(payload: Any) -> MissionProtocolDraft:
        if isinstance(payload, MissionProtocolDraft):
            return payload
        if isinstance(payload, MissionProtocolComplete):
            return MissionProtocolDraft.model_validate(payload.model_dump())
        if isinstance(payload, dict):
            return MissionProtocolDraft.model_validate(payload)
        raise TypeError("Unsupported mission payload type")

    @staticmethod
    def _load_traceability_counts(
        db: Session | None,
        mission: MissionProtocolDraft,
    ) -> Mapping[str, int] | None:
        if db is None:
            return None

        insight_ids: list[UUID] = []
        evidence = mission.evidence or []
        for item in evidence:
            if not item.insight_id:
                continue
            try:
                insight_ids.append(UUID(str(item.insight_id)))
            except (TypeError, ValueError):
                continue

        if not insight_ids:
            return None

        rows = (
            db.query(InsightSource.insight_id, func.count(InsightSource.chunk_id))
            .filter(InsightSource.insight_id.in_(insight_ids))
            .group_by(InsightSource.insight_id)
            .all()
        )
        counts: dict[str, int] = {str(row[0]): int(row[1]) for row in rows}
        for insight_id in {str(value) for value in insight_ids}:
            counts.setdefault(insight_id, 0)
        return counts
