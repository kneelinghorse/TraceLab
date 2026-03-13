"""Deterministic quality gate validators for Mission Protocol payloads."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.models.mission_protocol import (
    MissionProtocolComplete,
    MissionProtocolDraft,
    QualityGateName,
)

MissionPayload = MissionProtocolDraft | MissionProtocolComplete | dict[str, Any]


@dataclass(slots=True)
class QualityGateResult:
    """Represents the outcome of a single quality gate evaluation."""

    gate: QualityGateName
    status: str
    details: str
    blocking: bool = True
    metadata: MutableMapping[str, Any] = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "gate": self.gate,
            "status": self.status,
            "details": self.details,
            "blocking": self.blocking,
            "evaluated_at": self.evaluated_at.isoformat().replace("+00:00", "Z"),
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


def _coerce_mission(payload: MissionPayload) -> MissionProtocolDraft:
    if isinstance(payload, MissionProtocolDraft):
        return payload
    if isinstance(payload, MissionProtocolComplete):
        return MissionProtocolDraft.model_validate(payload.model_dump())
    if isinstance(payload, dict):
        return MissionProtocolDraft.model_validate(payload)
    raise TypeError("Unsupported mission payload type")


def check_research_statement_completeness(payload: MissionPayload) -> QualityGateResult:
    """Ensure topic, scope, and hypothesis (objective) are supplied."""

    mission = _coerce_mission(payload)
    missing: list[str] = []
    statement = mission.research_statement
    if not statement:
        missing.extend(["topic", "scope", "hypothesis"])
    else:
        if not (statement.topic or "").strip():
            missing.append("topic")
        if not (statement.scope or "").strip():
            missing.append("scope")
        if not (statement.objective or "").strip():
            missing.append("hypothesis")

    if missing:
        return QualityGateResult(
            gate="research_statement",
            status="fail",
            details="Research statement missing required sections.",
            metadata={"missing_fields": sorted(set(missing))},
        )
    return QualityGateResult(
        gate="research_statement",
        status="pass",
        details="Research statement includes topic, scope, and hypothesis.",
    )


def check_evidence_links(
    payload: MissionPayload,
    *,
    min_sources_per_insight: int = 1,
) -> QualityGateResult:
    """Validate that each insight is supported by chunk-linked evidence."""

    mission = _coerce_mission(payload)
    insights = (mission.synthesis.key_insights if mission.synthesis else []) or []
    evidence = mission.evidence or []

    if not insights:
        return QualityGateResult(
            gate="evidence_links",
            status="fail",
            details="Mission lacks key insights for evidence coverage checks.",
        )
    if not evidence:
        return QualityGateResult(
            gate="evidence_links",
            status="fail",
            details="Mission provides no evidence entries.",
        )

    chunk_linked = [item for item in evidence if (item.chunk_id or "").strip()]
    if not chunk_linked:
        return QualityGateResult(
            gate="evidence_links",
            status="fail",
            details="Evidence entries are missing chunk_id traceability.",
        )

    assigned: dict[str, set[str]] = {}
    for item in chunk_linked:
        key = (item.insight_id or "unassigned").strip()
        assigned.setdefault(key, set()).add(item.chunk_id.strip())

    metadata: dict[str, Any] = {
        "insight_count": len(insights),
        "evidence_items": len(evidence),
        "chunk_backed": len(chunk_linked),
        "threshold": min_sources_per_insight,
    }

    if len(assigned) == 1 and "unassigned" in assigned:
        avg_sources = len(chunk_linked) / max(len(insights), 1)
        metadata["average_sources_per_insight"] = avg_sources
        if avg_sources < min_sources_per_insight:
            return QualityGateResult(
                gate="evidence_links",
                status="fail",
                details="Average evidence coverage per insight is below threshold.",
                metadata=metadata,
            )
        return QualityGateResult(
            gate="evidence_links",
            status="pass",
            details="Evidence coverage meets the minimum source threshold per insight.",
            metadata=metadata,
        )

    deficient = [
        insight_id
        for insight_id, chunk_ids in assigned.items()
        if insight_id != "unassigned" and len(chunk_ids) < min_sources_per_insight
    ]
    if deficient:
        metadata["insights_below_threshold"] = deficient
        return QualityGateResult(
            gate="evidence_links",
            status="fail",
            details="Some insights lack the required number of supporting source chunks.",
            metadata=metadata,
        )

    return QualityGateResult(
        gate="evidence_links",
        status="pass",
        details="All insight-linked evidence meets source coverage requirements.",
        metadata=metadata,
    )


def check_contradictions_resolved(payload: MissionPayload) -> QualityGateResult:
    """Ensure contradictory_information entries have resolution notes."""

    mission = _coerce_mission(payload)
    synthesis = mission.synthesis
    contradictions = (synthesis.contradictory_information if synthesis else []) or []
    resolutions = (synthesis.contradiction_resolutions if synthesis else []) or []

    if not contradictions:
        return QualityGateResult(
            gate="contradictions_resolved",
            status="pass",
            details="No contradictory information documented in synthesis.",
        )

    resolved_count = len([item for item in resolutions if (item or "").strip()])
    missing = max(len(contradictions) - resolved_count, 0)
    if missing > 0:
        return QualityGateResult(
            gate="contradictions_resolved",
            status="fail",
            details="Contradictory findings lack documented resolution notes.",
            metadata={
                "contradictions": len(contradictions),
                "resolved": resolved_count,
            },
        )

    return QualityGateResult(
        gate="contradictions_resolved",
        status="pass",
        details="All contradictory findings include resolution notes.",
        metadata={
            "contradictions": len(contradictions),
            "resolved": resolved_count,
        },
    )


def check_synthesis_quality(payload: MissionPayload) -> QualityGateResult:
    """Validate synthesis depth via insights, recommendations, and next steps."""

    mission = _coerce_mission(payload)
    synthesis = mission.synthesis
    if not synthesis:
        return QualityGateResult(
            gate="synthesis_quality",
            status="fail",
            details="Mission synthesis section is missing.",
        )

    insights = [item.strip() for item in synthesis.key_insights if (item or "").strip()]
    if not insights:
        return QualityGateResult(
            gate="synthesis_quality",
            status="fail",
            details="Synthesis lacks key insights.",
        )

    short_insights = [insight for insight in insights if len(insight) < 40]
    if short_insights:
        return QualityGateResult(
            gate="synthesis_quality",
            status="fail",
            details="Key insights must include actionable detail (>= 40 characters).",
            metadata={"short_insights": short_insights[:3]},
        )

    if not synthesis.recommendations:
        return QualityGateResult(
            gate="synthesis_quality",
            status="fail",
            details="Add at least one recommendation tied to the insights.",
        )
    if not synthesis.next_steps:
        return QualityGateResult(
            gate="synthesis_quality",
            status="fail",
            details="Add next steps to operationalise the synthesis.",
        )

    return QualityGateResult(
        gate="synthesis_quality",
        status="pass",
        details="Synthesis includes detailed insights, recommendations, and next steps.",
        metadata={
            "insights": len(insights),
            "recommendations": len(synthesis.recommendations),
            "next_steps": len(synthesis.next_steps),
        },
    )


def check_source_traceability(
    payload: MissionPayload,
    *,
    expected_links: Mapping[str, int] | None = None,
) -> QualityGateResult:
    """Verify that evidence entries are traceable to source chunks."""

    mission = _coerce_mission(payload)
    evidence = mission.evidence or []
    if not evidence:
        return QualityGateResult(
            gate="traceability",
            status="fail",
            details="Mission includes no evidence to verify traceability.",
        )

    missing_chunk = [
        item.evidence_id for item in evidence if not (item.chunk_id or "").strip()
    ]
    if missing_chunk:
        return QualityGateResult(
            gate="traceability",
            status="fail",
            details="Some evidence entries are missing chunk identifiers.",
            metadata={"evidence_ids": missing_chunk},
        )

    if expected_links:
        insufficient = [
            insight_id for insight_id, count in expected_links.items() if count <= 0
        ]
        if insufficient:
            return QualityGateResult(
                gate="traceability",
                status="fail",
                details="Insight-source links missing in insight_sources table.",
                metadata={"missing_links": insufficient},
            )

    return QualityGateResult(
        gate="traceability",
        status="pass",
        details="Evidence entries contain chunk references for traceability.",
        metadata={"evidence_items": len(evidence)},
    )


def default_validators() -> Sequence:
    """Return validators in execution order."""

    return (
        check_research_statement_completeness,
        check_evidence_links,
        check_contradictions_resolved,
        check_synthesis_quality,
        check_source_traceability,
    )
