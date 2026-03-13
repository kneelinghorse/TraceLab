"""Rule-based bias detection service."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from app.models.mission_protocol import (
    MethodologyDetails,
    MissionProtocolDraft,
    ParticipantSegment,
)
from app.services.quality_automation_models import (
    QualityAutomationCheckResult,
    QualityIssue,
)


class BiasDetector:
    """Detect leading questions and demographic imbalance in research plans."""

    def __init__(
        self,
        *,
        leading_patterns: Sequence[str] | None = None,
        lower_ratio: float = 0.25,
        upper_ratio: float = 0.6,
    ) -> None:
        patterns = leading_patterns or (
            r"\bdon't you think\b",
            r"\bwouldn't you agree\b",
            r"\bisn't it true\b",
            r"\bhow much do you love\b",
            r"\bwouldn't it be better if\b",
            r"\bshouldn't we\b",
        )
        self._compiled_patterns = [re.compile(pat, re.IGNORECASE) for pat in patterns]
        self.lower_ratio = lower_ratio
        self.upper_ratio = upper_ratio

    def evaluate(self, mission: MissionProtocolDraft) -> QualityAutomationCheckResult:
        """Run bias detection rules on the mission payload."""
        script_text = self._discussion_text(mission)
        leading_matches = self._detect_leading_questions(script_text)
        demographic_issues = self._detect_demographic_imbalance(
            mission.methodology_details
        )

        issues: list[QualityIssue] = []
        recommendations: list[str] = []
        metrics = {
            "leading_question_matches": leading_matches,
            "segment_issues": len(demographic_issues),
        }

        if leading_matches:
            issues.append(
                QualityIssue(
                    code="leading_questions",
                    severity="medium",
                    message=f"Detected {leading_matches} potential leading questions in the discussion guide.",
                )
            )
            recommendations.append(
                "Rewrite moderator prompts as neutral, open-ended questions."
            )

        if demographic_issues:
            for segment, ratio in demographic_issues.items():
                issues.append(
                    QualityIssue(
                        code="demographic_imbalance",
                        severity="high",
                        message=f"Segment '{segment}' holds {ratio:.0%} of the sample, breaching balance thresholds.",
                        metadata={"segment": segment, "ratio": ratio},
                    )
                )
            recommendations.append(
                "Recruit additional participants from under-represented cohorts."
            )

        summary = (
            "Bias detection completed with no findings."
            if not issues
            else "Bias detection flagged leading-question phrasing or demographic imbalance."
        )

        return QualityAutomationCheckResult(
            check_type="bias_detection",
            summary=summary,
            issues=issues,
            metrics=metrics,
            recommendations=recommendations,
        )

    def _discussion_text(self, mission: MissionProtocolDraft) -> str:
        prompts: list[str] = []
        if mission.discussion_guide:
            prompts.extend([item for item in mission.discussion_guide if item])
        if mission.key_questions:
            prompts.extend(
                [
                    question.question
                    for question in mission.key_questions
                    if question.question
                ]
            )
        return " ".join(prompts).lower()

    def _detect_leading_questions(self, script_text: str) -> int:
        if not script_text:
            return 0
        matches = 0
        for pattern in self._compiled_patterns:
            matches += len(pattern.findall(script_text))
        return matches

    def _detect_demographic_imbalance(
        self,
        details: MethodologyDetails | None,
    ) -> Mapping[str, float]:
        if not details or not details.participant_segments:
            return {}

        totals = self._segment_ratios(
            details.participant_segments, details.total_participants
        )
        return {
            name: ratio
            for name, ratio in totals.items()
            if ratio < self.lower_ratio or ratio > self.upper_ratio
        }

    def _segment_ratios(
        self,
        segments: Sequence[ParticipantSegment],
        total_participants: int | None,
    ) -> Mapping[str, float]:
        distributions: dict[str, float] = {}
        total = total_participants or sum(
            seg.count or 0 for seg in segments if seg.count
        )

        for entry in segments:
            ratio: float | None = entry.percentage
            if ratio is not None and ratio > 1:
                ratio = ratio / 100.0
            if ratio is None and entry.count and total:
                ratio = entry.count / total
            if ratio is None:
                continue
            distributions[entry.segment] = max(0.0, min(1.0, ratio))
        return distributions


__all__ = ["BiasDetector"]
