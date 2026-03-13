"""Unit tests for the PEDR pragmatic layer (intent classification and routing)."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.pedr.pragmatic import (
    PragmaticFilters,
    PragmaticService,
    QueryIntent,
    get_pragmatic_service,
)


class TestQueryIntent:
    """Tests for QueryIntent enum."""

    def test_all_intents_available(self):
        """All expected intents are available."""
        intents = [e.value for e in QueryIntent]
        assert "search" in intents
        assert "create" in intents
        assert "update" in intents
        assert "delete" in intents
        assert "execute" in intents
        assert len(intents) == 5

    def test_enum_string_conversion(self):
        """Intent enums convert to expected strings."""
        assert QueryIntent.SEARCH.value == "search"
        assert QueryIntent.CREATE.value == "create"
        assert QueryIntent.UPDATE.value == "update"
        assert QueryIntent.DELETE.value == "delete"
        assert QueryIntent.EXECUTE.value == "execute"


class TestIntentClassification:
    """Tests for query intent classification."""

    @pytest.fixture
    def service(self) -> PragmaticService:
        return PragmaticService()

    # Search intent tests (READ operations)
    @pytest.mark.parametrize(
        "query,expected_confidence_min",
        [
            ("find documents about user research", 0.9),
            ("show me the latest insights", 0.9),
            ("what is the status of the project?", 0.9),
            ("where can I find the API docs?", 0.9),
            ("list all missions for sprint 12", 0.9),
            ("get the research findings", 0.9),
            ("search for pricing feedback", 0.9),
            ("how do I configure authentication?", 0.85),
            ("which documents contain user feedback?", 0.85),
            ("research on competitive analysis", 0.9),
            ("tell me about the onboarding flow", 0.8),
            ("who was interviewed last week?", 0.8),
            ("when did we complete the analysis?", 0.75),
            ("why is the conversion rate dropping?", 0.75),
            ("what does the data say about churn?", 0.75),
        ],
    )
    def test_detect_search_intent(
        self,
        service: PragmaticService,
        query: str,
        expected_confidence_min: float,
    ):
        """Search/read queries are classified correctly."""
        result = service.classify_intent(query)
        assert result.intent == QueryIntent.SEARCH
        assert result.confidence >= expected_confidence_min
        assert result.is_action_query is False
        assert len(result.signals) > 0

    # Create intent tests
    @pytest.mark.parametrize(
        "query,expected_confidence_min",
        [
            ("create a new project", 0.9),
            ("add a document to the collection", 0.9),
            ("make a new mission for research", 0.9),
            ("new collection for user feedback", 0.9),
            ("start new research project", 0.9),
            ("upload a new document", 0.9),
            ("generate a report from findings", 0.85),
            ("build a summary of insights", 0.85),
            ("initialize a new workspace", 0.75),
        ],
    )
    def test_detect_create_intent(
        self,
        service: PragmaticService,
        query: str,
        expected_confidence_min: float,
    ):
        """Create queries are classified correctly."""
        result = service.classify_intent(query)
        assert result.intent == QueryIntent.CREATE
        assert result.confidence >= expected_confidence_min
        assert result.is_action_query is True

    # Update intent tests
    @pytest.mark.parametrize(
        "query,expected_confidence_min",
        [
            ("update the project description", 0.9),
            ("edit the document metadata", 0.9),
            ("modify the mission objective", 0.9),
            ("change the project status", 0.9),
            ("rename the collection", 0.9),
            ("revise the research plan", 0.9),
            ("fix the typo in the summary", 0.85),
            ("correct the date in the report", 0.85),
            ("adjust the success criteria", 0.85),
            ("make changes to the document", 0.8),
        ],
    )
    def test_detect_update_intent(
        self,
        service: PragmaticService,
        query: str,
        expected_confidence_min: float,
    ):
        """Update queries are classified correctly."""
        result = service.classify_intent(query)
        assert result.intent == QueryIntent.UPDATE
        assert result.confidence >= expected_confidence_min
        assert result.is_action_query is True

    # Delete intent tests
    @pytest.mark.parametrize(
        "query,expected_confidence_min",
        [
            ("delete the old project", 0.9),
            ("remove the document from collection", 0.9),
            ("erase the outdated insights", 0.9),
            ("archive the completed mission", 0.85),
            ("discard the draft report", 0.85),
            ("purge old data", 0.85),
            ("trash the failed uploads", 0.85),
            ("get rid of duplicate entries", 0.8),
        ],
    )
    def test_detect_delete_intent(
        self,
        service: PragmaticService,
        query: str,
        expected_confidence_min: float,
    ):
        """Delete queries are classified correctly."""
        result = service.classify_intent(query)
        assert result.intent == QueryIntent.DELETE
        assert result.confidence >= expected_confidence_min
        assert result.is_action_query is True

    # Execute intent tests
    @pytest.mark.parametrize(
        "query,expected_confidence_min",
        [
            ("run the analysis on documents", 0.9),
            ("execute the mission", 0.9),
            ("trigger the sync process", 0.9),
            ("start the research workflow", 0.9),
            ("launch the batch processing", 0.9),
            ("activate the pipeline", 0.9),
            ("submit the report for review", 0.85),
            ("process the uploaded files", 0.85),
            ("perform the data analysis", 0.85),
            ("synthesize the research findings", 0.85),
            ("analyze the document data", 0.85),
        ],
    )
    def test_detect_execute_intent(
        self,
        service: PragmaticService,
        query: str,
        expected_confidence_min: float,
    ):
        """Execute queries are classified correctly."""
        result = service.classify_intent(query)
        assert result.intent == QueryIntent.EXECUTE
        assert result.confidence >= expected_confidence_min
        assert result.is_action_query is True

    def test_empty_query_defaults_to_search(self, service: PragmaticService):
        """Empty queries default to search intent."""
        result = service.classify_intent("")
        assert result.intent == QueryIntent.SEARCH
        assert result.confidence == 0.5
        assert result.is_action_query is False

    def test_whitespace_query_defaults_to_search(self, service: PragmaticService):
        """Whitespace-only queries default to search."""
        result = service.classify_intent("   ")
        assert result.intent == QueryIntent.SEARCH
        assert result.is_action_query is False

    def test_generic_query_defaults_to_search(self, service: PragmaticService):
        """Generic queries without clear intent default to search."""
        result = service.classify_intent("user feedback")
        assert result.intent == QueryIntent.SEARCH
        # Should have default signal
        assert any("default" in s for s in result.signals)

    def test_question_mark_indicates_search(self, service: PragmaticService):
        """Queries ending with question mark suggest search intent."""
        result = service.classify_intent("user feedback?")
        assert result.intent == QueryIntent.SEARCH
        assert result.confidence >= 0.7

    def test_signals_contain_pattern_info(self, service: PragmaticService):
        """Detection signals include pattern match details."""
        result = service.classify_intent("find all documents about research")
        assert result.signals
        for signal in result.signals:
            parts = signal.split(":")
            assert len(parts) >= 2


class TestPragmaticFilters:
    """Tests for filter creation."""

    @pytest.fixture
    def service(self) -> PragmaticService:
        return PragmaticService()

    def test_create_filters_search_intent(self, service: PragmaticService):
        """Search intent creates correct filter configuration."""
        filters = service.create_filters(query="find documents about research")
        assert filters.intent == QueryIntent.SEARCH
        assert filters.confidence > 0.5
        assert filters.is_action_query is False
        assert filters.route_to_search is True
        assert filters.route_to_action_handler is False

    def test_create_filters_create_intent(self, service: PragmaticService):
        """Create intent creates correct filter configuration."""
        filters = service.create_filters(query="create a new project")
        assert filters.intent == QueryIntent.CREATE
        assert filters.is_action_query is True
        assert filters.route_to_search is False
        assert filters.route_to_action_handler is True

    def test_create_filters_intent_boost_flag(self, service: PragmaticService):
        """Intent boost flag is preserved in filters."""
        filters_enabled = service.create_filters(
            query="find documents",
            intent_boost_enabled=True,
        )
        assert filters_enabled.intent_boost_enabled is True

        filters_disabled = service.create_filters(
            query="find documents",
            intent_boost_enabled=False,
        )
        assert filters_disabled.intent_boost_enabled is False


class TestIntentBoost:
    """Tests for intent-based result boosting."""

    @pytest.fixture
    def service(self) -> PragmaticService:
        return PragmaticService()

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

    def test_search_intent_boosts_insights(self, service: PragmaticService):
        """Search intent boosts insights and research artifacts."""
        results = [
            self._make_result("c1", 0.8, element_type="insight"),
            self._make_result("c2", 0.85, element_type="document"),
            self._make_result("c3", 0.75, element_type="chunk"),
        ]
        filters = PragmaticFilters(
            intent=QueryIntent.SEARCH,
            confidence=0.9,
            is_action_query=False,
            intent_boost_enabled=True,
            route_to_search=True,
            route_to_action_handler=False,
        )

        boosted = service.apply_intent_boost(results, filters=filters)

        # Insight should get the highest boost
        insight = next(r for r in boosted if r["chunk_id"] == "c1")
        document = next(r for r in boosted if r["chunk_id"] == "c2")
        chunk = next(r for r in boosted if r["chunk_id"] == "c3")

        assert insight["intent_boost"] >= document["intent_boost"]
        assert document["intent_boost"] >= chunk["intent_boost"]
        assert insight["query_intent"] == "search"

    def test_execute_intent_boosts_missions(self, service: PragmaticService):
        """Execute intent boosts missions."""
        results = [
            self._make_result("c1", 0.8, element_type="mission"),
            self._make_result("c2", 0.85, element_type="document"),
        ]
        filters = PragmaticFilters(
            intent=QueryIntent.EXECUTE,
            confidence=0.9,
            is_action_query=True,
            intent_boost_enabled=True,
            route_to_search=False,
            route_to_action_handler=True,
        )

        boosted = service.apply_intent_boost(results, filters=filters)

        mission = next(r for r in boosted if r["chunk_id"] == "c1")
        document = next(r for r in boosted if r["chunk_id"] == "c2")

        assert mission["intent_boost"] > document["intent_boost"]
        assert mission["combined_score"] > 0.8  # Score increased

    def test_create_intent_no_boost(self, service: PragmaticService):
        """Create intent doesn't boost search results (it's an action)."""
        results = [
            self._make_result("c1", 0.8, element_type="document"),
        ]
        filters = PragmaticFilters(
            intent=QueryIntent.CREATE,
            confidence=0.9,
            is_action_query=True,
            intent_boost_enabled=True,
            route_to_search=False,
            route_to_action_handler=True,
        )

        boosted = service.apply_intent_boost(results, filters=filters)

        # CREATE intent has empty boost weights
        assert boosted[0]["intent_boost"] == 0.0

    def test_intent_boost_disabled(self, service: PragmaticService):
        """No boost applied when intent_boost_enabled is False."""
        results = [self._make_result("c1", 0.8, element_type="insight")]
        filters = PragmaticFilters(
            intent=QueryIntent.SEARCH,
            confidence=0.9,
            is_action_query=False,
            intent_boost_enabled=False,
            route_to_search=True,
            route_to_action_handler=False,
        )

        boosted = service.apply_intent_boost(results, filters=filters)

        assert boosted[0]["intent_boost"] == 0.0
        assert boosted[0]["combined_score"] == 0.8  # Unchanged

    def test_intent_boost_annotates_query_intent(self, service: PragmaticService):
        """Results are annotated with query intent."""
        results = [self._make_result("c1", 0.8)]
        filters = PragmaticFilters(
            intent=QueryIntent.DELETE,
            confidence=0.9,
            is_action_query=True,
            intent_boost_enabled=True,
            route_to_search=False,
            route_to_action_handler=True,
        )

        boosted = service.apply_intent_boost(results, filters=filters)

        assert boosted[0]["query_intent"] == "delete"


class TestApplyMethod:
    """Tests for the main apply() method."""

    @pytest.fixture
    def service(self) -> PragmaticService:
        return PragmaticService()

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

    def test_apply_processes_results(self, service: PragmaticService):
        """Apply processes results with intent boost."""
        results = [
            self._make_result("c1", 0.8, element_type="insight"),
            self._make_result("c2", 0.9, element_type="document"),
        ]
        filters = PragmaticFilters(
            intent=QueryIntent.SEARCH,
            confidence=0.9,
            is_action_query=False,
            intent_boost_enabled=True,
            route_to_search=True,
            route_to_action_handler=False,
        )

        processed = service.apply(results, filters=filters)

        assert len(processed) == 2
        assert all("intent_boost" in r for r in processed)
        assert all("query_intent" in r for r in processed)

    def test_apply_empty_results(self, service: PragmaticService):
        """Apply handles empty results gracefully."""
        filters = PragmaticFilters(
            intent=QueryIntent.SEARCH,
            confidence=0.9,
            is_action_query=False,
            intent_boost_enabled=True,
            route_to_search=True,
            route_to_action_handler=False,
        )

        processed = service.apply([], filters=filters)

        assert processed == []


class TestResultTypeInference:
    """Tests for result type inference from metadata."""

    @pytest.fixture
    def service(self) -> PragmaticService:
        return PragmaticService()

    def test_infer_insight_from_element_type(self, service: PragmaticService):
        """Explicit insight element_type is recognized."""
        result = {"element_type": "insight"}
        inferred = service._infer_result_type(result)
        assert inferred == "insight"

    def test_infer_mission_from_element_type(self, service: PragmaticService):
        """Explicit mission element_type is recognized."""
        result = {"element_type": "mission"}
        inferred = service._infer_result_type(result)
        assert inferred == "mission"

    def test_infer_from_insight_id(self, service: PragmaticService):
        """Insight inferred from insight_id field."""
        result = {"insight_id": "i-1", "insight_type": "finding"}
        inferred = service._infer_result_type(result)
        assert inferred == "insight"

    def test_infer_mission_from_metadata(self, service: PragmaticService):
        """Mission inferred from mission_id with objective."""
        result = {
            "mission_id": "m-1",
            "objective": "Research user needs",
            "success_criteria": ["Criterion 1"],
        }
        inferred = service._infer_result_type(result)
        assert inferred == "mission"

    def test_infer_document_from_document_id(self, service: PragmaticService):
        """Document inferred from document_id without chunk_id."""
        result = {"document_id": "d-1", "file_name": "report.pdf"}
        inferred = service._infer_result_type(result)
        assert inferred == "document"

    def test_infer_chunk_from_chunk_id(self, service: PragmaticService):
        """Chunk inferred from chunk_id."""
        result = {"chunk_id": "c-1", "document_id": "d-1", "content": "text"}
        inferred = service._infer_result_type(result)
        assert inferred == "chunk"

    def test_infer_returns_none_for_unknown(self, service: PragmaticService):
        """Unknown results return None."""
        result = {"some_field": "value"}
        inferred = service._infer_result_type(result)
        assert inferred is None


class TestSingleton:
    """Tests for singleton service accessor."""

    def test_get_pragmatic_service_returns_service(self):
        """get_pragmatic_service returns a PragmaticService instance."""
        service = get_pragmatic_service()
        assert isinstance(service, PragmaticService)

    def test_get_pragmatic_service_returns_same_instance(self):
        """get_pragmatic_service returns the same singleton."""
        service1 = get_pragmatic_service()
        service2 = get_pragmatic_service()
        assert service1 is service2


class TestCustomConfiguration:
    """Tests for custom service configuration."""

    def test_custom_confidence_threshold(self):
        """Custom confidence threshold affects classification."""
        service_high = PragmaticService(confidence_threshold=0.99)

        # Low confidence pattern should fall back to default search
        result = service_high.classify_intent("maybe search for something")
        assert result.intent == QueryIntent.SEARCH  # Default fallback

    def test_custom_boost_weights(self):
        """Custom boost weights are applied."""
        custom_weights = {
            QueryIntent.SEARCH: {
                "insight": 0.5,  # Higher than default
            },
        }
        service = PragmaticService(boost_weights=custom_weights)

        results = [{"chunk_id": "c1", "element_type": "insight", "combined_score": 1.0}]
        filters = PragmaticFilters(
            intent=QueryIntent.SEARCH,
            confidence=0.9,
            is_action_query=False,
            intent_boost_enabled=True,
            route_to_search=True,
            route_to_action_handler=False,
        )

        boosted = service.apply_intent_boost(results, filters=filters)

        assert boosted[0]["intent_boost"] == 0.5
        assert boosted[0]["combined_score"] == 1.5  # 1.0 * (1 + 0.5)


class TestAccuracyValidation:
    """Test intent classification accuracy on a diverse set of queries.

    Target: 80%+ accuracy as per mission success criteria.
    """

    @pytest.fixture
    def service(self) -> PragmaticService:
        return PragmaticService()

    # Full accuracy test with labeled queries
    TEST_QUERIES = [
        # Search queries (25 examples)
        ("find user research documents", QueryIntent.SEARCH),
        ("show me all insights", QueryIntent.SEARCH),
        ("what is the project status?", QueryIntent.SEARCH),
        ("where are the API docs?", QueryIntent.SEARCH),
        ("list missions for sprint 12", QueryIntent.SEARCH),
        ("get the research findings", QueryIntent.SEARCH),
        ("search for pricing feedback", QueryIntent.SEARCH),
        ("how do I configure auth?", QueryIntent.SEARCH),
        ("which docs have user feedback?", QueryIntent.SEARCH),
        ("research on competitors", QueryIntent.SEARCH),
        ("tell me about onboarding", QueryIntent.SEARCH),
        ("who was interviewed?", QueryIntent.SEARCH),
        ("when did analysis complete?", QueryIntent.SEARCH),
        ("why is conversion dropping?", QueryIntent.SEARCH),
        ("what does data say?", QueryIntent.SEARCH),
        ("explore user pain points", QueryIntent.SEARCH),
        ("look for authentication issues", QueryIntent.SEARCH),
        ("display recent uploads", QueryIntent.SEARCH),
        ("describe the workflow", QueryIntent.SEARCH),
        ("explain the architecture", QueryIntent.SEARCH),
        ("investigate the bug", QueryIntent.SEARCH),
        ("show user feedback?", QueryIntent.SEARCH),
        ("what happened with churn?", QueryIntent.SEARCH),
        ("any research on pricing?", QueryIntent.SEARCH),
        ("documents related to UX?", QueryIntent.SEARCH),
        # Create queries (10 examples)
        ("create a new project", QueryIntent.CREATE),
        ("add document to collection", QueryIntent.CREATE),
        ("make a new mission", QueryIntent.CREATE),
        ("new collection for feedback", QueryIntent.CREATE),
        ("start a new research project", QueryIntent.CREATE),
        ("upload a document", QueryIntent.CREATE),
        ("generate a report", QueryIntent.CREATE),
        ("build a summary", QueryIntent.CREATE),
        ("set up workspace", QueryIntent.CREATE),
        ("initialize new project", QueryIntent.CREATE),
        # Update queries (10 examples)
        ("update project description", QueryIntent.UPDATE),
        ("edit document metadata", QueryIntent.UPDATE),
        ("modify mission objective", QueryIntent.UPDATE),
        ("change project status", QueryIntent.UPDATE),
        ("rename the collection", QueryIntent.UPDATE),
        ("revise research plan", QueryIntent.UPDATE),
        ("fix typo in summary", QueryIntent.UPDATE),
        ("correct the date", QueryIntent.UPDATE),
        ("adjust success criteria", QueryIntent.UPDATE),
        ("make changes to doc", QueryIntent.UPDATE),
        # Delete queries (10 examples)
        ("delete old project", QueryIntent.DELETE),
        ("remove from collection", QueryIntent.DELETE),
        ("erase outdated insights", QueryIntent.DELETE),
        ("archive completed mission", QueryIntent.DELETE),
        ("discard draft report", QueryIntent.DELETE),
        ("purge old data", QueryIntent.DELETE),
        ("trash failed uploads", QueryIntent.DELETE),
        ("get rid of duplicates", QueryIntent.DELETE),
        ("eliminate old entries", QueryIntent.DELETE),
        ("clear the cache", QueryIntent.DELETE),
        # Execute queries (10 examples)
        ("run the analysis", QueryIntent.EXECUTE),
        ("execute the mission", QueryIntent.EXECUTE),
        ("trigger sync process", QueryIntent.EXECUTE),
        ("start the workflow", QueryIntent.EXECUTE),
        ("launch batch processing", QueryIntent.EXECUTE),
        ("activate the pipeline", QueryIntent.EXECUTE),
        ("submit for review", QueryIntent.EXECUTE),
        ("process uploaded files", QueryIntent.EXECUTE),
        ("perform data analysis", QueryIntent.EXECUTE),
        ("synthesize findings", QueryIntent.EXECUTE),
    ]

    def test_overall_accuracy_above_80_percent(self, service: PragmaticService):
        """Intent classification achieves 80%+ accuracy on test set."""
        correct = 0
        total = len(self.TEST_QUERIES)
        failures = []

        for query, expected_intent in self.TEST_QUERIES:
            result = service.classify_intent(query)
            if result.intent == expected_intent:
                correct += 1
            else:
                failures.append(
                    f"'{query}': expected {expected_intent.value}, "
                    f"got {result.intent.value} (conf={result.confidence:.2f})"
                )

        accuracy = correct / total

        # Print failures for debugging
        if failures:
            print(f"\nFailed classifications ({len(failures)}):")
            for failure in failures[:10]:  # First 10 failures
                print(f"  - {failure}")

        print(f"\nAccuracy: {accuracy:.1%} ({correct}/{total})")

        assert accuracy >= 0.80, (
            f"Intent classification accuracy {accuracy:.1%} is below 80% target. Failed on {len(failures)} queries."
        )

    def test_search_intent_recall(self, service: PragmaticService):
        """Search intent has high recall (doesn't miss search queries)."""
        search_queries = [
            q for q, intent in self.TEST_QUERIES if intent == QueryIntent.SEARCH
        ]
        correct = sum(
            1
            for q in search_queries
            if service.classify_intent(q).intent == QueryIntent.SEARCH
        )
        recall = correct / len(search_queries)

        assert recall >= 0.85, f"Search recall {recall:.1%} is below 85%"

    def test_action_intent_precision(self, service: PragmaticService):
        """Action intents (CREATE/UPDATE/DELETE/EXECUTE) have high precision."""
        action_queries = [
            q
            for q, intent in self.TEST_QUERIES
            if intent
            in {
                QueryIntent.CREATE,
                QueryIntent.UPDATE,
                QueryIntent.DELETE,
                QueryIntent.EXECUTE,
            }
        ]

        correct = 0
        for query in action_queries:
            result = service.classify_intent(query)
            if result.is_action_query:
                correct += 1

        precision = correct / len(action_queries)

        assert precision >= 0.85, f"Action precision {precision:.1%} is below 85%"
