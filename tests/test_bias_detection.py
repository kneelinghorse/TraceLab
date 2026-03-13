"""Unit tests for the BiasDetector service."""

from __future__ import annotations

from app.models.mission_protocol import MissionProtocolDraft
from app.services.bias_detection import BiasDetector


def _mission_payload(**overrides):
    base = {
        "mission_id": "QA-BIAS",
        "title": "Bias Automation",
        "research_statement": {
            "topic": "Automation",
            "objective": "Detect bias risks",
            "scope": "UX Research",
        },
        "key_questions": [
            {"question": "Don't you think automation saves time?", "status": "open"},
            {"question": "Wouldn't you agree that tooling matters?", "status": "open"},
        ],
        "synthesis": {
            "key_insights": [
                "Quality automation removes manual toil and helps researchers stay focused on rigor."
            ],
            "recommendations": ["Keep automation transparent"],
            "next_steps": ["Document reviewer feedback"],
        },
        "discussion_guide": [
            "Don't you think automation saves time?",
            "Walk me through the biggest blockers.",
        ],
        "methodology_details": {
            "participant_segments": [
                {"segment": "APAC", "percentage": 0.85},
                {"segment": "EMEA", "percentage": 0.15},
            ]
        },
    }
    base.update(overrides)
    return MissionProtocolDraft.model_validate(base)


def test_bias_detector_flags_leading_questions_and_imbalance():
    detector = BiasDetector()
    mission = _mission_payload()
    result = detector.evaluate(mission)
    assert result.status == "failed"
    codes = {issue.code for issue in result.issues}
    assert "leading_questions" in codes
    assert "demographic_imbalance" in codes
    assert any(
        "APAC" in (issue.metadata or {}).get("segment", "") for issue in result.issues
    )
