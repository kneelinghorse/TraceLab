"""Unit tests for the PEDR Semantic Protocol (The Namer).

Tests cover:
- URN generation: urn:research:{type}:{id} format
- Confidence scoring: Bayesian approach with evidence
- Criticality calculation: Weighted formula
- Manifest creation: Full protocol manifests
- Integration with manifest_transformer.py
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

import pytest

from app.services.pedr.semantic_protocol import (
    URN,
    URNGenerator,
    GovernanceMetadata,
    SemanticFeatures,
    ElementMetadata,
    ProtocolManifest,
    Edge,
    ConfidenceScorer,
    CriticalityCalculator,
    IntentResolver,
    SemanticVectorGenerator,
    SemanticProtocol,
    get_semantic_protocol,
    EntityType,
    SemanticIntent,
    PROTOCOL_VERSION,
    CRITICALITY_WEIGHTS,
    CONFIDENCE_PRIOR,
    fnv1a_64_hash,
)


# ==============================================================================
# URN Tests
# ==============================================================================

class TestURN:
    """Tests for URN data class and parsing."""

    def test_urn_str_format(self):
        """URN converts to expected string format."""
        urn = URN(entity_type="mission", entity_id="B12.1")
        assert str(urn) == "urn:research:mission:B12.1"

    def test_urn_with_version(self):
        """URN with version includes version in string."""
        urn = URN(entity_type="chunk", entity_id="doc123-chunk-5", version="3.2.0")
        assert str(urn) == "urn:research:chunk:doc123-chunk-5@3.2.0"

    def test_urn_parse_valid(self):
        """Valid URN string is parsed correctly."""
        urn = URN.parse("urn:research:mission:B12.1")
        assert urn is not None
        assert urn.entity_type == "mission"
        assert urn.entity_id == "B12.1"
        assert urn.version is None

    def test_urn_parse_with_version(self):
        """URN with version is parsed correctly."""
        urn = URN.parse("urn:research:document:abc123@3.2.0")
        assert urn is not None
        assert urn.entity_type == "document"
        assert urn.entity_id == "abc123"
        assert urn.version == "3.2.0"

    def test_urn_parse_invalid(self):
        """Invalid URN string returns None."""
        assert URN.parse("invalid") is None
        assert URN.parse("urn:other:mission:123") is None
        assert URN.parse("") is None

    def test_urn_create(self):
        """URN.create factory method works correctly."""
        urn = URN.create("mission", "B12.1")
        assert str(urn) == "urn:research:mission:B12.1"

        urn_with_version = URN.create(EntityType.DOCUMENT, "doc123", version="1.0")
        assert str(urn_with_version) == "urn:research:document:doc123@1.0"


class TestURNGenerator:
    """Tests for URNGenerator utility class."""

    def test_generate_basic(self):
        """Generator creates URNs with correct format."""
        urn = URNGenerator.generate("mission", "B12.1")
        assert str(urn) == "urn:research:mission:B12.1"

    def test_for_mission(self):
        """Mission URN helper works correctly."""
        urn = URNGenerator.for_mission("B12.1")
        assert str(urn) == "urn:research:mission:B12.1"

    def test_for_document(self):
        """Document URN helper works correctly."""
        urn = URNGenerator.for_document("abc123")
        assert str(urn) == "urn:research:document:abc123"

    def test_for_insight(self):
        """Insight URN helper works correctly."""
        urn = URNGenerator.for_insight("insight-456")
        assert str(urn) == "urn:research:insight:insight-456"

    def test_for_chunk(self):
        """Chunk URN helper creates correct compound ID."""
        urn = URNGenerator.for_chunk("doc123", 5)
        assert str(urn) == "urn:research:chunk:doc123-chunk-5"

    def test_for_project(self):
        """Project URN helper works correctly."""
        urn = URNGenerator.for_project("project-789")
        assert str(urn) == "urn:research:project:project-789"


# ==============================================================================
# Confidence Scoring Tests
# ==============================================================================

class TestConfidenceScorer:
    """Tests for Bayesian confidence scoring."""

    @pytest.fixture
    def scorer(self) -> ConfidenceScorer:
        return ConfidenceScorer()

    def test_prior_confidence(self, scorer: ConfidenceScorer):
        """Default prior is used when no evidence."""
        confidence = scorer.calculate({})
        # With no evidence, score should be below prior due to negative updates
        assert confidence < CONFIDENCE_PRIOR

    def test_all_evidence_high_confidence(self, scorer: ConfidenceScorer):
        """All evidence present results in high confidence."""
        evidence = {
            "has_purpose": True,
            "has_type": True,
            "has_governance": True,
            "has_requires": True,
            "has_provides": True,
            "has_quality_gates": True,
            "has_evidence": True,
            "has_synthesis": True,
        }
        confidence = scorer.calculate(evidence)
        assert confidence > 0.8
        assert confidence <= 1.0

    def test_partial_evidence(self, scorer: ConfidenceScorer):
        """Partial evidence gives medium confidence."""
        evidence = {
            "has_purpose": True,
            "has_type": True,
            "has_governance": False,
            "has_requires": False,
            "has_provides": False,
            "has_quality_gates": False,
            "has_evidence": False,
            "has_synthesis": False,
        }
        confidence = scorer.calculate(evidence)
        assert 0.25 < confidence < 0.7

    def test_no_evidence_low_confidence(self, scorer: ConfidenceScorer):
        """No evidence results in low confidence."""
        evidence = {
            "has_purpose": False,
            "has_type": False,
            "has_governance": False,
            "has_requires": False,
            "has_provides": False,
            "has_quality_gates": False,
            "has_evidence": False,
            "has_synthesis": False,
        }
        confidence = scorer.calculate(evidence)
        assert confidence < 0.2

    def test_score_manifest_with_purpose(self, scorer: ConfidenceScorer):
        """Manifest with purpose has higher confidence than empty."""
        data_with_purpose = {"purpose": "Research authentication patterns"}
        data_empty = {}

        score_with = scorer.score_manifest(data_with_purpose)
        score_empty = scorer.score_manifest(data_empty)

        assert score_with > score_empty

    def test_score_manifest_with_quality_gates(self, scorer: ConfidenceScorer):
        """Quality gates increase confidence significantly."""
        data_with_gates = {
            "quality_gates": {
                "research_statement": {"status": "pass"},
                "evidence_links": {"status": "pass"},
            }
        }
        data_without = {}

        score_with = scorer.score_manifest(data_with_gates)
        score_without = scorer.score_manifest(data_without)

        assert score_with > score_without


# ==============================================================================
# Criticality Calculation Tests
# ==============================================================================

class TestCriticalityCalculator:
    """Tests for criticality calculation with weighted formula."""

    @pytest.fixture
    def calculator(self) -> CriticalityCalculator:
        return CriticalityCalculator()

    def test_default_criticality(self, calculator: CriticalityCalculator):
        """Default values give medium criticality."""
        criticality = calculator.calculate()
        # impact=5 (0.5), visibility=0.5, pii=False (0), blast_radius=0
        # = 0.5*0.4 + 0.5*0.2 + 0*0.3 + 0*0.1 = 0.2 + 0.1 = 0.3
        assert 0.25 <= criticality <= 0.35

    def test_high_impact_high_criticality(self, calculator: CriticalityCalculator):
        """High impact increases criticality."""
        criticality = calculator.calculate(impact=10.0)
        assert criticality > 0.4

    def test_pii_increases_criticality(self, calculator: CriticalityCalculator):
        """PII handling significantly increases criticality."""
        without_pii = calculator.calculate(pii=False)
        with_pii = calculator.calculate(pii=True)

        assert with_pii > without_pii
        # PII adds 0.3 * 0.3 (pii weight) = 0.3
        assert with_pii - without_pii >= 0.25

    def test_many_dependents_increases_criticality(self, calculator: CriticalityCalculator):
        """Many dependents increase blast radius component."""
        without_deps = calculator.calculate(dependents=[])
        with_deps = calculator.calculate(dependents=[f"dep-{i}" for i in range(10)])

        assert with_deps > without_deps

    def test_max_criticality(self, calculator: CriticalityCalculator):
        """Maximum possible criticality is capped at 1.0."""
        criticality = calculator.calculate(
            impact=10.0,
            visibility=1.0,
            pii=True,
            dependents=[f"dep-{i}" for i in range(100)],
        )
        assert criticality <= 1.0
        assert criticality >= 0.9

    def test_min_criticality(self, calculator: CriticalityCalculator):
        """Minimum criticality is at least 0."""
        criticality = calculator.calculate(
            impact=0.0,
            visibility=0.0,
            pii=False,
            dependents=[],
        )
        assert criticality == 0.0

    def test_from_governance_metadata(self, calculator: CriticalityCalculator):
        """Calculate from GovernanceMetadata object."""
        governance = GovernanceMetadata(
            pii_handling=True,
            business_impact=8,
            user_visibility=0.9,
        )
        criticality = calculator.calculate_from_governance(governance)
        # High impact, high visibility, PII = high criticality
        assert criticality > 0.6


# ==============================================================================
# Intent Resolver Tests
# ==============================================================================

class TestIntentResolver:
    """Tests for semantic intent resolution."""

    @pytest.fixture
    def resolver(self) -> IntentResolver:
        return IntentResolver()

    def test_empty_purpose_returns_generic(self, resolver: IntentResolver):
        """Empty purpose returns GENERIC intent."""
        assert resolver.resolve("") == SemanticIntent.GENERIC
        assert resolver.resolve(None) == SemanticIntent.GENERIC

    @pytest.mark.parametrize(
        "purpose,expected_intent",
        [
            ("Create new user authentication flow", SemanticIntent.CREATE),
            ("Add document upload capability", SemanticIntent.CREATE),
            ("Submit research findings", SemanticIntent.CREATE),
            ("Read authentication patterns", SemanticIntent.READ),
            ("View user research findings", SemanticIntent.READ),
            ("Find related missions", SemanticIntent.READ),
            ("Update existing workflow", SemanticIntent.UPDATE),
            ("Edit mission objectives", SemanticIntent.UPDATE),
            ("Delete outdated documents", SemanticIntent.DELETE),
            ("Remove archived missions", SemanticIntent.DELETE),
            ("Execute analysis pipeline", SemanticIntent.EXECUTE),
            ("Run synthesis workflow", SemanticIntent.EXECUTE),
            ("Analyze user feedback", SemanticIntent.EXECUTE),
        ],
    )
    def test_intent_from_keywords(
        self,
        resolver: IntentResolver,
        purpose: str,
        expected_intent: SemanticIntent,
    ):
        """Intent is resolved from keywords in purpose."""
        assert resolver.resolve(purpose) == expected_intent

    def test_resolve_from_type_mission(self, resolver: IntentResolver):
        """Missions default to READ intent."""
        assert resolver.resolve_from_type("mission") == SemanticIntent.READ

    def test_resolve_from_type_document(self, resolver: IntentResolver):
        """Documents default to READ intent."""
        assert resolver.resolve_from_type("document") == SemanticIntent.READ

    def test_resolve_from_type_unknown(self, resolver: IntentResolver):
        """Unknown types default to GENERIC intent."""
        assert resolver.resolve_from_type("unknown") == SemanticIntent.GENERIC


# ==============================================================================
# Semantic Vector Generator Tests
# ==============================================================================

class TestSemanticVectorGenerator:
    """Tests for semantic vector generation."""

    @pytest.fixture
    def generator(self) -> SemanticVectorGenerator:
        return SemanticVectorGenerator()

    def test_empty_text_returns_empty(self, generator: SemanticVectorGenerator):
        """Empty text returns empty vector."""
        assert generator.generate("") == []
        assert generator.generate(None) == []

    def test_generates_term_weight_pairs(self, generator: SemanticVectorGenerator):
        """Vector contains term-weight pairs."""
        text = "user authentication security login"
        vector = generator.generate(text)

        assert len(vector) > 0
        for entry in vector:
            assert "term" in entry
            assert "weight" in entry
            assert isinstance(entry["term"], str)
            assert isinstance(entry["weight"], (int, float))

    def test_weights_are_normalized(self, generator: SemanticVectorGenerator):
        """Weights are normalized (unit vector)."""
        text = "authentication security patterns user login access"
        vector = generator.generate(text)

        # Sum of squares should be approximately 1 (unit vector)
        sum_squares = sum(entry["weight"] ** 2 for entry in vector)
        assert 0.99 <= sum_squares <= 1.01

    def test_stopwords_filtered(self, generator: SemanticVectorGenerator):
        """Common stopwords are filtered out."""
        text = "the user and the authentication in the system"
        vector = generator.generate(text)

        terms = [entry["term"] for entry in vector]
        assert "the" not in terms
        assert "and" not in terms
        assert "in" not in terms

    def test_from_manifest_data(self, generator: SemanticVectorGenerator):
        """Vector generated from manifest data fields."""
        data = {
            "purpose": "Research authentication patterns",
            "title": "User Login Security",
            "tags": ["security", "auth", "login"],
        }
        vector = generator.from_manifest_data(data)

        assert len(vector) > 0
        terms = [entry["term"] for entry in vector]
        assert "authentication" in terms or "security" in terms


# ==============================================================================
# Semantic Protocol Service Tests
# ==============================================================================

class TestSemanticProtocol:
    """Tests for main SemanticProtocol service."""

    @pytest.fixture
    def protocol(self) -> SemanticProtocol:
        return SemanticProtocol()

    def test_generate_urn(self, protocol: SemanticProtocol):
        """URN generation works through service."""
        urn = protocol.generate_urn("mission", "B12.1")
        assert urn == "urn:research:mission:B12.1"

    def test_calculate_confidence(self, protocol: SemanticProtocol):
        """Confidence calculation works through service."""
        data = {"purpose": "Test purpose", "quality_gates": {"test": {}}}
        confidence = protocol.calculate_confidence(data)
        assert 0.0 <= confidence <= 1.0

    def test_calculate_criticality(self, protocol: SemanticProtocol):
        """Criticality calculation works through service."""
        criticality = protocol.calculate_criticality(
            impact=8,
            visibility=0.8,
            pii=True,
        )
        assert 0.0 <= criticality <= 1.0
        assert criticality > 0.5  # High values should give high criticality

    def test_create_manifest_basic(self, protocol: SemanticProtocol):
        """Basic manifest creation with minimal data."""
        manifest = protocol.create_manifest(
            entity_id="test-123",
            entity_type="mission",
            data={"purpose": "Test mission"},
        )

        assert str(manifest.urn) == "urn:research:mission:test-123"
        assert manifest.version == PROTOCOL_VERSION
        assert manifest.element.element_type == "research.mission"
        assert manifest.semantics.purpose == "Test mission"
        assert 0.0 <= manifest.confidence <= 1.0
        assert 0.0 <= manifest.criticality <= 1.0

    def test_create_mission_manifest(self, protocol: SemanticProtocol):
        """Mission-specific manifest creation."""
        mission_data = {
            "missionId": "B12.1",
            "researchStatement": {
                "objective": "Research authentication patterns for enterprise users"
            },
            "tags": ["security", "auth"],
            "governance": {
                "businessImpact": 8,
            },
        }
        quality_gates = {
            "research_statement": {"status": "pass"},
            "evidence_links": {"status": "pass"},
        }

        manifest = protocol.create_mission_manifest(
            mission_id="B12.1",
            mission_data=mission_data,
            quality_gates=quality_gates,
            project_id="proj-123",
            status="complete",
        )

        assert str(manifest.urn) == "urn:research:mission:B12.1"
        assert "authentication" in manifest.semantics.purpose.lower()
        assert manifest.element.intent == SemanticIntent.READ
        # Confidence is based on evidence factors - with purpose, governance, and quality_gates
        assert manifest.confidence > 0.35
        assert "belongs_to" in manifest.relationships

    def test_create_document_manifest(self, protocol: SemanticProtocol):
        """Document manifest creation."""
        manifest = protocol.create_document_manifest(
            document_id="doc-456",
            name="User Interview Transcript",
            content="Interview with user about login experience...",
            file_type="md",
            project_id="proj-123",
            chunk_count=5,
        )

        assert str(manifest.urn) == "urn:research:document:doc-456"
        assert manifest.element.element_type == "research.document"
        assert manifest.element.intent == SemanticIntent.READ

    def test_create_insight_manifest(self, protocol: SemanticProtocol):
        """Insight manifest creation."""
        manifest = protocol.create_insight_manifest(
            insight_id="insight-789",
            title="Users prefer passwordless authentication",
            content="Based on 12 interviews, users strongly prefer...",
            insight_type="finding",
            validated=True,
            project_id="proj-123",
        )

        assert str(manifest.urn) == "urn:research:insight:insight-789"
        assert manifest.element.element_type == "research.insight"
        assert manifest.governance.business_impact == 7  # Validated gets higher impact

    def test_create_chunk_manifest(self, protocol: SemanticProtocol):
        """Chunk manifest creation."""
        manifest = protocol.create_chunk_manifest(
            document_id="doc-456",
            chunk_index=3,
            content="This chunk contains important research findings...",
        )

        assert str(manifest.urn) == "urn:research:chunk:doc-456-chunk-3"
        assert manifest.element.element_type == "research.chunk"
        assert "part_of" in manifest.relationships

    def test_manifest_to_dict(self, protocol: SemanticProtocol):
        """Manifest can be serialized to dictionary."""
        manifest = protocol.create_manifest(
            entity_id="test",
            entity_type="mission",
            data={"purpose": "Test"},
        )
        result = manifest.to_dict()

        assert isinstance(result, dict)
        assert "urn" in result
        assert "version" in result
        assert "element" in result
        assert "semantics" in result
        assert "governance" in result
        assert "confidence" in result
        assert "criticality" in result

    def test_fnv1a_hash_matches_js(self):
        """FNV-1a hash output matches JS v3.3.0 reference."""
        assert fnv1a_64_hash({"b": 2, "a": 1}) == "fnv1a64-a0ebc03bdc71de7b"

    def test_manifest_hashes_deterministic_with_ordering(self, protocol: SemanticProtocol):
        """Hash outputs are stable across input ordering changes."""
        data_a = {
            "purpose": "Research login patterns",
            "tags": ["beta", "alpha"],
            "description": "Focus on enterprise SSO",
        }
        data_b = {
            "description": "Focus on enterprise SSO",
            "tags": ["alpha", "beta"],
            "purpose": "Research login patterns",
        }

        manifest_a = protocol.create_manifest(
            entity_id="order-test",
            entity_type="mission",
            data=data_a,
        )
        manifest_b = protocol.create_manifest(
            entity_id="order-test",
            entity_type="mission",
            data=data_b,
        )

        assert manifest_a.node_hash == manifest_b.node_hash
        assert manifest_a.graph_hash == manifest_b.graph_hash
        assert manifest_a.text_hash == manifest_b.text_hash
        assert manifest_a.sig_hash == manifest_b.sig_hash
        assert manifest_a.signature == manifest_a.sig_hash

    def test_hashes_ignore_timestamps(self, protocol: SemanticProtocol):
        """Timestamp fields do not influence deterministic hashes."""
        base = {
            "purpose": "Test hashing stability",
            "tags": ["alpha", "beta"],
        }
        data_a = dict(
            base,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-02T00:00:00Z",
        )
        data_b = dict(
            base,
            created_at="2025-02-01T00:00:00Z",
            updated_at="2025-03-02T00:00:00Z",
        )

        manifest_a = protocol.create_manifest(
            entity_id="timestamp-test",
            entity_type="mission",
            data=data_a,
        )
        manifest_b = protocol.create_manifest(
            entity_id="timestamp-test",
            entity_type="mission",
            data=data_b,
        )

        assert manifest_a.node_hash == manifest_b.node_hash
        assert manifest_a.graph_hash == manifest_b.graph_hash
        assert manifest_a.text_hash == manifest_b.text_hash
        assert manifest_a.sig_hash == manifest_b.sig_hash

    def test_graph_hash_stable_with_edge_order(self, protocol: SemanticProtocol):
        """Graph hash is stable regardless of edge ordering."""
        manifest_a = protocol.create_manifest(
            entity_id="edge-test",
            entity_type="mission",
            data={"purpose": "Edge hashing"},
        )
        manifest_a.edges = [
            Edge(
                edge_type="belongs_to",
                from_urn=str(manifest_a.urn),
                to_urn="urn:research:project:proj-1",
                direction="out",
                weight=0.5,
                via="data",
            ),
            Edge(
                edge_type="evidence",
                from_urn=str(manifest_a.urn),
                to_urn="urn:research:chunk:chunk-1",
                direction="out",
                weight=0.5,
                via="data",
            ),
        ]
        protocol._apply_hashes(manifest_a)

        manifest_b = protocol.create_manifest(
            entity_id="edge-test",
            entity_type="mission",
            data={"purpose": "Edge hashing"},
        )
        manifest_b.edges = list(reversed(manifest_a.edges))
        protocol._apply_hashes(manifest_b)

        assert manifest_a.graph_hash == manifest_b.graph_hash
        assert manifest_a.sig_hash == manifest_b.sig_hash


class TestSemanticProtocolSingleton:
    """Tests for singleton access."""

    def test_get_semantic_protocol_returns_instance(self):
        """get_semantic_protocol returns a SemanticProtocol instance."""
        protocol = get_semantic_protocol()
        assert isinstance(protocol, SemanticProtocol)

    def test_singleton_returns_same_instance(self):
        """Multiple calls return the same instance."""
        protocol1 = get_semantic_protocol()
        protocol2 = get_semantic_protocol()
        assert protocol1 is protocol2


# ==============================================================================
# Integration Tests with ManifestTransformer
# ==============================================================================

class TestManifestTransformerIntegration:
    """Tests for integration with manifest_transformer.py."""

    def test_import_semantic_protocol(self):
        """Semantic protocol can be imported from manifest_transformer."""
        from app.services.pedr.manifest_transformer import get_semantic_protocol
        protocol = get_semantic_protocol()
        assert isinstance(protocol, SemanticProtocol)

    def test_pedr_manifest_from_protocol_manifest(self):
        """PEDRManifest can be created from ProtocolManifest."""
        from app.services.pedr.manifest_transformer import PEDRManifest

        protocol = get_semantic_protocol()
        protocol_manifest = protocol.create_mission_manifest(
            mission_id="B12.1",
            mission_data={"purpose": "Test"},
            status="complete",
        )

        legacy_manifest = PEDRManifest.from_protocol_manifest(protocol_manifest)

        assert legacy_manifest.urn == "urn:research:mission:B12.1"
        assert legacy_manifest.confidence > 0
        assert legacy_manifest.criticality > 0
        assert isinstance(legacy_manifest.semantic_vector, list)

    def test_transform_with_protocol(self):
        """ManifestTransformer.transform_with_protocol works."""
        from app.services.pedr.manifest_transformer import get_manifest_transformer

        transformer = get_manifest_transformer()
        result = transformer.transform_with_protocol(
            mission_id="B12.1",
            mission_data={
                "researchStatement": {"objective": "Test research"},
                "tags": ["test"],
            },
            status="complete",
        )

        assert result.success
        assert result.manifest is not None
        assert result.manifest.urn == "urn:research:mission:B12.1"
        assert result.manifest.confidence > 0
        assert result.manifest.criticality > 0


# ==============================================================================
# Constants and Configuration Tests
# ==============================================================================

class TestConstants:
    """Tests for protocol constants."""

    def test_protocol_version(self):
        """Protocol version is defined."""
        assert PROTOCOL_VERSION == "3.3.0"

    def test_criticality_weights_sum_to_one(self):
        """Criticality weights sum to 1.0."""
        total = sum(CRITICALITY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_confidence_prior_valid(self):
        """Confidence prior is a valid probability."""
        assert 0.0 < CONFIDENCE_PRIOR < 1.0
