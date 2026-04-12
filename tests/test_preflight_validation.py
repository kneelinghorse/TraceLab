"""Preflight & Quality Gate Validation Tests — T33.2 Deliverable.

Validates:
1. Preflight similarity thresholds with known-duplicate and novel queries
2. Quality gate scoring against completed mission scenarios
3. Governance mode behavior (strict/soft/warn) produces correct outcomes
4. Edge cases: empty corpus, single document, no gates, stale missions
5. Threshold analysis with documented rationale

Uses injectable metadata loader to avoid DB dependency while testing
real scoring logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import MagicMock

import pytest

from app.schemas.pedr_preflight import (
    PreflightMatch,
    PreflightQuery,
    PreflightRecommendation,
)
from app.services.pedr.preflight import (
    PreflightService,
    PreflightThresholds,
)
from app.services.pedr.quality_scoring import (
    QualityFilters,
    QualityScore,
    QualityScoringService,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quality_gates(passed: int) -> Dict[str, Dict[str, Any]]:
    """Build a quality_gates dict with N passing gates out of 5."""
    gates = [
        "research_statement",
        "evidence_links",
        "synthesis_quality",
        "traceability",
        "contradictions_resolved",
    ]
    result: Dict[str, Dict[str, Any]] = {}
    for i, gate in enumerate(gates):
        if i < passed:
            result[gate] = {"status": "pass", "validated": True}
        else:
            result[gate] = {"status": "pending", "validated": False}
    return result


def _make_metadata(
    mission_id: str = "M-001",
    status: str = "complete",
    passed_gates: int = 5,
    pii: bool = False,
    validated: bool = True,
) -> Dict[str, Any]:
    """Build a metadata dict suitable for QualityScoringService._score_metadata()."""
    gates = _make_quality_gates(passed_gates)
    mission_data: Dict[str, Any] = {}
    if pii:
        mission_data["pii_flag"] = True
    return {
        "mission_id": mission_id,
        "status": status,
        "quality_gates": gates,
        "mission_data": mission_data,
    }


def _make_search_result(doc_id: str, score: float) -> Dict[str, Any]:
    return {
        "chunk_id": f"chunk-{doc_id}",
        "content": f"Content for {doc_id}",
        "document_id": doc_id,
        "project_id": "proj-1",
        "combined_score": score,
        "score": score,
    }


def _make_mission_metadata_for_preflight(
    mission_id: str,
    title: str,
    status: str = "complete",
    passed_gates: int = 5,
) -> Dict[str, Any]:
    return {
        "mission_uuid": f"uuid-{mission_id}",
        "mission_data": {
            "mission_id": mission_id,
            "title": title,
            "research_statement": {"objective": f"Research objective: {title}"},
            "synthesis": {"key_insights": ["Key insight 1", "Key insight 2"]},
            "tags": ["research"],
        },
        "status": status,
        "created_at": datetime.now(timezone.utc),
        "quality_gates_passed": passed_gates,
        "quality_gates_total": 5,
        "quality_score": 1.0,
    }


class _FakeSearchService:
    """Fake search service returning configurable results."""

    def __init__(self, results: List[Dict[str, Any]]):
        self._results = results

    def search(self, **kwargs) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._results]


def _make_preflight_service(
    search_results: List[Dict[str, Any]],
    mission_metadata: Dict[str, Dict[str, Any]],
    thresholds: Optional[PreflightThresholds] = None,
) -> PreflightService:
    service = PreflightService(
        search_service=_FakeSearchService(search_results),
        session_factory=MagicMock(),
        thresholds=thresholds,
        telemetry_enabled=False,
    )
    service._load_mission_metadata = lambda doc_ids: mission_metadata
    return service


def _make_scoring_service(
    metadata_map: Dict[str, Dict[str, Any]],
) -> QualityScoringService:
    """Create a QualityScoringService with injectable metadata loader."""
    return QualityScoringService(
        metadata_loader=lambda doc_ids: {
            k: v for k, v in metadata_map.items() if k in doc_ids
        },
    )


# ===========================================================================
# 1. PREFLIGHT SIMILARITY THRESHOLD VALIDATION
# ===========================================================================


class TestPreflightDuplicateQueries:
    """5+ known-duplicate queries that should trigger 'reuse' at >= 85%."""

    DUPLICATE_SCENARIOS = [
        ("doc-dup-1", 0.92, 5, "Impact of transformer architectures on NLP"),
        ("doc-dup-2", 0.88, 4, "Graph neural network applications in biology"),
        ("doc-dup-3", 0.95, 5, "Reinforcement learning for robotics control"),
        ("doc-dup-4", 0.87, 4, "Federated learning privacy guarantees"),
        ("doc-dup-5", 0.90, 5, "Large language model alignment techniques"),
    ]

    @pytest.mark.parametrize("doc_id,score,gates,title", DUPLICATE_SCENARIOS)
    def test_high_similarity_high_quality_returns_reuse(
        self, doc_id, score, gates, title
    ):
        results = [_make_search_result(doc_id, score)]
        metadata = {
            doc_id: _make_mission_metadata_for_preflight(
                f"M-{doc_id}", title, "complete", gates
            )
        }
        service = _make_preflight_service(results, metadata)

        rec = service.query(PreflightQuery(query=title))
        assert rec.action == "reuse", (
            f"Expected 'reuse' for score={score}, gates={gates}"
        )
        assert rec.top_score >= 0.85
        assert rec.match_count >= 1

    def test_high_similarity_low_quality_returns_review(self):
        """Score >= 0.85 but quality_gates < 4 should be 'review', not 'reuse'."""
        results = [_make_search_result("doc-low-q", 0.90)]
        metadata = {
            "doc-low-q": _make_mission_metadata_for_preflight(
                "M-low-q",
                "Low quality match",
                "complete",
                2,  # Only 2/5 gates
            )
        }
        service = _make_preflight_service(results, metadata)

        rec = service.query(PreflightQuery(query="Low quality match"))
        assert rec.action == "review"


class TestPreflightNovelQueries:
    """5+ novel queries that should trigger 'proceed' at < 70%."""

    NOVEL_SCENARIOS = [
        ("doc-novel-1", 0.45, "Quantum computing error correction"),
        ("doc-novel-2", 0.30, "Cryptocurrency market dynamics"),
        ("doc-novel-3", 0.55, "Climate change mitigation strategies"),
        ("doc-novel-4", 0.10, "Ancient Roman trade routes"),
        ("doc-novel-5", 0.65, "Protein folding prediction methods"),
        ("doc-novel-6", 0.00, "Completely unrelated topic"),
    ]

    @pytest.mark.parametrize("doc_id,score,title", NOVEL_SCENARIOS)
    def test_low_similarity_returns_proceed(self, doc_id, score, title):
        results = [_make_search_result(doc_id, score)]
        metadata = {
            doc_id: _make_mission_metadata_for_preflight(
                f"M-{doc_id}", title, "complete", 5
            )
        }
        service = _make_preflight_service(results, metadata)

        rec = service.query(PreflightQuery(query=title, similarity_threshold=0.70))
        assert rec.action == "proceed", f"Expected 'proceed' for score={score}"

    def test_empty_results_returns_proceed(self):
        """No search results should always return 'proceed'."""
        service = _make_preflight_service([], {})
        rec = service.query(PreflightQuery(query="Anything"))
        assert rec.action == "proceed"
        assert rec.match_count == 0


class TestPreflightReviewZone:
    """Queries in the 70-85% review zone."""

    REVIEW_SCENARIOS = [
        ("doc-rev-1", 0.75, 5, "Partial match topic A"),
        ("doc-rev-2", 0.82, 3, "Close match but low quality"),
        ("doc-rev-3", 0.71, 5, "Just above review threshold"),
        ("doc-rev-4", 0.84, 5, "Just below reuse threshold"),
    ]

    @pytest.mark.parametrize("doc_id,score,gates,title", REVIEW_SCENARIOS)
    def test_mid_similarity_returns_review(self, doc_id, score, gates, title):
        results = [_make_search_result(doc_id, score)]
        metadata = {
            doc_id: _make_mission_metadata_for_preflight(
                f"M-{doc_id}", title, "complete", gates
            )
        }
        service = _make_preflight_service(results, metadata)

        rec = service.query(PreflightQuery(query=title))
        assert rec.action == "review", (
            f"Expected 'review' for score={score}, gates={gates}"
        )


# ===========================================================================
# 2. QUALITY GATE SCORING VALIDATION
# ===========================================================================


class TestQualityGateScoring:
    """Verify quality gate scoring matches expected behavior."""

    def test_all_gates_passed_complete_status(self):
        """5/5 gates + complete status → highest score."""
        service = QualityScoringService()
        score = service._score_metadata(
            _make_metadata(passed_gates=5, status="complete")
        )
        assert score.passed_gates == 5
        assert score.status == "complete"
        # 5/5 = 1.0 base × (1 + 0.12 boost + 0.05 validation) = 1.17
        assert 1.1 <= score.final_score <= 1.20

    def test_zero_gates_uses_default_base(self):
        """0 gates → DEFAULT_BASE_SCORE (0.60)."""
        service = QualityScoringService()
        score = service._score_metadata(
            _make_metadata(passed_gates=0, status="complete")
        )
        assert score.passed_gates == 0
        # 0/5 = 0.0 base, but still gets status boost
        assert score.base_score == 0.0  # No curve applied since status is "complete"
        assert score.final_score >= QualityScoringService.MIN_SCORE

    def test_partial_gates_draft_status_softened(self):
        """2/5 gates + draft → base^0.45 curve softens penalty."""
        service = QualityScoringService()
        score = service._score_metadata(_make_metadata(passed_gates=2, status="draft"))
        # base = 2/5 = 0.4, curved = 0.4^0.45 ≈ 0.665
        assert score.base_score > 0.4  # Curve should raise it
        assert score.boost == 0.0  # draft gets no boost

    def test_review_status_applies_curve_and_boost(self):
        """3/5 gates + review → softened by x^0.80, boosted by +9%."""
        service = QualityScoringService()
        score = service._score_metadata(_make_metadata(passed_gates=3, status="review"))
        # base = 3/5 = 0.6, curved = 0.6^0.80 ≈ 0.656
        assert score.base_score > 0.6
        assert score.boost >= 0.09

    def test_in_progress_status_curve(self):
        """4/5 gates + in_progress → x^0.70 curve."""
        service = QualityScoringService()
        score = service._score_metadata(
            _make_metadata(passed_gates=4, status="in_progress")
        )
        # base = 4/5 = 0.8, curved = 0.8^0.70 ≈ 0.858
        assert score.base_score > 0.8
        assert score.boost >= 0.05  # in_progress boost

    def test_unknown_status_no_boost_no_curve(self):
        """Unknown status → no curve, no boost."""
        service = QualityScoringService()
        score = service._score_metadata(
            _make_metadata(passed_gates=3, status="unknown")
        )
        assert score.base_score == 0.6  # 3/5 = 0.6, no curve
        assert score.boost == 0.0

    def test_score_clamped_to_range(self):
        """Score should never exceed MAX_SCORE (1.50) or go below MIN_SCORE (0.10)."""
        service = QualityScoringService()
        # Maximum possible: 5/5 gates + complete + validated = 1.0 × 1.17 = 1.17
        score_max = service._score_metadata(
            _make_metadata(passed_gates=5, status="complete")
        )
        assert score_max.final_score <= QualityScoringService.MAX_SCORE

        # Minimum: 0 gates + unknown status
        score_min = service._score_metadata(
            _make_metadata(passed_gates=0, status="unknown")
        )
        assert score_min.final_score >= QualityScoringService.MIN_SCORE

    def test_validation_boost_applied(self):
        """Validated gates should add VALIDATION_BOOST (0.05)."""
        service = QualityScoringService()
        score = service._score_metadata(
            _make_metadata(passed_gates=5, status="complete", validated=True)
        )
        assert score.validated is True
        assert score.boost >= 0.12 + 0.05  # status + validation


class TestQualityGateFromCheckpoints:
    """Verify gates are extracted from both quality_gates and quality_checkpoints."""

    def test_gates_from_primary_source(self):
        """quality_gates dict is the primary source."""
        service = QualityScoringService()
        metadata = {
            "mission_id": "M-1",
            "status": "complete",
            "quality_gates": {
                "research_statement": {"status": "pass"},
                "evidence_links": {"status": "pass"},
                "synthesis_quality": {"status": "pass"},
            },
            "mission_data": {},
        }
        score = service._score_metadata(metadata)
        assert score.passed_gates == 3

    def test_gates_from_checkpoints_fallback(self):
        """quality_checkpoints fills gaps not covered by quality_gates."""
        service = QualityScoringService()
        metadata = {
            "mission_id": "M-1",
            "status": "complete",
            "quality_gates": {
                "research_statement": {"status": "pass"},
            },
            "mission_data": {
                "quality_checkpoints": [
                    {"gate": "evidence_links", "status": "pass"},
                    {"gate": "traceability", "status": "pass"},
                ],
            },
        }
        score = service._score_metadata(metadata)
        assert score.passed_gates == 3  # 1 from gates + 2 from checkpoints


# ===========================================================================
# 3. GOVERNANCE MODE VALIDATION
# ===========================================================================


class TestGovernanceModes:
    """Verify strict/soft/warn governance modes produce correct outcomes."""

    def _make_results_with_pii(self) -> tuple:
        """Create results with one PII-flagged and one clean document."""
        results = [
            _make_search_result("doc-pii", 0.8),
            _make_search_result("doc-clean", 0.7),
        ]
        metadata = {
            "doc-pii": _make_metadata(
                mission_id="M-pii", status="complete", passed_gates=5, pii=True
            ),
            "doc-clean": _make_metadata(
                mission_id="M-clean", status="complete", passed_gates=5, pii=False
            ),
        }
        return results, metadata

    def test_strict_excludes_pii_results(self):
        """Strict mode: PII-flagged results are excluded entirely."""
        results, metadata = self._make_results_with_pii()
        service = _make_scoring_service(metadata)

        filters = QualityFilters(allow_pii=False, governance_mode="strict")
        annotated = service.apply(results, filters=filters)

        doc_ids = [r["document_id"] for r in annotated]
        assert "doc-pii" not in doc_ids
        assert "doc-clean" in doc_ids

    def test_soft_penalizes_pii_results(self):
        """Soft mode: PII-flagged results kept but penalized by 30%."""
        results, metadata = self._make_results_with_pii()
        service = _make_scoring_service(metadata)

        filters = QualityFilters(allow_pii=False, governance_mode="soft")
        annotated = service.apply(results, filters=filters)

        doc_ids = [r["document_id"] for r in annotated]
        assert "doc-pii" in doc_ids
        assert "doc-clean" in doc_ids

        pii_result = next(r for r in annotated if r["document_id"] == "doc-pii")
        clean_result = next(r for r in annotated if r["document_id"] == "doc-clean")
        # PII result should have lower quality_score due to penalty
        assert pii_result["quality_score"] < clean_result["quality_score"]

    def test_warn_keeps_pii_without_penalty(self):
        """Warn mode: PII results kept with no score penalty."""
        results, metadata = self._make_results_with_pii()
        service = _make_scoring_service(metadata)

        filters = QualityFilters(allow_pii=False, governance_mode="warn")
        annotated = service.apply(results, filters=filters)

        doc_ids = [r["document_id"] for r in annotated]
        assert "doc-pii" in doc_ids
        assert "doc-clean" in doc_ids

        pii_result = next(r for r in annotated if r["document_id"] == "doc-pii")
        clean_result = next(r for r in annotated if r["document_id"] == "doc-clean")
        # Same quality_score since no penalty in warn mode
        assert pii_result["quality_score"] == clean_result["quality_score"]

    def test_allow_pii_true_ignores_governance(self):
        """When allow_pii=True, governance mode is irrelevant."""
        results, metadata = self._make_results_with_pii()
        service = _make_scoring_service(metadata)

        filters = QualityFilters(allow_pii=True, governance_mode="strict")
        annotated = service.apply(results, filters=filters)

        # Both results should be present even in strict mode
        doc_ids = [r["document_id"] for r in annotated]
        assert "doc-pii" in doc_ids
        assert "doc-clean" in doc_ids


# ===========================================================================
# 4. EDGE CASES
# ===========================================================================


class TestEdgeCases:
    """Edge cases: empty corpus, single document, stale missions."""

    def test_empty_results_returns_empty(self):
        """Empty search results → empty annotation."""
        service = _make_scoring_service({})
        annotated = service.apply([])
        assert annotated == []

    def test_single_document_annotated(self):
        """Single document is properly annotated."""
        results = [_make_search_result("doc-1", 0.9)]
        metadata = {"doc-1": _make_metadata(passed_gates=3, status="review")}
        service = _make_scoring_service(metadata)

        annotated = service.apply(results)
        assert len(annotated) == 1
        assert annotated[0]["quality_gates_passed"] == 3
        assert annotated[0]["quality_status"] == "review"

    def test_missing_metadata_uses_defaults(self):
        """Document with no mission metadata gets default score."""
        results = [_make_search_result("doc-orphan", 0.8)]
        service = _make_scoring_service({})  # No metadata

        annotated = service.apply(results)
        assert len(annotated) == 1
        assert annotated[0]["quality_score"] == QualityScoringService.DEFAULT_BASE_SCORE

    def test_min_quality_gates_filter(self):
        """Results below min_quality_gates are filtered out."""
        results = [
            _make_search_result("doc-high", 0.9),
            _make_search_result("doc-low", 0.85),
        ]
        metadata = {
            "doc-high": _make_metadata(passed_gates=4, status="complete"),
            "doc-low": _make_metadata(passed_gates=1, status="complete"),
        }
        service = _make_scoring_service(metadata)

        filters = QualityFilters(min_quality_gates=3)
        annotated = service.apply(results, filters=filters)

        doc_ids = [r["document_id"] for r in annotated]
        assert "doc-high" in doc_ids
        assert "doc-low" not in doc_ids

    def test_status_filter_excludes_non_matching(self):
        """Only results with matching statuses are returned."""
        results = [
            _make_search_result("doc-complete", 0.9),
            _make_search_result("doc-draft", 0.85),
        ]
        metadata = {
            "doc-complete": _make_metadata(status="complete"),
            "doc-draft": _make_metadata(status="draft"),
        }
        service = _make_scoring_service(metadata)

        filters = QualityFilters(statuses=("complete",))
        annotated = service.apply(results, filters=filters)

        doc_ids = [r["document_id"] for r in annotated]
        assert "doc-complete" in doc_ids
        assert "doc-draft" not in doc_ids

    def test_preflight_empty_corpus_proceeds(self):
        """Preflight with zero search results returns 'proceed'."""
        service = _make_preflight_service([], {})
        rec = service.query(PreflightQuery(query="Any research topic"))
        assert rec.action == "proceed"
        assert rec.match_count == 0
        assert rec.top_score is None

    def test_preflight_single_low_quality_document(self):
        """Single document with low quality gates → review instead of reuse."""
        results = [_make_search_result("doc-1", 0.90)]
        metadata = {
            "doc-1": _make_mission_metadata_for_preflight(
                "M-1",
                "Single match",
                "complete",
                2,  # Only 2/5 gates
            )
        }
        service = _make_preflight_service(results, metadata)

        rec = service.query(PreflightQuery(query="Single match"))
        assert rec.action == "review"  # Not reuse because gates < 4


# ===========================================================================
# 5. THRESHOLD ANALYSIS
# ===========================================================================


class TestThresholdAnalysis:
    """Document and validate current threshold settings.

    Current thresholds:
    - reuse_similarity: 0.85 — high bar ensures only very relevant research is reused
    - reuse_min_gates: 4 — at least 4/5 quality gates must pass for reuse
    - review_similarity: 0.70 — moderate bar for human review
    - proceed_below: 0.70 — anything below triggers new research

    Analysis: These thresholds create a clear 3-zone decision boundary:
    - [0.85, 1.0] + 4+ gates → REUSE (high confidence)
    - [0.70, 0.85) or gates < 4 → REVIEW (needs human judgment)
    - [0.0, 0.70) → PROCEED (insufficient existing research)
    """

    def test_boundary_at_reuse_threshold(self):
        """Scores exactly at 0.85 with 4 gates should trigger reuse."""
        results = [_make_search_result("doc-boundary", 0.85)]
        metadata = {
            "doc-boundary": _make_mission_metadata_for_preflight(
                "M-boundary", "Boundary test", "complete", 4
            )
        }
        service = _make_preflight_service(results, metadata)
        rec = service.query(PreflightQuery(query="Boundary test"))
        assert rec.action == "reuse"

    def test_boundary_just_below_reuse(self):
        """Score at 0.849 should trigger review, not reuse."""
        results = [_make_search_result("doc-below", 0.849)]
        metadata = {
            "doc-below": _make_mission_metadata_for_preflight(
                "M-below", "Below threshold", "complete", 5
            )
        }
        service = _make_preflight_service(results, metadata)
        rec = service.query(PreflightQuery(query="Below threshold"))
        assert rec.action == "review"

    def test_boundary_at_review_threshold(self):
        """Score exactly at 0.70 should trigger review."""
        results = [_make_search_result("doc-rev", 0.70)]
        metadata = {
            "doc-rev": _make_mission_metadata_for_preflight(
                "M-rev", "Review boundary", "complete", 5
            )
        }
        service = _make_preflight_service(results, metadata)
        rec = service.query(PreflightQuery(query="Review boundary"))
        assert rec.action == "review"

    def test_boundary_just_below_review(self):
        """Score at 0.699 should trigger proceed."""
        results = [_make_search_result("doc-proceed", 0.699)]
        metadata = {
            "doc-proceed": _make_mission_metadata_for_preflight(
                "M-proceed", "Proceed boundary", "complete", 5
            )
        }
        service = _make_preflight_service(results, metadata)
        rec = service.query(
            PreflightQuery(
                query="Proceed boundary",
                similarity_threshold=0.60,  # Lower threshold to allow the match through
            )
        )
        assert rec.action == "proceed"

    def test_custom_thresholds_override_defaults(self):
        """Custom thresholds should change decision boundaries."""
        results = [_make_search_result("doc-custom", 0.80)]
        metadata = {
            "doc-custom": _make_mission_metadata_for_preflight(
                "M-custom", "Custom threshold", "complete", 5
            )
        }
        # Lower reuse threshold to 0.80
        service = _make_preflight_service(
            results,
            metadata,
            thresholds=PreflightThresholds(reuse_similarity=0.80, reuse_min_gates=3),
        )
        rec = service.query(PreflightQuery(query="Custom threshold"))
        assert rec.action == "reuse"  # Would be "review" with default thresholds
