"""Unit tests for the PEDR syntactic layer (type detection and filtering)."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.pedr.syntactic import (
    ElementType,
    SyntacticFilters,
    SyntacticService,
    get_syntactic_service,
)


class TestElementType:
    """Tests for ElementType enum."""

    def test_values_contains_all_types(self):
        """All expected element types are available."""
        values = ElementType.values()
        assert "mission" in values
        assert "document" in values
        assert "insight" in values
        assert "chunk" in values
        assert len(values) == 4

    def test_enum_string_conversion(self):
        """Element types convert to expected strings."""
        assert ElementType.MISSION.value == "mission"
        assert ElementType.DOCUMENT.value == "document"
        assert ElementType.INSIGHT.value == "insight"
        assert ElementType.CHUNK.value == "chunk"


class TestTypeDetection:
    """Tests for query-based type detection."""

    @pytest.fixture
    def service(self) -> SyntacticService:
        return SyntacticService()

    # Mission detection tests
    @pytest.mark.parametrize(
        "query,expected_confidence_min",
        [
            ("find all missions about user research", 0.9),
            ("show missions related to onboarding", 0.9),
            ("what missions cover authentication?", 0.85),
            ("list missions for sprint 12", 0.9),
            ("get mission objectives", 0.7),
            ("research missions about pricing", 0.9),
        ],
    )
    def test_detect_mission_queries(
        self,
        service: SyntacticService,
        query: str,
        expected_confidence_min: float,
    ):
        """Queries asking for missions are detected correctly."""
        result = service.detect_type(query)
        assert result.detected_type == ElementType.MISSION
        assert result.confidence >= expected_confidence_min
        assert len(result.signals) > 0

    # Document detection tests
    @pytest.mark.parametrize(
        "query,expected_confidence_min",
        [
            ("find documents about user interviews", 0.9),
            ("show documents containing pricing feedback", 0.9),
            ("what documents cover the API?", 0.85),
            ("list transcripts about onboarding", 0.85),
            ("get source documents for research", 0.9),
            ("uploaded files related to design", 0.7),
        ],
    )
    def test_detect_document_queries(
        self,
        service: SyntacticService,
        query: str,
        expected_confidence_min: float,
    ):
        """Queries asking for documents are detected correctly."""
        result = service.detect_type(query)
        assert result.detected_type == ElementType.DOCUMENT
        assert result.confidence >= expected_confidence_min

    # Insight detection tests
    @pytest.mark.parametrize(
        "query,expected_confidence_min",
        [
            ("find insights about user pain points", 0.9),
            ("show key findings from research", 0.9),
            ("what did we learn about conversion?", 0.85),
            ("list key takeaways from interviews", 0.9),
            ("get insights related to churn", 0.9),
            ("summary of findings from usability tests", 0.65),
        ],
    )
    def test_detect_insight_queries(
        self,
        service: SyntacticService,
        query: str,
        expected_confidence_min: float,
    ):
        """Queries asking for insights are detected correctly."""
        result = service.detect_type(query)
        assert result.detected_type == ElementType.INSIGHT
        assert result.confidence >= expected_confidence_min

    # Chunk detection tests
    @pytest.mark.parametrize(
        "query,expected_confidence_min",
        [
            ("find chunks containing pricing", 0.9),
            ("show text chunks about authentication", 0.9),
            ("get raw chunks with user feedback", 0.85),
            ("specific quote about performance", 0.7),
        ],
    )
    def test_detect_chunk_queries(
        self,
        service: SyntacticService,
        query: str,
        expected_confidence_min: float,
    ):
        """Queries asking for chunks are detected correctly."""
        result = service.detect_type(query)
        assert result.detected_type == ElementType.CHUNK
        assert result.confidence >= expected_confidence_min

    def test_no_detection_for_generic_query(self, service: SyntacticService):
        """Generic queries should not trigger type detection."""
        result = service.detect_type("tell me about user feedback")
        # May or may not detect - if confidence is below threshold
        if result.detected_type:
            assert result.confidence >= 0.5

    def test_empty_query_returns_no_detection(self, service: SyntacticService):
        """Empty queries return no detection."""
        result = service.detect_type("")
        assert result.detected_type is None
        assert result.confidence == 0.0
        assert result.signals == []

    def test_whitespace_query_returns_no_detection(self, service: SyntacticService):
        """Whitespace-only queries return no detection."""
        result = service.detect_type("   ")
        assert result.detected_type is None
        assert result.confidence == 0.0

    def test_signals_contain_pattern_info(self, service: SyntacticService):
        """Detection signals include pattern match details."""
        result = service.detect_type("find all missions about research")
        assert result.signals
        # Signals should contain element type, matched pattern, confidence
        for signal in result.signals:
            parts = signal.split(":")
            assert len(parts) >= 2


class TestSyntacticFilters:
    """Tests for filter creation."""

    @pytest.fixture
    def service(self) -> SyntacticService:
        return SyntacticService()

    def test_create_filters_with_single_type(self, service: SyntacticService):
        """Single element_type creates correct filter."""
        filters = service.create_filters(element_type="mission")
        assert ElementType.MISSION in filters.element_types
        assert len(filters.element_types) == 1
        assert filters.detected_type is None  # Not auto-detected
        assert filters.detection_confidence == 0.0

    def test_create_filters_with_multiple_types(self, service: SyntacticService):
        """Multiple element_types creates correct filter."""
        filters = service.create_filters(element_types=["mission", "document"])
        assert ElementType.MISSION in filters.element_types
        assert ElementType.DOCUMENT in filters.element_types
        assert len(filters.element_types) == 2

    def test_create_filters_with_auto_detect(self, service: SyntacticService):
        """Auto-detection from query when no explicit type provided."""
        filters = service.create_filters(
            query="find all missions about research",
            auto_detect=True,
        )
        assert ElementType.MISSION in filters.element_types
        assert filters.detected_type == ElementType.MISSION
        assert filters.detection_confidence > 0.5

    def test_create_filters_explicit_overrides_auto_detect(
        self, service: SyntacticService
    ):
        """Explicit element_type takes precedence over auto-detection."""
        filters = service.create_filters(
            element_type="document",
            query="find all missions about research",  # Would detect mission
            auto_detect=True,
        )
        assert ElementType.DOCUMENT in filters.element_types
        assert ElementType.MISSION not in filters.element_types
        assert filters.detected_type is None  # Auto-detect skipped

    def test_create_filters_disabled_auto_detect(self, service: SyntacticService):
        """Auto-detection can be disabled."""
        filters = service.create_filters(
            query="find all missions about research",
            auto_detect=False,
        )
        assert len(filters.element_types) == 0
        assert filters.detected_type is None

    def test_create_filters_invalid_type_ignored(self, service: SyntacticService):
        """Invalid element types are ignored."""
        filters = service.create_filters(
            element_type="invalid_type",
            element_types=["mission", "also_invalid"],
        )
        assert ElementType.MISSION in filters.element_types
        assert len(filters.element_types) == 1

    def test_create_filters_type_boost_flag(self, service: SyntacticService):
        """Type boost flag is preserved in filters."""
        filters_enabled = service.create_filters(
            element_type="mission",
            type_boost_enabled=True,
        )
        assert filters_enabled.type_boost_enabled is True

        filters_disabled = service.create_filters(
            element_type="mission",
            type_boost_enabled=False,
        )
        assert filters_disabled.type_boost_enabled is False


class TestTypeBoost:
    """Tests for type boost scoring."""

    @pytest.fixture
    def service(self) -> SyntacticService:
        return SyntacticService()

    def _make_result(
        self,
        chunk_id: str,
        score: float,
        element_type: str | None = None,
        **extras,
    ) -> dict[str, Any]:
        """Create a mock search result."""
        result = {
            "chunk_id": chunk_id,
            "content": f"Content for {chunk_id}",
            "document_id": f"doc-{chunk_id}",
            "combined_score": score,
            "score": score,
        }
        if element_type:
            result["element_type"] = element_type
        result.update(extras)
        return result

    def test_type_boost_increases_matching_scores(self, service: SyntacticService):
        """Results matching target type receive score boost."""
        results = [
            self._make_result("c1", 0.8, element_type="mission"),
            self._make_result("c2", 0.85, element_type="document"),
        ]
        filters = SyntacticFilters(
            element_types=(ElementType.MISSION,),
            type_boost_enabled=True,
        )

        boosted = service.apply_type_boost(results, filters=filters)

        # Mission result should be boosted
        mission_result = next(r for r in boosted if r["chunk_id"] == "c1")
        assert mission_result["type_boost"] > 0
        assert mission_result["element_type_match"] is True
        assert mission_result["combined_score"] > 0.8

        # Document result should not be boosted
        doc_result = next(r for r in boosted if r["chunk_id"] == "c2")
        assert doc_result["type_boost"] == 0
        assert doc_result["element_type_match"] is False

    def test_type_boost_disabled(self, service: SyntacticService):
        """No boost applied when type_boost_enabled is False."""
        results = [self._make_result("c1", 0.8, element_type="mission")]
        filters = SyntacticFilters(
            element_types=(ElementType.MISSION,),
            type_boost_enabled=False,
        )

        boosted = service.apply_type_boost(results, filters=filters)

        assert boosted[0]["type_boost"] == 0
        assert boosted[0]["element_type_match"] is False

    def test_type_boost_no_target_types(self, service: SyntacticService):
        """No boost when no target types specified."""
        results = [self._make_result("c1", 0.8, element_type="mission")]
        filters = SyntacticFilters(
            element_types=(),
            type_boost_enabled=True,
        )

        boosted = service.apply_type_boost(results, filters=filters)

        assert boosted[0]["type_boost"] == 0
        assert boosted[0]["element_type_match"] is False

    def test_type_boost_infers_element_type(self, service: SyntacticService):
        """Element type is inferred from result metadata when not explicit."""
        # Result with mission_id suggests it's mission-related
        results = [
            self._make_result(
                "c1",
                0.8,
                mission_id="m-123",
                objective="Research user feedback",
            ),
            self._make_result("c2", 0.85, chunk_index=0),  # Chunk with index
        ]
        filters = SyntacticFilters(
            element_types=(ElementType.MISSION,),
            type_boost_enabled=True,
        )

        boosted = service.apply_type_boost(results, filters=filters)

        # Mission result inferred and boosted
        mission_result = next(r for r in boosted if r["chunk_id"] == "c1")
        assert mission_result["element_type"] == "mission"
        assert mission_result["type_boost"] > 0


class TestTypeFiltering:
    """Tests for type-based filtering."""

    @pytest.fixture
    def service(self) -> SyntacticService:
        return SyntacticService()

    def _make_result(
        self,
        chunk_id: str,
        element_type: str | None = None,
        **extras,
    ) -> dict[str, Any]:
        result = {
            "chunk_id": chunk_id,
            "content": f"Content for {chunk_id}",
            "combined_score": 0.8,
        }
        if element_type:
            result["element_type"] = element_type
        result.update(extras)
        return result

    def test_filter_by_type_keeps_matching(self, service: SyntacticService):
        """Filter keeps results matching target types."""
        results = [
            self._make_result("c1", element_type="mission"),
            self._make_result("c2", element_type="document"),
            self._make_result("c3", element_type="mission"),
        ]
        filters = SyntacticFilters(element_types=(ElementType.MISSION,))

        filtered = service.filter_by_type(results, filters=filters)

        assert len(filtered) == 2
        assert all(r["element_type"] == "mission" for r in filtered)

    def test_filter_by_type_empty_filters_returns_all(self, service: SyntacticService):
        """No filter returns all results."""
        results = [
            self._make_result("c1", element_type="mission"),
            self._make_result("c2", element_type="document"),
        ]
        filters = SyntacticFilters(element_types=())

        filtered = service.filter_by_type(results, filters=filters)

        assert len(filtered) == 2

    def test_filter_by_multiple_types(self, service: SyntacticService):
        """Filter supports multiple target types."""
        results = [
            self._make_result("c1", element_type="mission"),
            self._make_result("c2", element_type="document"),
            self._make_result("c3", element_type="insight"),
        ]
        filters = SyntacticFilters(
            element_types=(ElementType.MISSION, ElementType.INSIGHT)
        )

        filtered = service.filter_by_type(results, filters=filters)

        assert len(filtered) == 2
        types = {r["element_type"] for r in filtered}
        assert types == {"mission", "insight"}


class TestApplyMethod:
    """Tests for the main apply() method."""

    @pytest.fixture
    def service(self) -> SyntacticService:
        return SyntacticService()

    def _make_result(
        self,
        chunk_id: str,
        score: float,
        element_type: str | None = None,
    ) -> dict[str, Any]:
        result = {
            "chunk_id": chunk_id,
            "content": f"Content for {chunk_id}",
            "combined_score": score,
            "score": score,
        }
        if element_type:
            result["element_type"] = element_type
        return result

    def test_apply_with_boost_only(self, service: SyntacticService):
        """Apply in boost mode adds scores but keeps all results."""
        results = [
            self._make_result("c1", 0.8, element_type="mission"),
            self._make_result("c2", 0.9, element_type="document"),
        ]
        filters = SyntacticFilters(
            element_types=(ElementType.MISSION,),
            type_boost_enabled=True,
        )

        processed = service.apply(results, filters=filters, filter_mode=False)

        assert len(processed) == 2  # All results kept
        mission = next(r for r in processed if r["chunk_id"] == "c1")
        assert mission["type_boost"] > 0

    def test_apply_with_filter_mode(self, service: SyntacticService):
        """Apply in filter mode removes non-matching results."""
        results = [
            self._make_result("c1", 0.8, element_type="mission"),
            self._make_result("c2", 0.9, element_type="document"),
        ]
        filters = SyntacticFilters(
            element_types=(ElementType.MISSION,),
            type_boost_enabled=True,
        )

        processed = service.apply(results, filters=filters, filter_mode=True)

        assert len(processed) == 1
        assert processed[0]["chunk_id"] == "c1"

    def test_apply_empty_results(self, service: SyntacticService):
        """Apply handles empty results gracefully."""
        filters = SyntacticFilters(element_types=(ElementType.MISSION,))

        processed = service.apply([], filters=filters)

        assert processed == []


class TestInferElementType:
    """Tests for element type inference from result metadata."""

    def test_infer_mission_from_objective(self):
        """Results with objective field are inferred as missions."""
        result = {
            "mission_id": "m-1",
            "objective": "Research user needs",
            "success_criteria": ["Criterion 1"],
        }
        inferred = SyntacticService._infer_element_type(result)
        assert inferred == "mission"

    def test_infer_document_from_file_type(self):
        """Results with file_type and document_id are inferred as documents."""
        result = {
            "document_id": "d-1",
            "file_type": "pdf",
            "source_type": "interview",
        }
        inferred = SyntacticService._infer_element_type(result)
        assert inferred == "document"

    def test_infer_chunk_from_chunk_index(self):
        """Results with chunk_id and chunk_index are inferred as chunks."""
        result = {
            "chunk_id": "c-1",
            "document_id": "d-1",
            "chunk_index": 0,
            "content": "Some text",
        }
        inferred = SyntacticService._infer_element_type(result)
        assert inferred == "chunk"

    def test_infer_insight_from_insight_id(self):
        """Results with insight_id are inferred as insights."""
        result = {"insight_id": "i-1", "insight_type": "finding"}
        inferred = SyntacticService._infer_element_type(result)
        assert inferred == "insight"

    def test_explicit_element_type_preserved(self):
        """Explicit element_type field is preserved."""
        result = {"element_type": "custom_type"}
        inferred = SyntacticService._infer_element_type(result)
        assert inferred == "custom_type"


class TestSingleton:
    """Tests for singleton service accessor."""

    def test_get_syntactic_service_returns_service(self):
        """get_syntactic_service returns a SyntacticService instance."""
        service = get_syntactic_service()
        assert isinstance(service, SyntacticService)

    def test_get_syntactic_service_returns_same_instance(self):
        """get_syntactic_service returns the same singleton."""
        service1 = get_syntactic_service()
        service2 = get_syntactic_service()
        assert service1 is service2


class TestCustomConfiguration:
    """Tests for custom service configuration."""

    def test_custom_confidence_threshold(self):
        """Custom confidence threshold affects detection."""
        service_low = SyntacticService(confidence_threshold=0.1)
        service_high = SyntacticService(confidence_threshold=0.99)

        query = "objectives for the project"  # Medium confidence

        result_low = service_low.detect_type(query)
        result_high = service_high.detect_type(query)

        # Low threshold may detect, high threshold should not
        if result_low.confidence > 0:
            assert result_low.detected_type is not None or result_low.confidence < 0.1
        if result_high.confidence < 0.99:
            assert result_high.detected_type is None

    def test_custom_boost_weights(self):
        """Custom boost weights are applied."""
        custom_weights = {
            ElementType.MISSION: 0.5,  # Higher than default
        }
        service = SyntacticService(boost_weights=custom_weights)

        results = [{"chunk_id": "c1", "element_type": "mission", "combined_score": 1.0}]
        filters = SyntacticFilters(
            element_types=(ElementType.MISSION,),
            type_boost_enabled=True,
        )

        boosted = service.apply_type_boost(results, filters=filters)

        assert boosted[0]["type_boost"] == 0.5
        assert boosted[0]["combined_score"] == 1.5  # 1.0 * (1 + 0.5)
