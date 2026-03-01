import pytest

from scripts.pedr_validation_benchmark import (
    apply_quality_scoring,
    build_quality_gates,
    quality_boost_ratio,
    sign_test_p_value,
)
from app.services.pedr import QualityFilters


def _metadata(*, status: str, passed_gates: int, validated: bool = False, pii: bool = False) -> dict:
    mission_data = {}
    if pii:
        mission_data["tags"] = ["pii"]
        mission_data["governance"] = {"piiHandling": True}
    return {
        "mission_id": f"{status}-mission",
        "status": status,
        "quality_gates": build_quality_gates(passed_gates, validated),
        "mission_data": mission_data,
    }


def test_sign_test_p_value():
    assert sign_test_p_value(5, 0) == pytest.approx(0.0625)


def test_quality_boost_ratio_complete_vs_draft():
    metadata_map = {
        "doc-complete": _metadata(status="complete", passed_gates=5, validated=True),
        "doc-draft": _metadata(status="draft", passed_gates=3, validated=False),
    }
    ratio = quality_boost_ratio(metadata_map)
    assert ratio["complete_avg"] > ratio["draft_avg"]
    assert ratio["ratio_complete_vs_draft"] > 1.0


def test_governance_filter_excludes_pii():
    metadata_map = {
        "doc-safe": _metadata(status="complete", passed_gates=5, validated=True, pii=False),
        "doc-pii": _metadata(status="complete", passed_gates=5, validated=True, pii=True),
    }
    results = [
        {"document_id": "doc-safe", "combined_score": 1.0, "score": 1.0},
        {"document_id": "doc-pii", "combined_score": 1.0, "score": 1.0},
    ]
    filtered = apply_quality_scoring(
        results,
        metadata_map=metadata_map,
        filters=QualityFilters(allow_pii=False),
    )
    assert len(filtered) == 1
    assert filtered[0]["document_id"] == "doc-safe"


def test_governance_soft_mode_penalizes_pii():
    metadata_map = {
        "doc-safe": _metadata(status="complete", passed_gates=5, validated=True, pii=False),
        "doc-pii": _metadata(status="complete", passed_gates=5, validated=True, pii=True),
    }
    results = [
        {"document_id": "doc-safe", "combined_score": 1.0, "score": 1.0},
        {"document_id": "doc-pii", "combined_score": 1.0, "score": 1.0},
    ]
    filtered = apply_quality_scoring(
        results,
        metadata_map=metadata_map,
        filters=QualityFilters(allow_pii=False, governance_mode="soft"),
    )
    assert len(filtered) == 2
    assert filtered[0]["document_id"] == "doc-safe"
    assert filtered[1]["document_id"] == "doc-pii"
