"""Unit tests for the PEDR pre-flight query service."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.pedr_preflight import (
    PreflightQuery,
)
from app.services.pedr.preflight import (
    PreflightService,
    PreflightThresholds,
)


class _FakeHybridSearchService:
    """Fake search service for testing."""

    def __init__(self, results: list[dict[str, Any]] | None = None):
        self.calls: list[dict[str, Any]] = []
        self._results = results or []

    def search(self, **kwargs) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        return [dict(item) for item in self._results]


def _make_search_result(
    document_id: str,
    score: float,
    **extras: Any,
) -> dict[str, Any]:
    """Create a mock search result."""
    return {
        "chunk_id": f"chunk-{document_id}",
        "content": f"Content for {document_id}",
        "document_id": document_id,
        "project_id": "proj-1",
        "combined_score": score,
        "score": score,
        **extras,
    }


def _make_mission_metadata(
    mission_id: str,
    title: str,
    status: str = "complete",
    passed_gates: int = 5,
    **extras: Any,
) -> dict[str, Any]:
    """Create mock mission metadata."""
    return {
        "mission_uuid": f"uuid-{mission_id}",
        "mission_data": {
            "mission_id": mission_id,
            "title": title,
            "research_statement": {
                "objective": f"Research objective for {title}",
            },
            "synthesis": {
                "key_insights": [
                    "First key insight for testing",
                    "Second key insight for testing",
                ],
            },
            "tags": ["test", "research"],
        },
        "status": status,
        "created_at": datetime.utcnow(),
        "quality_gates_passed": passed_gates,
        "quality_gates_total": 5,
        "quality_score": 1.0,
        **extras,
    }


class TestPreflightThresholds:
    """Tests for threshold configuration."""

    def test_default_thresholds(self):
        thresholds = PreflightThresholds()
        assert thresholds.reuse_similarity == 0.85
        assert thresholds.reuse_min_gates == 4
        assert thresholds.review_similarity == 0.70
        assert thresholds.proceed_below == 0.70

    def test_custom_thresholds(self):
        thresholds = PreflightThresholds(
            reuse_similarity=0.90,
            reuse_min_gates=5,
            review_similarity=0.75,
        )
        assert thresholds.reuse_similarity == 0.90
        assert thresholds.reuse_min_gates == 5
        assert thresholds.review_similarity == 0.75


class TestPreflightServiceRecommendations:
    """Tests for recommendation logic."""

    def test_reuse_recommendation_high_score_high_quality(self):
        """Score >= 0.85 and quality_gates >= 4 should recommend reuse."""
        search_results = [
            _make_search_result("doc-1", score=0.92),
        ]
        fake_search = _FakeHybridSearchService(search_results)

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        with patch.object(
            service,
            "_load_mission_metadata",
            return_value={
                "doc-1": _make_mission_metadata(
                    "M1",
                    "High Quality Research",
                    passed_gates=5,
                ),
            },
        ):
            request = PreflightQuery(query="test research topic")
            result = service.query(request)

        assert result.action == "reuse"
        assert "reusing" in result.summary.lower() or "reuse" in result.summary.lower()
        assert result.match_count == 1
        assert result.top_score == pytest.approx(0.92, rel=0.01)

    def test_review_recommendation_moderate_score(self):
        """Score >= 0.70 but < 0.85 should recommend review."""
        search_results = [
            _make_search_result("doc-1", score=0.78),
        ]
        fake_search = _FakeHybridSearchService(search_results)

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        with patch.object(
            service,
            "_load_mission_metadata",
            return_value={
                "doc-1": _make_mission_metadata(
                    "M1",
                    "Moderate Match Research",
                    passed_gates=5,
                ),
            },
        ):
            request = PreflightQuery(query="test topic")
            result = service.query(request)

        assert result.action == "review"
        assert "review" in result.summary.lower()

    def test_proceed_recommendation_no_matches(self):
        """No matches should recommend proceed."""
        fake_search = _FakeHybridSearchService([])

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        request = PreflightQuery(query="completely new topic")
        result = service.query(request)

        assert result.action == "proceed"
        assert result.match_count == 0
        assert result.top_score is None

    def test_proceed_recommendation_low_score(self):
        """Score below threshold should recommend proceed."""
        search_results = [
            _make_search_result("doc-1", score=0.55),
        ]
        fake_search = _FakeHybridSearchService(search_results)

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        # With default threshold of 0.70, this should be filtered out
        request = PreflightQuery(query="low relevance topic")
        result = service.query(request)

        assert result.action == "proceed"

    def test_reuse_requires_minimum_gates(self):
        """Reuse should require minimum quality gates."""
        search_results = [
            _make_search_result("doc-1", score=0.92),
        ]
        fake_search = _FakeHybridSearchService(search_results)

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        with patch.object(
            service,
            "_load_mission_metadata",
            return_value={
                "doc-1": _make_mission_metadata(
                    "M1",
                    "Low Quality Research",
                    passed_gates=2,  # Below threshold of 4
                ),
            },
        ):
            request = PreflightQuery(query="test topic")
            result = service.query(request)

        # Should be review, not reuse, due to low quality gates
        assert result.action == "review"


class TestPreflightServiceMatching:
    """Tests for match building and deduplication."""

    def test_builds_matches_from_search_results(self):
        """Should build PreflightMatch instances from search results."""
        search_results = [
            _make_search_result("doc-1", score=0.90),
        ]
        fake_search = _FakeHybridSearchService(search_results)

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        with patch.object(
            service,
            "_load_mission_metadata",
            return_value={
                "doc-1": _make_mission_metadata(
                    "DRM.0.5",
                    "Passwordless Auth Patterns",
                    passed_gates=5,
                ),
            },
        ):
            request = PreflightQuery(query="auth patterns")
            result = service.query(request)

        assert len(result.matches) == 1
        match = result.matches[0]
        assert match.mission_id == "DRM.0.5"
        assert match.title == "Passwordless Auth Patterns"
        assert match.status == "complete"
        assert match.quality_gates_passed == 5
        assert len(match.key_insights) <= 3

    def test_deduplicates_missions(self):
        """Should deduplicate matches by mission UUID."""
        search_results = [
            _make_search_result("doc-1", score=0.95),
            _make_search_result("doc-2", score=0.85),
        ]
        fake_search = _FakeHybridSearchService(search_results)

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        # Both documents belong to the same mission
        same_mission_meta = _make_mission_metadata("M1", "Same Mission", passed_gates=5)
        with patch.object(
            service,
            "_load_mission_metadata",
            return_value={
                "doc-1": same_mission_meta,
                "doc-2": same_mission_meta,
            },
        ):
            request = PreflightQuery(query="test")
            result = service.query(request)

        # Should only have one match due to deduplication
        assert len(result.matches) == 1

    def test_sorts_matches_by_similarity(self):
        """Should sort matches by similarity score descending."""
        search_results = [
            _make_search_result("doc-1", score=0.75),
            _make_search_result("doc-2", score=0.95),
            _make_search_result("doc-3", score=0.85),
        ]
        fake_search = _FakeHybridSearchService(search_results)

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        with patch.object(
            service,
            "_load_mission_metadata",
            return_value={
                "doc-1": _make_mission_metadata("M1", "Mission 1", passed_gates=5),
                "doc-2": _make_mission_metadata("M2", "Mission 2", passed_gates=5),
                "doc-3": _make_mission_metadata("M3", "Mission 3", passed_gates=5),
            },
        ):
            request = PreflightQuery(query="test")
            result = service.query(request)

        assert len(result.matches) == 3
        assert result.matches[0].similarity_score > result.matches[1].similarity_score
        assert result.matches[1].similarity_score > result.matches[2].similarity_score


class TestPreflightQuery:
    """Tests for query parameter handling."""

    def test_uses_hybrid_search_mode(self):
        """Should use hybrid search mode for queries."""
        fake_search = _FakeHybridSearchService([])

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        request = PreflightQuery(query="test query")
        service.query(request)

        assert len(fake_search.calls) == 1
        assert fake_search.calls[0]["search_mode"] == "hybrid"

    def test_passes_quality_filters(self):
        """Should pass quality filters to search service."""
        fake_search = _FakeHybridSearchService([])

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        request = PreflightQuery(
            query="test",
            min_quality_gates=3,
            status=["complete", "review"],
        )
        service.query(request)

        assert fake_search.calls[0]["min_quality_gates"] == 3
        assert fake_search.calls[0]["status_filters"] == ["complete", "review"]

    def test_respects_top_k_limit(self):
        """Should limit results to top_k."""
        search_results = [
            _make_search_result(f"doc-{i}", score=0.90 - i * 0.05) for i in range(10)
        ]
        fake_search = _FakeHybridSearchService(search_results)

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        with patch.object(
            service,
            "_load_mission_metadata",
            return_value={
                f"doc-{i}": _make_mission_metadata(
                    f"M{i}", f"Mission {i}", passed_gates=5
                )
                for i in range(10)
            },
        ):
            request = PreflightQuery(query="test", top_k=3)
            result = service.query(request)

        assert len(result.matches) <= 3


class TestPreflightLatency:
    """Tests for latency tracking."""

    def test_tracks_latency(self):
        """Should track query latency."""
        fake_search = _FakeHybridSearchService([])

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        request = PreflightQuery(query="test")
        result = service.query(request)

        assert result.latency_ms >= 0
        assert isinstance(result.latency_ms, float)


class TestPreflightFiltersApplied:
    """Tests for filter tracking in response."""

    def test_includes_filters_in_response(self):
        """Should include applied filters in response."""
        fake_search = _FakeHybridSearchService([])

        service = PreflightService(
            search_service=fake_search,
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        request = PreflightQuery(
            query="test",
            min_quality_gates=4,
            status=["complete"],
            similarity_threshold=0.75,
        )
        result = service.query(request)

        assert result.filters_applied["min_quality_gates"] == 4
        assert result.filters_applied["status"] == ["complete"]
        assert result.filters_applied["similarity_threshold"] == 0.75


class TestQualityGateCounting:
    """Tests for quality gate counting logic."""

    def test_counts_passing_gates_from_quality_gates(self):
        """Should count passing gates from quality_gates field."""
        service = PreflightService(
            search_service=MagicMock(),
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        quality_gates = {
            "research_statement": {"status": "pass"},
            "evidence_links": {"status": "passed"},
            "synthesis_quality": {"status": "complete"},
            "traceability": {"status": "pending"},
            "contradictions_resolved": {"status": "fail"},
        }

        count = service._count_passed_gates(quality_gates, {})
        assert count == 3

    def test_counts_gates_from_mission_data_checkpoints(self):
        """Should count gates from mission_data quality_checkpoints."""
        service = PreflightService(
            search_service=MagicMock(),
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        mission_data = {
            "quality_checkpoints": [
                {"gate": "research_statement", "status": "pass"},
                {"gate": "evidence_links", "status": "pass"},
            ],
        }

        count = service._count_passed_gates({}, mission_data)
        assert count == 2


class TestPreflightMatchInsights:
    """Tests for key insights extraction."""

    def test_extracts_key_insights(self):
        """Should extract up to 3 key insights."""
        service = PreflightService(
            search_service=MagicMock(),
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        metadata = {
            "mission_uuid": "uuid-1",
            "mission_data": {
                "mission_id": "M1",
                "title": "Test Mission",
                "research_statement": {"objective": "Test objective"},
                "synthesis": {
                    "key_insights": [
                        "First insight",
                        "Second insight",
                        "Third insight",
                        "Fourth insight",
                    ],
                },
            },
            "status": "complete",
            "created_at": datetime.utcnow(),
            "quality_gates_passed": 5,
            "quality_gates_total": 5,
            "quality_score": 1.0,
        }

        match = service._build_single_match(metadata, 0.90)

        assert match is not None
        assert len(match.key_insights) == 3
        assert match.key_insights[0].text == "First insight"

    def test_truncates_long_insights(self):
        """Should truncate insights longer than 150 chars."""
        service = PreflightService(
            search_service=MagicMock(),
            session_factory=MagicMock(),
            telemetry_enabled=False,
        )

        long_insight = "A" * 200  # 200 characters

        metadata = {
            "mission_uuid": "uuid-1",
            "mission_data": {
                "mission_id": "M1",
                "title": "Test",
                "research_statement": {},
                "synthesis": {"key_insights": [long_insight]},
            },
            "status": "complete",
            "created_at": datetime.utcnow(),
            "quality_gates_passed": 5,
            "quality_gates_total": 5,
            "quality_score": 1.0,
        }

        match = service._build_single_match(metadata, 0.90)

        assert match is not None
        assert len(match.key_insights[0].text) <= 150
        assert match.key_insights[0].text.endswith("...")
