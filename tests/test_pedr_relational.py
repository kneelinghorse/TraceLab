"""Unit tests for the PEDR Relational Layer (Graph Context).

Tests cover:
- URN parsing
- Graph traversal mechanics
- Neighbor finding for each entity type
- Filtering by entity types and relation types
- Result enrichment

Note: These are pure unit tests that don't require database access.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

# Note: This file is listed in conftest.py skip_patterns to skip DB reset
from app.services.pedr.relational import (
    RelationType,
    EntityType,
    RelatedEntity,
    GraphExpansionResult,
    RelationalService,
)


# ==============================================================================
# URN Parsing Tests
# ==============================================================================

class TestURNParsing:
    """Tests for URN parsing functionality."""

    def test_parse_valid_urn(self):
        """Valid URN is parsed correctly."""
        service = RelationalService()

        entity_type, entity_id = service.parse_urn("urn:research:chunk:abc123")
        assert entity_type == EntityType.CHUNK
        assert entity_id == "abc123"

    def test_parse_all_entity_types(self):
        """All entity types are parsed correctly."""
        service = RelationalService()

        test_cases = [
            ("urn:research:project:p1", EntityType.PROJECT),
            ("urn:research:document:d1", EntityType.DOCUMENT),
            ("urn:research:chunk:c1", EntityType.CHUNK),
            ("urn:research:mission:m1", EntityType.MISSION),
            ("urn:research:insight:i1", EntityType.INSIGHT),
            ("urn:research:report:r1", EntityType.REPORT),
        ]

        for urn, expected_type in test_cases:
            entity_type, entity_id = service.parse_urn(urn)
            assert entity_type == expected_type, f"Failed for {urn}"

    def test_parse_invalid_urn_format(self):
        """Invalid URN format raises ValueError."""
        service = RelationalService()

        with pytest.raises(ValueError, match="Invalid URN format"):
            service.parse_urn("invalid:urn")

    def test_parse_wrong_prefix(self):
        """URN with wrong prefix raises ValueError."""
        service = RelationalService()

        with pytest.raises(ValueError, match="Invalid URN format"):
            service.parse_urn("urn:other:chunk:abc123")

    def test_parse_unknown_entity_type(self):
        """Unknown entity type raises ValueError."""
        service = RelationalService()

        with pytest.raises(ValueError, match="Unknown entity type"):
            service.parse_urn("urn:research:unknown:abc123")

    def test_parse_uuid_entity_id(self):
        """UUID entity IDs are parsed correctly."""
        service = RelationalService()
        test_uuid = "550e8400-e29b-41d4-a716-446655440000"

        entity_type, entity_id = service.parse_urn(f"urn:research:mission:{test_uuid}")
        assert entity_id == test_uuid


# ==============================================================================
# RelatedEntity Tests
# ==============================================================================

class TestRelatedEntity:
    """Tests for RelatedEntity data class."""

    def test_to_dict(self):
        """RelatedEntity converts to dict correctly."""
        entity = RelatedEntity(
            entity_type=EntityType.CHUNK,
            entity_id="chunk-123",
            relation_type=RelationType.CONTAINS,
            relation_direction="outbound",
            distance=1,
            content_preview="Some content preview...",
            metadata={"chunk_index": 5},
            urn="urn:research:chunk:chunk-123",
        )

        result = entity.to_dict()

        assert result["entity_type"] == "chunk"
        assert result["entity_id"] == "chunk-123"
        assert result["relation_type"] == "contains"
        assert result["relation_direction"] == "outbound"
        assert result["distance"] == 1
        assert result["content_preview"] == "Some content preview..."
        assert result["metadata"]["chunk_index"] == 5
        assert result["urn"] == "urn:research:chunk:chunk-123"

    def test_to_dict_minimal(self):
        """RelatedEntity with minimal fields converts correctly."""
        entity = RelatedEntity(
            entity_type=EntityType.PROJECT,
            entity_id="proj-1",
            relation_type=RelationType.BELONGS_TO,
            relation_direction="outbound",
            distance=2,
        )

        result = entity.to_dict()

        assert result["entity_type"] == "project"
        assert result["content_preview"] is None
        assert result["metadata"] == {}
        assert result["urn"] is None


# ==============================================================================
# GraphExpansionResult Tests
# ==============================================================================

class TestGraphExpansionResult:
    """Tests for GraphExpansionResult data class."""

    def test_to_dict(self):
        """GraphExpansionResult converts to dict correctly."""
        related = [
            RelatedEntity(
                entity_type=EntityType.DOCUMENT,
                entity_id="doc-1",
                relation_type=RelationType.BELONGS_TO,
                relation_direction="outbound",
                distance=1,
            ),
        ]

        result = GraphExpansionResult(
            source_urn="urn:research:chunk:c1",
            source_entity_type=EntityType.CHUNK,
            source_entity_id="c1",
            related_entities=related,
            total_found=1,
            expansion_depth=2,
        )

        result_dict = result.to_dict()

        assert result_dict["source_urn"] == "urn:research:chunk:c1"
        assert result_dict["source_entity_type"] == "chunk"
        assert result_dict["source_entity_id"] == "c1"
        assert len(result_dict["related_entities"]) == 1
        assert result_dict["total_found"] == 1
        assert result_dict["expansion_depth"] == 2


# ==============================================================================
# RelationalService Unit Tests
# ==============================================================================

class TestRelationalServiceFiltering:
    """Tests for filtering in RelationalService."""

    def test_include_types_filter(self):
        """include_types parameter filters results."""
        # Create mock neighbors that would be returned
        mock_neighbors = [
            RelatedEntity(
                entity_type=EntityType.DOCUMENT,
                entity_id="d1",
                relation_type=RelationType.BELONGS_TO,
                relation_direction="outbound",
                distance=1,
            ),
            RelatedEntity(
                entity_type=EntityType.CHUNK,
                entity_id="c1",
                relation_type=RelationType.CONTAINS,
                relation_direction="outbound",
                distance=1,
            ),
            RelatedEntity(
                entity_type=EntityType.INSIGHT,
                entity_id="i1",
                relation_type=RelationType.DERIVED_FROM,
                relation_direction="inbound",
                distance=1,
            ),
        ]

        service = RelationalService()

        # Mock the internal neighbor methods
        with patch.object(service, "_get_chunk_neighbors", return_value=mock_neighbors):
            result = service.get_related(
                "urn:research:chunk:test",
                max_depth=1,
                include_types=[EntityType.DOCUMENT],
            )

        # Should only include documents
        assert len(result.related_entities) == 1
        assert result.related_entities[0].entity_type == EntityType.DOCUMENT

    def test_exclude_types_filter(self):
        """exclude_types parameter filters results."""
        mock_neighbors = [
            RelatedEntity(
                entity_type=EntityType.DOCUMENT,
                entity_id="d1",
                relation_type=RelationType.BELONGS_TO,
                relation_direction="outbound",
                distance=1,
            ),
            RelatedEntity(
                entity_type=EntityType.CHUNK,
                entity_id="c1",
                relation_type=RelationType.SIBLING_OF,
                relation_direction="outbound",
                distance=1,
            ),
        ]

        service = RelationalService()

        with patch.object(service, "_get_chunk_neighbors", return_value=mock_neighbors):
            result = service.get_related(
                "urn:research:chunk:test",
                max_depth=1,
                exclude_types=[EntityType.CHUNK],
            )

        # Should exclude chunks
        assert len(result.related_entities) == 1
        assert result.related_entities[0].entity_type == EntityType.DOCUMENT

    def test_relation_types_filter(self):
        """relation_types parameter filters results."""
        mock_neighbors = [
            RelatedEntity(
                entity_type=EntityType.DOCUMENT,
                entity_id="d1",
                relation_type=RelationType.BELONGS_TO,
                relation_direction="outbound",
                distance=1,
            ),
            RelatedEntity(
                entity_type=EntityType.CHUNK,
                entity_id="c1",
                relation_type=RelationType.SIBLING_OF,
                relation_direction="outbound",
                distance=1,
            ),
        ]

        service = RelationalService()

        with patch.object(service, "_get_chunk_neighbors", return_value=mock_neighbors):
            result = service.get_related(
                "urn:research:chunk:test",
                max_depth=1,
                relation_types=[RelationType.BELONGS_TO],
            )

        # Should only include belongs_to relations
        assert len(result.related_entities) == 1
        assert result.related_entities[0].relation_type == RelationType.BELONGS_TO


class TestRelationalServiceLimits:
    """Tests for limits in RelationalService."""

    def test_limit_results(self):
        """limit parameter caps the number of results."""
        mock_neighbors = [
            RelatedEntity(
                entity_type=EntityType.CHUNK,
                entity_id=f"c{i}",
                relation_type=RelationType.SIBLING_OF,
                relation_direction="outbound",
                distance=1,
            )
            for i in range(20)
        ]

        service = RelationalService()

        with patch.object(service, "_get_chunk_neighbors", return_value=mock_neighbors):
            result = service.get_related(
                "urn:research:chunk:test",
                max_depth=1,
                limit=5,
            )

        assert len(result.related_entities) <= 5

    def test_max_depth_respected(self):
        """max_depth parameter limits traversal depth."""
        # First level neighbors
        level1_neighbors = [
            RelatedEntity(
                entity_type=EntityType.DOCUMENT,
                entity_id="d1",
                relation_type=RelationType.BELONGS_TO,
                relation_direction="outbound",
                distance=1,
            ),
        ]

        # Second level would return more
        level2_neighbors = [
            RelatedEntity(
                entity_type=EntityType.PROJECT,
                entity_id="p1",
                relation_type=RelationType.BELONGS_TO,
                relation_direction="outbound",
                distance=1,
            ),
            RelatedEntity(
                entity_type=EntityType.CHUNK,
                entity_id="c2",
                relation_type=RelationType.CONTAINS,
                relation_direction="outbound",
                distance=1,
            ),
        ]

        service = RelationalService()

        def mock_neighbors(session, entity_type, entity_id, **kwargs):
            if entity_type == EntityType.CHUNK:
                return level1_neighbors
            elif entity_type == EntityType.DOCUMENT:
                return level2_neighbors
            return []

        # With max_depth=1, should only get level 1
        with patch.object(service, "_get_neighbors", side_effect=mock_neighbors):
            result = service.get_related(
                "urn:research:chunk:test",
                max_depth=1,
                limit=50,
            )

        # Should only have the document from level 1
        assert len(result.related_entities) == 1
        assert result.related_entities[0].entity_type == EntityType.DOCUMENT


# ==============================================================================
# Enum Tests
# ==============================================================================

class TestRelationType:
    """Tests for RelationType enum."""

    def test_all_relation_types_exist(self):
        """All expected relation types are defined."""
        expected = {"belongs_to", "contains", "references", "derived_from", "sibling_of", "related_to"}
        actual = {r.value for r in RelationType}
        assert expected == actual


class TestEntityType:
    """Tests for EntityType enum."""

    def test_all_entity_types_exist(self):
        """All expected entity types are defined."""
        expected = {"project", "document", "chunk", "mission", "insight", "report"}
        actual = {e.value for e in EntityType}
        assert expected == actual


# ==============================================================================
# Singleton Tests
# ==============================================================================

class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_relational_service_singleton(self):
        """get_relational_service returns same instance."""
        from app.services.pedr.relational import get_relational_service
        import app.services.pedr.relational as relational_module

        # Reset singleton for test
        relational_module._relational_service = None

        service1 = get_relational_service()
        service2 = get_relational_service()

        assert service1 is service2

        # Cleanup
        relational_module._relational_service = None


# ==============================================================================
# Integration-style Tests (with mocked DB)
# ==============================================================================

class TestEnrichSearchResults:
    """Tests for search result enrichment."""

    def test_enrich_with_include_related_false(self):
        """Results unchanged when include_related is False."""
        service = RelationalService()

        results = [
            {"chunk_id": "c1", "content": "test", "urn": "urn:research:chunk:c1"},
        ]

        enriched = service.enrich_search_results(results, include_related=False)

        # Should be unchanged
        assert enriched == results
        assert "related_entities" not in enriched[0]

    def test_enrich_adds_related_entities(self):
        """Enrichment adds related_entities field."""
        service = RelationalService()

        mock_expansion = GraphExpansionResult(
            source_urn="urn:research:chunk:c1",
            source_entity_type=EntityType.CHUNK,
            source_entity_id="c1",
            related_entities=[
                RelatedEntity(
                    entity_type=EntityType.DOCUMENT,
                    entity_id="d1",
                    relation_type=RelationType.BELONGS_TO,
                    relation_direction="outbound",
                    distance=1,
                ),
            ],
            total_found=1,
            expansion_depth=1,
        )

        results = [
            {"chunk_id": "c1", "content": "test", "urn": "urn:research:chunk:c1"},
        ]

        with patch.object(service, "get_related", return_value=mock_expansion):
            enriched = service.enrich_search_results(
                results,
                include_related=True,
                max_related_per_result=5,
            )

        assert "related_entities" in enriched[0]
        assert len(enriched[0]["related_entities"]) == 1
        assert enriched[0]["related_entities"][0]["entity_type"] == "document"

    def test_enrich_handles_missing_urn(self):
        """Enrichment handles results without URN gracefully."""
        service = RelationalService()

        results = [
            {"chunk_id": "c1", "content": "test"},  # No URN
        ]

        # Should generate URN from chunk_id
        mock_protocol = MagicMock()
        mock_protocol.generate_urn.return_value = "urn:research:chunk:c1"
        service._semantic_protocol = mock_protocol

        mock_expansion = GraphExpansionResult(
            source_urn="urn:research:chunk:c1",
            source_entity_type=EntityType.CHUNK,
            source_entity_id="c1",
            related_entities=[],
            total_found=0,
            expansion_depth=1,
        )

        with patch.object(service, "get_related", return_value=mock_expansion):
            enriched = service.enrich_search_results(
                results,
                include_related=True,
            )

        assert "related_entities" in enriched[0]
        mock_protocol.generate_urn.assert_called_once_with("chunk", "c1")

    def test_enrich_handles_expansion_error(self):
        """Enrichment handles expansion errors gracefully."""
        service = RelationalService()

        results = [
            {"chunk_id": "c1", "content": "test", "urn": "urn:research:chunk:c1"},
        ]

        with patch.object(service, "get_related", side_effect=ValueError("Test error")):
            enriched = service.enrich_search_results(
                results,
                include_related=True,
            )

        # Should have empty related_entities, not raise
        assert enriched[0]["related_entities"] == []
