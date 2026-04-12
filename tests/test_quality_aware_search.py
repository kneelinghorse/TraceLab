"""Tests for PEDR quality-aware search scoring."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.pedr import QualityFilters, QualityScoringService


class _RecordingLoader:
    def __init__(self, mapping: dict[str, dict[str, Any]]):
        self.mapping = mapping
        self.calls: list[list[str]] = []

    def __call__(self, document_ids):
        normalized = [str(doc_id) for doc_id in document_ids]
        self.calls.append(normalized)
        return {
            doc_id: self.mapping[doc_id]
            for doc_id in normalized
            if doc_id in self.mapping
        }


def _metadata(
    *, status: str, passed_gates: int, validated: bool = False, pii: bool = False
) -> dict[str, Any]:
    gates: dict[str, dict[str, Any]] = {}
    for index, gate in enumerate(QualityScoringService.EXPECTED_GATES):
        gates[gate] = {
            "status": "pass" if index < passed_gates else "pending",
            "validated": validated if index < passed_gates else False,
        }
    mission_data = {"tags": ["pii"]} if pii else {}
    if pii:
        mission_data["governance"] = {"piiHandling": True}
    return {
        "mission_id": f"{status}-mission",
        "status": status,
        "quality_gates": gates,
        "mission_data": mission_data,
    }


def test_complete_mission_scores_higher_than_draft():
    loader = _RecordingLoader(
        {
            "doc-complete": _metadata(
                status="complete", passed_gates=5, validated=True
            ),
            "doc-draft": _metadata(status="draft", passed_gates=2),
        }
    )
    service = QualityScoringService(metadata_loader=loader)

    results = service.apply(
        [
            {"document_id": "doc-complete", "combined_score": 0.8},
            {"document_id": "doc-draft", "combined_score": 0.8},
        ],
        filters=QualityFilters(),
    )

    complete = next(item for item in results if item["document_id"] == "doc-complete")
    draft = next(item for item in results if item["document_id"] == "doc-draft")
    assert complete["quality_score"] > draft["quality_score"]


def test_validation_boost_adds_to_final_score():
    loader = _RecordingLoader(
        {"doc-review": _metadata(status="review", passed_gates=5, validated=True)}
    )
    service = QualityScoringService(metadata_loader=loader)

    result = service.apply(
        [{"document_id": "doc-review", "combined_score": 0.5}],
        filters=QualityFilters(),
    )[0]

    assert result["quality_boost"] == pytest.approx(0.14, rel=1e-3)
    assert result["quality_score"] == pytest.approx(1.14, rel=1e-3)


def test_default_score_used_when_metadata_missing():
    loader = _RecordingLoader({})
    service = QualityScoringService(metadata_loader=loader)

    result = service.apply(
        [{"document_id": "doc-missing", "combined_score": 1.0}],
        filters=QualityFilters(),
    )[0]

    assert result["quality_score"] == pytest.approx(
        QualityScoringService.DEFAULT_BASE_SCORE, rel=1e-3
    )


def test_min_quality_gates_filter():
    loader = _RecordingLoader(
        {
            "doc-strong": _metadata(status="complete", passed_gates=5, validated=True),
            "doc-weak": _metadata(status="review", passed_gates=2),
        }
    )
    service = QualityScoringService(metadata_loader=loader)

    results = service.apply(
        [
            {"document_id": "doc-strong", "combined_score": 0.5},
            {"document_id": "doc-weak", "combined_score": 0.5},
        ],
        filters=QualityFilters(min_quality_gates=4),
    )

    assert len(results) == 1
    assert results[0]["document_id"] == "doc-strong"


def test_status_filter():
    loader = _RecordingLoader(
        {
            "doc-complete": _metadata(status="complete", passed_gates=5),
            "doc-draft": _metadata(status="draft", passed_gates=5),
        }
    )
    service = QualityScoringService(metadata_loader=loader)

    results = service.apply(
        [
            {"document_id": "doc-complete", "combined_score": 0.5},
            {"document_id": "doc-draft", "combined_score": 0.5},
        ],
        filters=QualityFilters(statuses=("complete",)),
    )

    assert len(results) == 1
    assert results[0]["document_id"] == "doc-complete"


def test_allow_pii_filter():
    loader = _RecordingLoader(
        {
            "doc-safe": _metadata(status="complete", passed_gates=5),
            "doc-pii": _metadata(status="complete", passed_gates=5, pii=True),
        }
    )
    service = QualityScoringService(metadata_loader=loader)

    results = service.apply(
        [
            {"document_id": "doc-safe", "combined_score": 0.5},
            {"document_id": "doc-pii", "combined_score": 0.5},
        ],
        filters=QualityFilters(allow_pii=False),
    )

    assert len(results) == 1
    assert results[0]["document_id"] == "doc-safe"


def test_soft_governance_penalty_keeps_pii():
    loader = _RecordingLoader(
        {"doc-pii": _metadata(status="complete", passed_gates=5, pii=True)}
    )
    service = QualityScoringService(metadata_loader=loader)

    result = service.apply(
        [{"document_id": "doc-pii", "combined_score": 1.0}],
        filters=QualityFilters(allow_pii=False, governance_mode="soft"),
    )[0]

    base = 1.0
    boost = QualityScoringService.STATUS_BOOSTS["complete"]
    expected = QualityScoringService._apply_governance_penalty(
        base * (1 + boost),
        QualityScoringService.SOFT_PII_PENALTY,
    )

    assert result["quality_score"] == pytest.approx(expected, rel=1e-3)


def test_warn_governance_keeps_pii_without_penalty():
    loader = _RecordingLoader(
        {"doc-pii": _metadata(status="complete", passed_gates=5, pii=True)}
    )
    service = QualityScoringService(metadata_loader=loader)

    result = service.apply(
        [{"document_id": "doc-pii", "combined_score": 1.0}],
        filters=QualityFilters(allow_pii=False, governance_mode="warn"),
    )[0]

    base = 1.0
    boost = QualityScoringService.STATUS_BOOSTS["complete"]
    expected = base * (1 + boost)

    assert result["quality_score"] == pytest.approx(expected, rel=1e-3)


def test_combined_score_scaled_by_quality():
    loader = _RecordingLoader(
        {"doc-scale": _metadata(status="complete", passed_gates=5)}
    )
    service = QualityScoringService(metadata_loader=loader)

    result = service.apply(
        [{"document_id": "doc-scale", "combined_score": 0.4}],
        filters=QualityFilters(),
    )[0]

    assert result["combined_score"] > 0.4
    assert result["score"] == result["combined_score"]


def test_documents_without_id_preserve_default_quality():
    loader = _RecordingLoader({})
    service = QualityScoringService(metadata_loader=loader)

    result = service.apply(
        [{"document_id": None, "combined_score": 0.3}],
        filters=QualityFilters(),
    )[0]

    assert result["quality_score"] == pytest.approx(
        QualityScoringService.DEFAULT_BASE_SCORE, rel=1e-3
    )


def test_metadata_loader_receives_document_ids():
    loader = _RecordingLoader({"doc-one": _metadata(status="draft", passed_gates=1)})
    service = QualityScoringService(metadata_loader=loader)

    service.apply(
        [{"document_id": "doc-one", "combined_score": 0.2}],
        filters=QualityFilters(),
    )

    assert loader.calls == [["doc-one"]]


def test_in_progress_status_receives_small_boost():
    loader = _RecordingLoader(
        {"doc-progress": _metadata(status="in_progress", passed_gates=3)}
    )
    service = QualityScoringService(metadata_loader=loader)

    result = service.apply(
        [{"document_id": "doc-progress", "combined_score": 0.2}],
        filters=QualityFilters(),
    )[0]

    assert result["quality_boost"] == pytest.approx(0.05, rel=1e-3)


def test_mid_quality_curve_softens_penalties():
    loader = _RecordingLoader(
        {
            "doc-progress": _metadata(status="in_progress", passed_gates=2),
            "doc-review": _metadata(status="review", passed_gates=3),
        }
    )
    service = QualityScoringService(metadata_loader=loader)

    results = service.apply(
        [
            {"document_id": "doc-progress", "combined_score": 0.2},
            {"document_id": "doc-review", "combined_score": 0.2},
        ],
        filters=QualityFilters(),
    )

    progress = next(item for item in results if item["document_id"] == "doc-progress")
    review = next(item for item in results if item["document_id"] == "doc-review")
    total_gates = len(QualityScoringService.EXPECTED_GATES)

    progress_base = (2 / total_gates) ** QualityScoringService.STATUS_CURVE_EXPONENTS[
        "in_progress"
    ]
    review_base = (3 / total_gates) ** QualityScoringService.STATUS_CURVE_EXPONENTS[
        "review"
    ]
    progress_expected = progress_base * (
        1 + QualityScoringService.STATUS_BOOSTS["in_progress"]
    )
    review_expected = review_base * (1 + QualityScoringService.STATUS_BOOSTS["review"])

    assert progress["quality_base_score"] == pytest.approx(progress_base, rel=1e-3)
    assert review["quality_base_score"] == pytest.approx(review_base, rel=1e-3)
    assert progress["quality_score"] == pytest.approx(progress_expected, rel=1e-3)
    assert review["quality_score"] == pytest.approx(review_expected, rel=1e-3)


def test_draft_curve_relaxes_penalty():
    loader = _RecordingLoader({"doc-draft": _metadata(status="draft", passed_gates=3)})
    service = QualityScoringService(metadata_loader=loader)

    result = service.apply(
        [{"document_id": "doc-draft", "combined_score": 0.2}],
        filters=QualityFilters(),
    )[0]

    total_gates = len(QualityScoringService.EXPECTED_GATES)
    draft_base = (3 / total_gates) ** QualityScoringService.STATUS_CURVE_EXPONENTS[
        "draft"
    ]
    expected = draft_base * (1 + QualityScoringService.STATUS_BOOSTS["draft"])

    assert result["quality_base_score"] == pytest.approx(draft_base, rel=1e-3)
    assert result["quality_score"] == pytest.approx(expected, rel=1e-3)


def test_zero_quality_gates_preserve_zero_base_score():
    loader = _RecordingLoader({"doc-zero": _metadata(status="draft", passed_gates=0)})
    service = QualityScoringService(metadata_loader=loader)

    result = service.apply(
        [{"document_id": "doc-zero", "combined_score": 0.4}],
        filters=QualityFilters(),
    )[0]

    assert result["quality_base_score"] == 0.0
    assert result["quality_score"] == pytest.approx(
        QualityScoringService.MIN_SCORE, rel=1e-3
    )
