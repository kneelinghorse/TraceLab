"""Methodology rigor checker leveraging project documents."""
from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.mission_protocol import MethodologyDetails, MissionProtocolDraft
from app.services.quality_automation_models import (
    QualityAutomationCheckResult,
    QualityIssue,
)


class MethodologyRigorChecker:
    """Validate research rigor via participant counts and metadata coverage."""

    RULES: Dict[str, Dict[str, object]] = {
        "qualitative": {
            "min_participants": 5,
            "required_metadata": ("participant_count", "collection_date", "source_type"),
            "min_validated_ratio": 0.4,
            "required_validation_steps": ("transcription_validation", "theme_validation"),
        },
        "quantitative": {
            "min_participants": 30,
            "required_metadata": ("participant_count", "collection_date", "source_type"),
            "min_validated_ratio": 0.6,
            "required_validation_steps": ("data_quality_check", "statistical_validation"),
        },
        "mixed": {
            "min_participants": 15,
            "required_metadata": ("participant_count", "collection_date"),
            "min_validated_ratio": 0.5,
            "required_validation_steps": ("triangulation_review",),
        },
    }

    def evaluate(
        self,
        *,
        mission: MissionProtocolDraft,
        db: Session,
        documents: Sequence[Document] | None = None,
    ) -> QualityAutomationCheckResult:
        methodology = (mission.research_statement.methodology if mission.research_statement else None) or "qualitative"
        rule = self._rule_for_methodology(methodology)
        docs = list(documents) if documents is not None else self._load_documents(db, mission)
        issues: List[QualityIssue] = []
        recommendations: List[str] = []

        participant_total = self._participant_total(docs, mission.methodology_details)
        min_participants = int(rule["min_participants"])  # type: ignore[arg-type]
        if participant_total < min_participants:
            issues.append(
                QualityIssue(
                    code="insufficient_sample",
                    severity="high",
                    message=f"{participant_total} participants recorded; {min_participants} required for {methodology}.",
                    metadata={"observed": participant_total, "required": min_participants},
                )
            )
            recommendations.append("Recruit additional participants or merge this mission with a broader study.")

        metadata_gaps = self._metadata_gaps(docs, rule["required_metadata"])  # type: ignore[arg-type]
        if metadata_gaps:
            issues.append(
                QualityIssue(
                    code="metadata_gaps",
                    severity="medium",
                    message="Documents are missing required methodology metadata.",
                    metadata=metadata_gaps,
                )
            )
            recommendations.append("Ensure uploads include collection_date, source_type, and participant counts.")

        validated_ratio = self._validated_ratio(docs)
        min_ratio = float(rule["min_validated_ratio"])  # type: ignore[arg-type]
        if validated_ratio < min_ratio:
            issues.append(
                QualityIssue(
                    code="insufficient_validation",
                    severity="medium",
                    message=f"Only {validated_ratio:.0%} of documents are marked validated (target {min_ratio:.0%}).",
                )
            )
            recommendations.append("Complete validation workflow for remaining transcripts or survey exports.")

        missing_steps = self._missing_validation_steps(mission.methodology_details, rule["required_validation_steps"])  # type: ignore[arg-type]
        if missing_steps:
            issues.append(
                QualityIssue(
                    code="missing_validation_steps",
                    severity="high",
                    message="Methodology notes do not list all required validation steps.",
                    metadata={"missing": missing_steps},
                )
            )
            recommendations.append("Document the completed validation steps within methodology_details.")

        summary = (
            "Methodology rigor requirements satisfied."
            if not issues
            else "Methodology rigor checks detected sampling or metadata gaps."
        )
        metrics = {
            "participants": participant_total,
            "documents": len(docs),
            "validated_ratio": round(validated_ratio, 3),
        }

        return QualityAutomationCheckResult(
            check_type="methodology_rigor",
            summary=summary,
            issues=issues,
            metrics=metrics,
            recommendations=recommendations,
        )

    def _rule_for_methodology(self, methodology: str) -> Dict[str, object]:
        lowered = methodology.lower()
        if "survey" in lowered or "quant" in lowered:
            return self.RULES["quantitative"]
        if "mixed" in lowered:
            return self.RULES["mixed"]
        return self.RULES["qualitative"]

    def _load_documents(self, db: Session, mission: MissionProtocolDraft) -> List[Document]:
        project_id = getattr(mission, "project_id", None)
        if not project_id:
            return []
        return list(db.query(Document).filter(Document.project_id == project_id).all())

    def _participant_total(self, documents: Sequence[Document], details: MethodologyDetails | None) -> int:
        if details and details.total_participants is not None:
            return details.total_participants
        total = sum(doc.participant_count or 0 for doc in documents)
        if total == 0 and details and details.participant_segments:
            total = sum(segment.count or 0 for segment in details.participant_segments)
        return total

    def _metadata_gaps(self, documents: Sequence[Document], fields: Iterable[str]) -> Dict[str, int]:
        gaps: Dict[str, int] = {}
        if not documents:
            return {field: 1 for field in fields}
        for field in fields:
            missing = sum(1 for doc in documents if not getattr(doc, field, None))
            if missing:
                gaps[field] = missing
        return gaps

    def _validated_ratio(self, documents: Sequence[Document]) -> float:
        if not documents:
            return 0.0
        validated = sum(1 for doc in documents if (doc.validation_status or "").lower() == "validated")
        return validated / len(documents)

    def _missing_validation_steps(
        self,
        details: MethodologyDetails | None,
        required_steps: Iterable[str],
    ) -> List[str]:
        if not required_steps:
            return []
        completed = set((details.validation_steps_completed if details else []) or [])
        return [step for step in required_steps if step not in completed]


__all__ = ["MethodologyRigorChecker"]
