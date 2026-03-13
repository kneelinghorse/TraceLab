"""Enhanced traceability validator for Mission Protocol evidence."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk
from app.models.insight import InsightSource
from app.models.mission_protocol import MissionProtocolDraft
from app.services.quality_automation_models import (
    QualityAutomationCheckResult,
    QualityIssue,
)


class TraceabilityValidator:
    """Validate that evidence maintains healthy links back to source chunks."""

    def __init__(self, *, low_relevance_threshold: float = 0.55) -> None:
        self.low_relevance_threshold = low_relevance_threshold

    def evaluate(
        self, mission: MissionProtocolDraft, db: Session
    ) -> QualityAutomationCheckResult:
        evidence = mission.evidence or []
        issues: list[QualityIssue] = []
        recommendations: list[str] = []
        metrics: dict[str, int | float] = {
            "evidence_items": len(evidence),
            "chunk_backed": 0,
            "broken_chunks": 0,
            "low_relevance": 0,
        }

        if not evidence:
            summary = "No evidence supplied; traceability checks skipped."
            issues.append(
                QualityIssue(
                    code="missing_evidence",
                    severity="high",
                    message="Mission evidence list is empty, preventing traceability verification.",
                )
            )
            recommendations.append(
                "Attach at least one chunk-backed evidence entry before completion."
            )
            return QualityAutomationCheckResult(
                check_type="traceability",
                summary=summary,
                issues=issues,
                metrics=metrics,
                recommendations=recommendations,
            )

        chunk_ids, invalid_chunks = self._normalize_chunk_ids(evidence)
        metrics["chunk_backed"] = len(chunk_ids)

        if invalid_chunks:
            issues.append(
                QualityIssue(
                    code="invalid_chunk_ids",
                    severity="medium",
                    message=f"{len(invalid_chunks)} evidence entries contain malformed chunk identifiers.",
                    metadata={"chunk_ids": invalid_chunks},
                )
            )

        missing_chunks = self._missing_chunks(db, chunk_ids)
        if missing_chunks:
            issues.append(
                QualityIssue(
                    code="missing_chunks",
                    severity="high",
                    message=f"{len(missing_chunks)} evidence entries reference chunks that do not exist.",
                    metadata={"chunk_ids": sorted(missing_chunks)},
                )
            )
            recommendations.append(
                "Re-link evidence to valid document chunks or regenerate the traceability map."
            )
        metrics["broken_chunks"] = len(missing_chunks)

        orphaned_insights = self._orphaned_insights(db, evidence)
        if orphaned_insights:
            issues.append(
                QualityIssue(
                    code="unlinked_insights",
                    severity="high",
                    message="Some insights referenced by evidence lack entries in insight_sources.",
                    metadata={"insight_ids": sorted(orphaned_insights)},
                )
            )
            recommendations.append(
                "Backfill insight_sources rows for every insight/evidence pair."
            )

        low_relevance = [
            item.evidence_id
            for item in evidence
            if item.relevance_score is not None
            and item.relevance_score < self.low_relevance_threshold
        ]
        if low_relevance:
            issues.append(
                QualityIssue(
                    code="low_relevance_sources",
                    severity="medium",
                    message=f"{len(low_relevance)} evidence entries have relevance below {self.low_relevance_threshold:.2f}.",
                    metadata={"evidence_ids": low_relevance},
                )
            )
            metrics["low_relevance"] = len(low_relevance)
            recommendations.append(
                "Review low-scoring sources and prune or replace them with higher-signal chunks."
            )

        summary = (
            "All evidence entries maintain healthy traceability."
            if not issues
            else "Traceability validator detected missing chunk references or weak evidence relevance."
        )

        return QualityAutomationCheckResult(
            check_type="traceability",
            summary=summary,
            issues=issues,
            metrics=metrics,
            recommendations=recommendations,
        )

    def _normalize_chunk_ids(self, evidence: Sequence) -> tuple[list[str], list[str]]:
        ids: list[str] = []
        invalid: list[str] = []
        for item in evidence:
            chunk_id = (item.chunk_id or "").strip()
            if chunk_id:
                try:
                    UUID(chunk_id)
                except (TypeError, ValueError):
                    invalid.append(chunk_id)
                    continue
                ids.append(chunk_id)
        return ids, invalid

    def _missing_chunks(self, db: Session, chunk_ids: Sequence[str]) -> set[str]:
        if not chunk_ids:
            return set()
        rows = db.query(DocumentChunk.id).filter(DocumentChunk.id.in_(chunk_ids)).all()
        existing = {str(row[0]) for row in rows}
        return set(chunk_ids) - existing

    def _orphaned_insights(self, db: Session, evidence: Sequence) -> set[str]:
        insight_ids: set[str] = set()
        for item in evidence:
            if item.insight_id:
                insight_ids.add(str(item.insight_id))
        if not insight_ids:
            return set()

        valid_ids: set[str] = set()
        converted: list[UUID] = []
        for identifier in insight_ids:
            try:
                converted.append(UUID(identifier))
            except (TypeError, ValueError):
                continue

        if converted:
            rows = (
                db.query(InsightSource.insight_id)
                .filter(InsightSource.insight_id.in_(converted))
                .distinct()
                .all()
            )
            valid_ids = {str(row[0]) for row in rows}

        return insight_ids - valid_ids


__all__ = ["TraceabilityValidator"]
