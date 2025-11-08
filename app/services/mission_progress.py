"""Mission Protocol progress and quality gate evaluation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Sequence, Tuple, Union, get_args

from app.models.mission_protocol import (
    MissionProtocolComplete,
    MissionProtocolDraft,
    QualityCheckpoint,
    QualityGateName,
    REQUIRED_COMPLETION_GATES,
)

MissionPayload = Union[MissionProtocolDraft, MissionProtocolComplete, Dict[str, Any]]


@dataclass
class MissionProgressSnapshot:
    """Represents derived progress metrics for a Mission Protocol payload."""

    completion_percentage: int
    completed_checks: List[str]
    pending_checks: List[str]
    quality_gates: Dict[str, Dict[str, Any]]

    def is_completion_ready(self) -> bool:
        """Return True when the mission satisfies completion criteria."""
        if self.pending_checks:
            return False
        return all(
            self.quality_gates.get(gate, {}).get("status") == "pass"
            for gate in REQUIRED_COMPLETION_GATES
        )


def evaluate_progress(payload: MissionPayload) -> MissionProgressSnapshot:
    """Calculate completion percentage and gate status from a payload."""
    mission = _coerce_payload(payload)
    completed, pending = _evaluate_required_fields(mission)
    percent = _calculate_percentage(len(completed), len(completed) + len(pending))
    gates = _collect_quality_gates(mission.quality_checkpoints)
    return MissionProgressSnapshot(
        completion_percentage=percent,
        completed_checks=completed,
        pending_checks=pending,
        quality_gates=gates,
    )


def derive_status(
    snapshot: MissionProgressSnapshot,
    requested_status: str | None = None,
) -> str:
    """Determine the mission status enforcing draft → complete transitions."""

    allowed = ("draft", "in_progress", "review", "complete")
    normalized = (requested_status or "draft").lower()
    if normalized not in allowed:
        normalized = "draft"

    if snapshot.is_completion_ready():
        return "complete"

    if normalized == "complete":
        return "review"
    if normalized == "review" and snapshot.completion_percentage < 60:
        return "in_progress"
    if normalized == "draft" and snapshot.completion_percentage > 0:
        return "in_progress"
    return normalized


def _coerce_payload(payload: MissionPayload) -> MissionProtocolDraft:
    if isinstance(payload, MissionProtocolDraft):
        return payload
    if isinstance(payload, MissionProtocolComplete):
        return MissionProtocolDraft.model_validate(payload.model_dump())
    if isinstance(payload, dict):
        return MissionProtocolDraft.model_validate(payload)
    raise TypeError("Unsupported mission payload type")


def _evaluate_required_fields(mission: MissionProtocolDraft) -> Tuple[List[str], List[str]]:
    checks: Sequence[Tuple[str, bool]] = (
        ("mission_id", bool(mission.mission_id)),
        ("title", bool(mission.title)),
        ("research_statement", mission.research_statement is not None),
        (
            "answered_key_question",
            any(q.status == "answered" and (q.answer or "").strip() for q in mission.key_questions),
        ),
        (
            "synthesis_key_insight",
            bool(mission.synthesis and mission.synthesis.key_insights),
        ),
        ("evidence", bool(mission.evidence)),
        ("quality_checkpoints", bool(mission.quality_checkpoints)),
    )
    completed = [name for name, ok in checks if ok]
    pending = [name for name, ok in checks if not ok]
    return completed, pending


def _calculate_percentage(completed: int, total: int) -> int:
    if total == 0:
        return 0
    return int(round((completed / total) * 100))


def _collect_quality_gates(checkpoints: Sequence[QualityCheckpoint]) -> Dict[str, Dict[str, Any]]:
    gate_names: Tuple[str, ...] = get_args(QualityGateName)  # type: ignore[arg-type]
    gates: Dict[str, Dict[str, Any]] = {
        gate: {"status": "pending", "validated": False, "notes": None,
               "validated_by": None, "validated_at": None}
        for gate in gate_names
    }

    for checkpoint in checkpoints:
        gates[checkpoint.gate] = {
            "status": checkpoint.status,
            "validated": checkpoint.status == "pass",
            "notes": checkpoint.notes,
            "validated_by": checkpoint.validated_by,
            "validated_at": _format_datetime(checkpoint.validated_at),
        }
    return gates


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    iso = value.isoformat()
    return iso if value.tzinfo else f"{iso}Z"
