"""Synthesis quality analyzer focusing on depth and actionability."""
from __future__ import annotations

from typing import List, Sequence

from app.models.mission_protocol import MissionProtocolDraft
from app.services.quality_automation_models import (
    QualityAutomationCheckResult,
    QualityIssue,
)


class SynthesisAnalyzer:
    """Validate synthesis depth, actionable recommendations, and next steps."""

    ACTION_VERBS: Sequence[str] = (
        "build",
        "launch",
        "design",
        "instrument",
        "measure",
        "experiment",
        "pilot",
        "validate",
        "ship",
        "iterate",
    )

    def __init__(self, *, min_insight_chars: int = 80, min_recommendation_ratio: float = 0.6) -> None:
        self.min_insight_chars = min_insight_chars
        self.min_recommendation_ratio = min_recommendation_ratio

    def evaluate(self, mission: MissionProtocolDraft) -> QualityAutomationCheckResult:
        synthesis = mission.synthesis
        issues: List[QualityIssue] = []
        recommendations: List[str] = []

        if not synthesis:
            issues.append(
                QualityIssue(
                    code="missing_synthesis",
                    severity="high",
                    message="Synthesis section is empty; cannot assess quality.",
                )
            )
            recommendations.append("Populate synthesis.key_insights, recommendations, and next_steps.")
            return QualityAutomationCheckResult(
                check_type="synthesis_analysis",
                summary="Synthesis section missing.",
                issues=issues,
                recommendations=recommendations,
                metrics={"insights": 0, "recommendations": 0, "next_steps": 0},
            )

        insights = [insight.strip() for insight in synthesis.key_insights if insight and insight.strip()]
        shallow = [insight for insight in insights if len(insight) < self.min_insight_chars]
        if shallow:
            issues.append(
                QualityIssue(
                    code="shallow_insights",
                    severity="medium",
                    message=f"{len(shallow)} insights are under {self.min_insight_chars} characters.",
                    metadata={"examples": shallow[:2]},
                )
            )
            recommendations.append("Expand insights with context, tension, and a 'so what'.")

        rec_count = len(synthesis.recommendations or [])
        required_recs = max(1, int(len(insights) * self.min_recommendation_ratio))
        if rec_count < required_recs:
            issues.append(
                QualityIssue(
                    code="insufficient_recommendations",
                    severity="medium",
                    message=f"{rec_count} recommendations provided; expected >= {required_recs}.",
                )
            )
            recommendations.append("Tie each key insight to at least one recommendation.")

        weak_steps = self._non_actionable_steps(synthesis.next_steps or [])
        if weak_steps:
            issues.append(
                QualityIssue(
                    code="non_actionable_next_steps",
                    severity="low",
                    message="Some next steps are not action-oriented.",
                    metadata={"examples": weak_steps[:2]},
                )
            )
            recommendations.append("Lead next steps with strong verbs and measurable outcomes.")

        summary = (
            "Synthesis reads as actionable and insight-heavy."
            if not issues
            else "Synthesis quality analyzer found depth or actionability gaps."
        )

        metrics = {
            "insights": len(insights),
            "recommendations": rec_count,
            "next_steps": len(synthesis.next_steps or []),
        }

        return QualityAutomationCheckResult(
            check_type="synthesis_analysis",
            summary=summary,
            issues=issues,
            metrics=metrics,
            recommendations=recommendations,
        )

    def _non_actionable_steps(self, steps: Sequence[str]) -> List[str]:
        weak: List[str] = []
        verbs = tuple(self.ACTION_VERBS)
        for step in steps:
            text = (step or "").strip().lower()
            if not text:
                continue
            if not text.startswith(verbs):
                weak.append(step)
        return weak


__all__ = ["SynthesisAnalyzer"]
