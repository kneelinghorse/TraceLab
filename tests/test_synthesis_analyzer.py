"""Unit tests for the SynthesisAnalyzer."""
from __future__ import annotations

from app.models.mission_protocol import MissionProtocolDraft
from app.services.synthesis_analyzer import SynthesisAnalyzer


def test_synthesis_analyzer_detects_shallow_insights_and_steps():
    payload = MissionProtocolDraft.model_validate(
        {
            "mission_id": "QA-SYN",
            "title": "Synthesis QA",
            "research_statement": {
                "topic": "Automation",
                "objective": "Assess synthesis",
                "scope": "Platform",
            },
            "synthesis": {
                "key_insights": ["Too short", "Needs more context"],
                "recommendations": ["Document automation impacts"],
                "next_steps": ["Consider later", "document telemetry"],
            },
            "evidence": [],
        }
    )

    analyzer = SynthesisAnalyzer(min_insight_chars=20, min_recommendation_ratio=1.0)
    result = analyzer.evaluate(payload)
    assert result.status == "warning"
    codes = {issue.code for issue in result.issues}
    assert "shallow_insights" in codes
    assert "insufficient_recommendations" in codes
    assert "non_actionable_next_steps" in codes
