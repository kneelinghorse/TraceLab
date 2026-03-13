"""Semantic Protocol implementation for PEDR - The Namer.

This module implements the Semantic Protocol from the PEDR architecture,
providing meaning, identity, and intent understanding for research entities.

Key capabilities:
- URN-based identification: urn:research:{type}:{id} format
- Confidence scoring: Bayesian approach based on evidence presence
- Criticality calculation: Weighted formula for importance scoring
- Manifest creation: Transform entities into protocol manifests

Reference: cmos/planning/PEDR-docs/protocol-enhanced-deep-research/PROTOCOL_ARCHITECTURE_GUIDE.md
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# ------------------------------------------------------------------
# Constants and Configuration
# ------------------------------------------------------------------

PROTOCOL_VERSION = "3.3.0"

# ------------------------------------------------------------------
# Deterministic Signature Hashing (v3.3.0)
# ------------------------------------------------------------------

FNV1A_64_OFFSET_BASIS = 0xCBF29CE484222325
FNV1A_64_PRIME = 0x100000001B3
FNV1A_64_MASK = 0xFFFFFFFFFFFFFFFF

# Stable node hash fields (exclude timestamps/runtime metadata).
SIGNATURE_NODE_FIELDS = {
    "element": ("type", "role", "intent", "criticality"),
    "semantics": ("purpose", "tags"),
    "context": ("domain", "flow", "step"),
    "governance": ("piiHandling", "businessImpact", "userVisibility"),
}


def _utf16_code_units(value: str) -> List[int]:
    """Return UTF-16 code units to match JS charCodeAt hashing."""
    data = value.encode("utf-16-le")
    return [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]


def _json_canon(value: Any) -> str:
    """Canonical JSON string matching the JS jsonCanon helper."""
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, URN):
        value = str(value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_json_canon(item) for item in value) + "]"

    if isinstance(value, dict):
        parts = []
        for key in sorted(value.keys(), key=lambda k: str(k)):
            parts.append(
                json.dumps(str(key), ensure_ascii=False, separators=(",", ":"))
                + ":"
                + _json_canon(value[key])
            )
        return "{" + ",".join(parts) + "}"

    return json.dumps(str(value), ensure_ascii=False, separators=(",", ":"))


def fnv1a_64_hash(value: Any) -> str:
    """Hash any JSON-serializable value to fnv1a64-<16hex>."""
    canonical = _json_canon(value)
    h = FNV1A_64_OFFSET_BASIS
    for code_unit in _utf16_code_units(canonical):
        h ^= code_unit
        h = (h * FNV1A_64_PRIME) & FNV1A_64_MASK
    return f"fnv1a64-{h:016x}"

# ------------------------------------------------------------------
# Edge Type Constants (v3.3.0)
# ------------------------------------------------------------------

# Standard edge types for research graph
EDGE_TYPES = frozenset({
    "belongs_to",  # Entity belongs to parent (project, document)
    "contains",  # Parent contains child
    "references",  # Entity references sources (chunks, documents)
    "derived_from",  # Insight derived from source chunks
    "evidence",  # Mission evidence links to chunks
    "related_to",  # General association
    "binds_to",  # Protocol binding relationship
    "part_of",  # Chunk is part of document
    "sibling_of",  # Same parent relationship
    "co_occurs",  # Chunks appearing in same collection (T38.1)
    "topic_similar",  # Chunks with high embedding cosine similarity (T38.1)
})


# Entity types for URN generation
class EntityType(str, Enum):
    """Supported entity types in TraceLab research system."""

    MISSION = "mission"
    DOCUMENT = "document"
    INSIGHT = "insight"
    CHUNK = "chunk"
    PROJECT = "project"
    COLLECTION = "collection"
    REPORT = "report"


# Intent types derived from semantic purpose analysis
class SemanticIntent(str, Enum):
    """Intent classification for research artifacts."""

    CREATE = "Create"
    READ = "Read"
    UPDATE = "Update"
    DELETE = "Delete"
    EXECUTE = "Execute"
    GENERIC = "Generic"


# Criticality calculation weights from PEDR docs
CRITICALITY_WEIGHTS = {
    "impact": 0.4,
    "visibility": 0.2,
    "pii": 0.3,
    "blast_radius": 0.1,
}

# Bayesian evidence configuration
EVIDENCE_FACTORS = [
    ("has_purpose", 1.5),
    ("has_type", 1.3),
    ("has_governance", 1.2),
    ("has_requires", 1.1),
    ("has_provides", 1.1),
    ("has_quality_gates", 1.4),
    ("has_evidence", 1.3),
    ("has_synthesis", 1.2),
]

# Prior probability for confidence scoring
CONFIDENCE_PRIOR = 0.4

# Pre-compiled URN regex to avoid recompilation on every parse.
URN_PARSE_PATTERN = re.compile(r"^urn:research:([a-z_]+):([^@]+)(?:@(.+))?$")

# Intent keywords for classification
INTENT_KEYWORDS: Dict[SemanticIntent, List[str]] = {
    SemanticIntent.CREATE: ["create", "add", "submit", "new", "generate", "make"],
    SemanticIntent.READ: ["read", "get", "view", "display", "show", "find", "search", "research"],
    SemanticIntent.UPDATE: ["update", "edit", "save", "modify", "change", "revise"],
    SemanticIntent.DELETE: ["delete", "remove", "archive", "purge"],
    SemanticIntent.EXECUTE: ["execute", "trigger", "run", "process", "analyze", "synthesize"],
}


def _normalized_blast_radius(dependents: Optional[Sequence[Any]]) -> float:
    dependent_count = len(dependents) if dependents else 0
    blast_radius = math.log1p(dependent_count) / 10.0
    return min(1.0, blast_radius)


# ------------------------------------------------------------------
# Data Classes
# ------------------------------------------------------------------

@dataclass(frozen=True)
class URN:
    """Uniform Resource Name for research entities.

    Format: urn:research:{type}:{id}[@{version}]

    Examples:
        urn:research:mission:B12.1
        urn:research:document:abc123
        urn:research:chunk:doc456-chunk-3@3.2.0
    """

    entity_type: str
    entity_id: str
    version: Optional[str] = None

    def __str__(self) -> str:
        base = f"urn:research:{self.entity_type}:{self.entity_id}"
        if self.version:
            return f"{base}@{self.version}"
        return base

    @classmethod
    def parse(cls, urn_string: str) -> Optional["URN"]:
        """Parse a URN string into components.

        Args:
            urn_string: URN string to parse

        Returns:
            URN object or None if invalid
        """
        if not isinstance(urn_string, str):
            return None
        match = URN_PARSE_PATTERN.match(urn_string)
        if not match:
            return None
        return cls(
            entity_type=match.group(1),
            entity_id=match.group(2),
            version=match.group(3),
        )

    @classmethod
    def create(
        cls,
        entity_type: Union[str, EntityType],
        entity_id: str,
        version: Optional[str] = None,
    ) -> "URN":
        """Create a new URN.

        Args:
            entity_type: Type of entity (mission, document, etc.)
            entity_id: Unique identifier for the entity
            version: Optional version string

        Returns:
            URN object
        """
        if isinstance(entity_type, EntityType):
            entity_type = entity_type.value
        return cls(
            entity_type=str(entity_type).lower(),
            entity_id=str(entity_id),
            version=version,
        )


@dataclass
class GovernanceMetadata:
    """Governance information for research entities."""

    pii_handling: bool = False
    business_impact: int = 5  # 1-10 scale
    user_visibility: float = 0.5  # 0.0-1.0 scale
    blast_radius: float = 0.0  # Calculated from dependents

    def to_dict(self) -> Dict[str, Any]:
        return {
            "piiHandling": self.pii_handling,
            "businessImpact": self.business_impact,
            "userVisibility": self.user_visibility,
            "blastRadius": self.blast_radius,
        }


@dataclass
class SemanticFeatures:
    """Semantic features extracted from entity content."""

    purpose: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    vector: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "purpose": self.purpose,
            "description": self.description,
            "tags": self.tags,
            "vector": self.vector,
        }


@dataclass
class ElementMetadata:
    """Core element metadata for a protocol manifest."""

    element_type: str = ""
    role: str = ""
    intent: SemanticIntent = SemanticIntent.GENERIC
    criticality: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.element_type,
            "role": self.role,
            "intent": self.intent.value,
            "criticality": self.criticality,
        }


@dataclass
class Edge:
    """Graph edge representing a relationship between entities (v3.3.0).

    Edges are the foundation of graph-based search and traversal.
    Each edge connects two URNs with typed, weighted relationships.

    Attributes:
        edge_type: Type of relationship (belongs_to, references, derived_from, etc.)
        from_urn: Source entity URN
        to_urn: Target entity URN
        direction: Edge direction (out, in, bidirectional)
        weight: Edge weight for scoring (0.0-1.0, default 0.5)
        reason: Human-readable reason for the relationship
        via: Binding category that created this edge (api, ui, data, etc.)
        evidence: Optional evidence/metadata for the relationship
    """

    edge_type: str
    from_urn: str
    to_urn: str
    direction: str = "out"
    weight: float = 0.5
    reason: Optional[str] = None
    via: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate and normalize edge fields."""
        # Normalize direction
        if self.direction not in ("out", "in", "bidirectional"):
            object.__setattr__(self, "direction", "out")
        # Clamp weight to 0.0-1.0
        if self.weight < 0.0 or self.weight > 1.0:
            object.__setattr__(self, "weight", max(0.0, min(1.0, self.weight)))

    @property
    def normalization_key(self) -> str:
        """Generate key for edge deduplication.

        Edges with the same (type, from, to, direction) are considered duplicates.
        """
        return f"{self.edge_type}|{self.from_urn}|{self.to_urn}|{self.direction}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert edge to dictionary for serialization."""
        result = {
            "type": self.edge_type,
            "from": self.from_urn,
            "to": self.to_urn,
            "direction": self.direction,
            "weight": self.weight,
        }
        if self.reason:
            result["reason"] = self.reason
        if self.via:
            result["via"] = self.via
        if self.evidence:
            result["evidence"] = self.evidence
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Edge":
        """Create Edge from dictionary."""
        return cls(
            edge_type=data.get("type", data.get("edge_type", "related_to")),
            from_urn=data.get("from", data.get("from_urn", "")),
            to_urn=data.get("to", data.get("to_urn", "")),
            direction=data.get("direction", "out"),
            weight=float(data.get("weight", 0.5)),
            reason=data.get("reason"),
            via=data.get("via"),
            evidence=data.get("evidence"),
        )


def normalize_edges(edges: List[Edge]) -> List[Edge]:
    """Normalize and deduplicate a list of edges.

    Removes duplicates based on (type, from, to, direction) key.
    Keeps the first occurrence of each unique edge.

    Args:
        edges: List of Edge objects

    Returns:
        Deduplicated list of edges
    """
    seen: Dict[str, Edge] = {}
    for edge in edges:
        key = edge.normalization_key
        if key not in seen:
            seen[key] = edge
    return list(seen.values())


def sort_edges(edges: List[Edge]) -> List[Edge]:
    """Sort edges deterministically for stable signatures.

    Sorts by (type, from, to, direction) to ensure consistent ordering.

    Args:
        edges: List of Edge objects

    Returns:
        Sorted list of edges
    """
    return sorted(edges, key=lambda e: e.normalization_key)


def normalize_and_sort_edges(edges: List[Edge]) -> List[Edge]:
    """Normalize, deduplicate, and sort edges.

    Convenience function combining normalize_edges and sort_edges.

    Args:
        edges: List of Edge objects

    Returns:
        Deduplicated and sorted list of edges
    """
    return sort_edges(normalize_edges(edges))


@dataclass
class ProtocolManifest:
    """Full PEDR Semantic Protocol manifest (v3.3.0).

    Contains all metadata, scoring, and relationship information
    for a research entity. Includes graph-ready edges for L6 layer.
    """

    urn: URN
    version: str = PROTOCOL_VERSION

    # Core element metadata
    element: ElementMetadata = field(default_factory=ElementMetadata)

    # Semantic features
    semantics: SemanticFeatures = field(default_factory=SemanticFeatures)

    # Governance information
    governance: GovernanceMetadata = field(default_factory=GovernanceMetadata)

    # Computed scores
    confidence: float = 0.5
    criticality: float = 0.5

    # Relationships (legacy format for backward compatibility)
    relationships: Dict[str, List[str]] = field(default_factory=dict)

    # Graph-ready edges (v3.3.0)
    edges: List[Edge] = field(default_factory=list)

    # Protocol bindings
    context: Dict[str, Any] = field(default_factory=dict)

    # Original entity data
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Manifest signature (for caching/validation)
    signature: str = ""
    node_hash: str = ""
    graph_hash: str = ""
    text_hash: str = ""
    sig_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to dictionary for serialization."""
        # Build relationships dict with edges included
        relationships_dict = dict(self.relationships)
        relationships_dict["edges"] = [e.to_dict() for e in self.edges]

        return {
            "urn": str(self.urn),
            "version": self.version,
            "element": self.element.to_dict(),
            "semantics": self.semantics.to_dict(),
            "governance": self.governance.to_dict(),
            "confidence": self.confidence,
            "criticality": self.criticality,
            "relationships": relationships_dict,
            "context": self.context,
            "metadata": self.metadata,
            "__sig": self.signature,
            "__hashes": {
                "node_hash": self.node_hash,
                "graph_hash": self.graph_hash,
                "text_hash": self.text_hash,
                "sig_hash": self.sig_hash,
            },
        }

    def add_edge(self, edge: Edge) -> None:
        """Add an edge and update legacy relationships for backward compatibility."""
        self.edges.append(edge)
        # Update legacy relationship lists
        target_urn = edge.to_urn
        edge_type = edge.edge_type
        if edge_type not in self.relationships:
            self.relationships[edge_type] = []
        if target_urn not in self.relationships[edge_type]:
            self.relationships[edge_type].append(target_urn)

    def normalize_edges(self) -> None:
        """Normalize and sort edges in place for deterministic signatures."""
        self.edges = normalize_and_sort_edges(self.edges)


# ------------------------------------------------------------------
# URN Generator
# ------------------------------------------------------------------

class URNGenerator:
    """Utility class for generating URNs."""

    @staticmethod
    def generate(
        entity_type: Union[str, EntityType],
        entity_id: str,
        version: Optional[str] = None,
    ) -> URN:
        """Generate a URN for an entity.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            version: Optional version

        Returns:
            URN object
        """
        return URN.create(entity_type, entity_id, version)

    @staticmethod
    def for_mission(mission_id: str) -> URN:
        """Generate URN for a mission."""
        return URN.create(EntityType.MISSION, mission_id)

    @staticmethod
    def for_document(document_id: str) -> URN:
        """Generate URN for a document."""
        return URN.create(EntityType.DOCUMENT, document_id)

    @staticmethod
    def for_insight(insight_id: str) -> URN:
        """Generate URN for an insight."""
        return URN.create(EntityType.INSIGHT, insight_id)

    @staticmethod
    def for_chunk(document_id: str, chunk_index: int) -> URN:
        """Generate URN for a document chunk."""
        chunk_id = f"{document_id}-chunk-{chunk_index}"
        return URN.create(EntityType.CHUNK, chunk_id)

    @staticmethod
    def for_project(project_id: str) -> URN:
        """Generate URN for a project."""
        return URN.create(EntityType.PROJECT, project_id)

    @staticmethod
    def for_collection(collection_id: str) -> URN:
        """Generate URN for a collection."""
        return URN.create(EntityType.COLLECTION, collection_id)

    @staticmethod
    def for_report(report_id: str) -> URN:
        """Generate URN for a report."""
        return URN.create(EntityType.REPORT, report_id)


# ------------------------------------------------------------------
# Confidence Scoring
# ------------------------------------------------------------------

class ConfidenceScorer:
    """Bayesian confidence scoring based on evidence presence.

    Uses a log-odds approach to update confidence based on
    the presence or absence of evidence factors.
    """

    def __init__(
        self,
        prior: float = CONFIDENCE_PRIOR,
        evidence_factors: Optional[List[Tuple[str, float]]] = None,
    ):
        """Initialize the confidence scorer.

        Args:
            prior: Prior probability (default 0.4)
            evidence_factors: List of (factor_name, likelihood_ratio) tuples
        """
        self.prior = prior
        self.evidence_factors = evidence_factors or EVIDENCE_FACTORS

    def calculate(self, evidence: Dict[str, bool]) -> float:
        """Calculate confidence score using Bayesian update.

        Args:
            evidence: Dictionary mapping factor names to boolean presence

        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Start with log-odds of prior
        log_odds = math.log(self.prior / (1 - self.prior))

        # Update based on evidence
        for factor_name, likelihood in self.evidence_factors:
            is_present = evidence.get(factor_name, False)
            if is_present:
                log_odds += math.log(likelihood)
            else:
                log_odds += math.log(1 / likelihood)

        # Convert back to probability
        odds = math.exp(log_odds)
        confidence = odds / (1 + odds)

        # Round to 3 decimal places
        return round(confidence, 3)

    def score_manifest(self, manifest_data: Dict[str, Any]) -> float:
        """Calculate confidence for a manifest data dictionary.

        Args:
            manifest_data: Raw manifest/entity data

        Returns:
            Confidence score
        """
        evidence = self._extract_evidence(manifest_data)
        return self.calculate(evidence)

    def _extract_evidence(self, data: Dict[str, Any]) -> Dict[str, bool]:
        """Extract evidence factors from entity data.

        Args:
            data: Raw entity data

        Returns:
            Evidence dictionary
        """
        evidence: Dict[str, bool] = {}

        # Check for purpose/objective
        evidence["has_purpose"] = bool(
            data.get("purpose") or
            data.get("objective") or
            data.get("researchStatement", {}).get("objective") or
            data.get("research_statement", {}).get("objective")
        )

        # Check for element type
        evidence["has_type"] = bool(
            data.get("element_type") or
            data.get("type") or
            data.get("element", {}).get("type")
        )

        # Check for governance metadata
        governance = data.get("governance") or {}
        evidence["has_governance"] = bool(
            governance.get("businessImpact") or
            governance.get("business_impact") or
            data.get("governance_impact")
        )

        # Check for requires relationships
        relationships = data.get("relationships") or {}
        evidence["has_requires"] = bool(
            relationships.get("requires") or
            relationships.get("depends_on") or
            data.get("evidence")  # Evidence is a form of "requires"
        )

        # Check for provides relationships
        evidence["has_provides"] = bool(
            relationships.get("provides") or
            relationships.get("deliverables") or
            data.get("deliverables")
        )

        # Check for quality gates
        evidence["has_quality_gates"] = bool(
            data.get("quality_gates") or
            data.get("qualityGates") or
            data.get("quality_checkpoints")
        )

        # Check for evidence/sources
        evidence["has_evidence"] = bool(
            data.get("evidence") or
            data.get("sources") or
            data.get("references")
        )

        # Check for synthesis/summary
        evidence["has_synthesis"] = bool(
            data.get("synthesis") or
            data.get("summary") or
            data.get("key_insights")
        )

        return evidence


# ------------------------------------------------------------------
# Criticality Calculation
# ------------------------------------------------------------------

class CriticalityCalculator:
    """Calculate criticality scores using weighted formula.

    Criticality = (impact * 0.4) + (visibility * 0.2) + (pii * 0.3) + (blast_radius * 0.1)

    Returns a normalized score between 0.0 and 1.0.
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
    ):
        """Initialize the criticality calculator.

        Args:
            weights: Custom weights for factors
        """
        self.weights = weights or CRITICALITY_WEIGHTS

    def calculate(
        self,
        impact: float = 5.0,
        visibility: float = 0.5,
        pii: bool = False,
        dependents: Optional[List[str]] = None,
    ) -> float:
        """Calculate criticality score.

        Args:
            impact: Business impact score (1-10)
            visibility: User visibility (0.0-1.0)
            pii: Whether entity handles PII
            dependents: List of dependent entity IDs

        Returns:
            Criticality score (0.0-1.0)
        """
        # Normalize impact to 0-1 range
        normalized_impact = max(0.0, min(1.0, impact / 10.0))

        # Ensure visibility is in range
        normalized_visibility = max(0.0, min(1.0, visibility))

        # PII factor
        pii_factor = 1.0 if pii else 0.0

        # Blast radius using log1p for smooth scaling
        blast_radius = _normalized_blast_radius(dependents)

        # Calculate weighted score
        score = (
            (normalized_impact * self.weights["impact"]) +
            (normalized_visibility * self.weights["visibility"]) +
            (pii_factor * self.weights["pii"]) +
            (blast_radius * self.weights["blast_radius"])
        )

        # Clamp to 0-1 range and round
        return round(min(1.0, max(0.0, score)), 2)

    def calculate_from_governance(
        self,
        governance: GovernanceMetadata,
        dependents: Optional[List[str]] = None,
    ) -> float:
        """Calculate criticality from governance metadata.

        Args:
            governance: GovernanceMetadata object
            dependents: List of dependent entity IDs

        Returns:
            Criticality score
        """
        return self.calculate(
            impact=governance.business_impact,
            visibility=governance.user_visibility,
            pii=governance.pii_handling,
            dependents=dependents,
        )


# ------------------------------------------------------------------
# Intent Resolver
# ------------------------------------------------------------------

class IntentResolver:
    """Resolve semantic intent from purpose/description text."""

    _ACTION_INTENT_PRIORITY: Dict[SemanticIntent, int] = {
        SemanticIntent.EXECUTE: 4,
        SemanticIntent.UPDATE: 3,
        SemanticIntent.DELETE: 2,
        SemanticIntent.CREATE: 1,
        SemanticIntent.READ: 0,
        SemanticIntent.GENERIC: -1,
    }

    def __init__(
        self,
        keywords: Optional[Dict[SemanticIntent, List[str]]] = None,
    ):
        """Initialize the intent resolver.

        Args:
            keywords: Custom keyword mappings
        """
        self.keywords = keywords or INTENT_KEYWORDS

    def resolve(self, purpose: str) -> SemanticIntent:
        """Resolve intent from purpose text.

        Args:
            purpose: Purpose or description text

        Returns:
            Resolved SemanticIntent
        """
        if not purpose or not isinstance(purpose, str):
            return SemanticIntent.GENERIC

        purpose_lower = purpose.lower()
        intent_scores: List[Tuple[SemanticIntent, float, int]] = []

        for intent, keywords in self.keywords.items():
            if not keywords:
                continue
            matches = sum(1 for keyword in keywords if self._keyword_matches(purpose_lower, keyword))
            if matches <= 0:
                continue
            confidence = matches / len(keywords)
            intent_scores.append((intent, confidence, matches))

        if intent_scores:
            intent_scores.sort(
                key=lambda row: (
                    row[1],
                    row[2],
                    self._ACTION_INTENT_PRIORITY.get(row[0], -1),
                    row[0].value,
                ),
                reverse=True,
            )
            return intent_scores[0][0]

        return SemanticIntent.GENERIC

    @staticmethod
    def _keyword_matches(text: str, keyword: str) -> bool:
        pattern = rf"\b{re.escape(keyword.lower())}\b"
        return re.search(pattern, text) is not None

    def resolve_from_type(self, entity_type: str) -> SemanticIntent:
        """Resolve default intent based on entity type.

        Args:
            entity_type: Entity type string

        Returns:
            Default SemanticIntent for the type
        """
        # Research artifacts default to Read
        read_types = {"mission", "document", "insight", "chunk", "report"}

        # Collections are for organizing (Generic)
        # Projects can have any intent

        if entity_type.lower() in read_types:
            return SemanticIntent.READ

        return SemanticIntent.GENERIC


# ------------------------------------------------------------------
# Semantic Vector Generator
# ------------------------------------------------------------------

class SemanticVectorGenerator:
    """Generate simplified semantic vectors from text.

    Uses a TF-IDF-like approach for lightweight semantic features.
    """

    STOPWORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
        "be", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "must", "shall", "can", "this",
        "that", "these", "those", "it", "its", "they", "them", "their",
    }

    def __init__(self, max_dimensions: int = 50, min_word_length: int = 3):
        """Initialize the vector generator.

        Args:
            max_dimensions: Maximum vector dimensions
            min_word_length: Minimum word length to include
        """
        self.max_dimensions = max_dimensions
        self.min_word_length = min_word_length

    def generate(self, text: str) -> List[Dict[str, Any]]:
        """Generate semantic vector from text.

        Args:
            text: Text to vectorize

        Returns:
            List of {term, weight} dictionaries
        """
        if not text:
            return []

        # Tokenize and clean
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        words = [
            w for w in words
            if len(w) >= self.min_word_length and w not in self.STOPWORDS
        ]

        if not words:
            return []

        # Calculate term frequency
        term_freq: Dict[str, int] = {}
        for word in words:
            term_freq[word] = term_freq.get(word, 0) + 1

        # Sort by frequency and take top N
        entries = sorted(term_freq.items(), key=lambda x: x[1], reverse=True)
        entries = entries[:self.max_dimensions]

        # Calculate magnitude for normalization
        magnitude = math.sqrt(sum(freq ** 2 for _, freq in entries))

        if magnitude == 0:
            return []

        # Return normalized vector
        return [
            {"term": term, "weight": round(freq / magnitude, 4)}
            for term, freq in entries
        ]

    def from_manifest_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate vector from manifest data fields.

        Args:
            data: Manifest/entity data dictionary

        Returns:
            Semantic vector
        """
        text_parts = []

        # Extract text from various fields
        if data.get("purpose"):
            text_parts.append(data["purpose"])
        if data.get("description"):
            text_parts.append(data["description"])
        if data.get("objective"):
            text_parts.append(data["objective"])
        if data.get("title"):
            text_parts.append(data["title"])
        if data.get("tags"):
            text_parts.extend(data["tags"])

        # Check nested fields
        research_statement = data.get("researchStatement") or data.get("research_statement") or {}
        if research_statement.get("objective"):
            text_parts.append(research_statement["objective"])

        element = data.get("element") or {}
        if element.get("type"):
            text_parts.append(element["type"])
        if element.get("role"):
            text_parts.append(element["role"])

        semantics = data.get("semantics") or {}
        if semantics.get("purpose"):
            text_parts.append(semantics["purpose"])
        if semantics.get("tags"):
            text_parts.extend(semantics["tags"])

        combined_text = " ".join(text_parts)
        return self.generate(combined_text)


# ------------------------------------------------------------------
# Semantic Protocol Service
# ------------------------------------------------------------------

class SemanticProtocol:
    """Main Semantic Protocol service - The Namer.

    Provides:
    - URN generation
    - Confidence scoring (Bayesian)
    - Criticality calculation
    - Manifest creation and transformation
    """

    def __init__(
        self,
        *,
        confidence_prior: float = CONFIDENCE_PRIOR,
        criticality_weights: Optional[Dict[str, float]] = None,
        intent_keywords: Optional[Dict[SemanticIntent, List[str]]] = None,
    ):
        """Initialize the Semantic Protocol service.

        Args:
            confidence_prior: Prior probability for confidence scoring
            criticality_weights: Custom weights for criticality
            intent_keywords: Custom intent keyword mappings
        """
        self.urn_generator = URNGenerator()
        self.confidence_scorer = ConfidenceScorer(prior=confidence_prior)
        self.criticality_calculator = CriticalityCalculator(weights=criticality_weights)
        self.intent_resolver = IntentResolver(keywords=intent_keywords)
        self.vector_generator = SemanticVectorGenerator()

    def create_manifest(
        self,
        entity_id: str,
        entity_type: Union[str, EntityType],
        data: Dict[str, Any],
        *,
        project_id: Optional[str] = None,
        dependents: Optional[List[str]] = None,
    ) -> ProtocolManifest:
        """Create a full protocol manifest for an entity.

        Args:
            entity_id: Unique entity identifier
            entity_type: Type of entity
            data: Raw entity data
            project_id: Associated project ID
            dependents: List of dependent entity IDs

        Returns:
            ProtocolManifest with all computed fields
        """
        # Generate URN
        urn = self.urn_generator.generate(entity_type, entity_id)

        # Extract governance info
        governance = self._extract_governance(data, dependents)

        # Resolve intent
        purpose = self._extract_purpose(data)
        intent = self.intent_resolver.resolve(purpose)
        if intent == SemanticIntent.GENERIC:
            type_str = entity_type.value if isinstance(entity_type, EntityType) else entity_type
            intent = self.intent_resolver.resolve_from_type(type_str)

        # Calculate confidence
        confidence = self.confidence_scorer.score_manifest(data)

        # Calculate criticality
        criticality = self.criticality_calculator.calculate_from_governance(
            governance, dependents
        )

        # Build semantic features
        semantics = SemanticFeatures(
            purpose=self._extract_purpose(data),
            description=self._extract_description(data),
            tags=self._extract_tags(data),
            vector=self.vector_generator.from_manifest_data(data),
        )

        # Build element metadata
        type_str = entity_type.value if isinstance(entity_type, EntityType) else entity_type
        element = ElementMetadata(
            element_type=f"research.{type_str}",
            role=self._extract_role(data, type_str),
            intent=intent,
            criticality=criticality,
        )

        # Build relationships
        relationships = self._extract_relationships(data, project_id)

        # Build context
        context = self._build_context(data, project_id)

        manifest = ProtocolManifest(
            urn=urn,
            version=PROTOCOL_VERSION,
            element=element,
            semantics=semantics,
            governance=governance,
            confidence=confidence,
            criticality=criticality,
            relationships=relationships,
            context=context,
            metadata=self._extract_metadata(data),
        )
        self._apply_hashes(manifest)
        return manifest

    def create_mission_manifest(
        self,
        mission_id: str,
        mission_data: Dict[str, Any],
        *,
        quality_gates: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        status: str = "unknown",
    ) -> ProtocolManifest:
        """Create manifest specifically for a mission.

        Args:
            mission_id: Mission protocol ID
            mission_data: Full mission data
            quality_gates: Quality gate results
            project_id: Associated project ID
            status: Mission status

        Returns:
            ProtocolManifest for the mission
        """
        # Merge quality gates into data for scoring
        data = dict(mission_data)
        if quality_gates:
            data["quality_gates"] = quality_gates
        data["status"] = status

        return self.create_manifest(
            entity_id=mission_id,
            entity_type=EntityType.MISSION,
            data=data,
            project_id=project_id,
        )

    def create_document_manifest(
        self,
        document_id: str,
        name: str,
        *,
        content: Optional[str] = None,
        file_type: Optional[str] = None,
        source_type: Optional[str] = None,
        project_id: Optional[str] = None,
        chunk_count: int = 0,
    ) -> ProtocolManifest:
        """Create manifest for a document.

        Args:
            document_id: Document ID
            name: Document name
            content: Document content (for PII detection)
            file_type: File type (pdf, md, etc.)
            source_type: Source type
            project_id: Associated project ID
            chunk_count: Number of chunks

        Returns:
            ProtocolManifest for the document
        """
        data = {
            "name": name,
            "content": content,
            "file_type": file_type,
            "source_type": source_type,
            "chunk_count": chunk_count,
            "purpose": f"Research document: {name}",
        }

        # Documents with many chunks are more important
        dependents = [f"chunk-{i}" for i in range(chunk_count)] if chunk_count > 0 else None

        return self.create_manifest(
            entity_id=document_id,
            entity_type=EntityType.DOCUMENT,
            data=data,
            project_id=project_id,
            dependents=dependents,
        )

    def create_insight_manifest(
        self,
        insight_id: str,
        title: str,
        content: str,
        *,
        insight_type: Optional[str] = None,
        validated: bool = False,
        project_id: Optional[str] = None,
        source_chunk_ids: Optional[List[str]] = None,
    ) -> ProtocolManifest:
        """Create manifest for an insight.

        Args:
            insight_id: Insight ID
            title: Insight title
            content: Insight content
            insight_type: Type of insight (finding, recommendation, etc.)
            validated: Whether insight is validated
            project_id: Associated project ID
            source_chunk_ids: Source chunk URNs

        Returns:
            ProtocolManifest for the insight
        """
        data = {
            "title": title,
            "content": content,
            "insight_type": insight_type,
            "validated": validated,
            "purpose": title,
            "sources": source_chunk_ids or [],
            "governance": {
                "businessImpact": 7 if validated else 5,
            },
        }

        return self.create_manifest(
            entity_id=insight_id,
            entity_type=EntityType.INSIGHT,
            data=data,
            project_id=project_id,
        )

    def create_chunk_manifest(
        self,
        document_id: str,
        chunk_index: int,
        content: str,
        *,
        project_id: Optional[str] = None,
    ) -> ProtocolManifest:
        """Create manifest for a document chunk.

        Args:
            document_id: Parent document ID
            chunk_index: Chunk index in document
            content: Chunk content
            project_id: Associated project ID

        Returns:
            ProtocolManifest for the chunk
        """
        chunk_id = f"{document_id}-chunk-{chunk_index}"
        data = {
            "content": content,
            "document_id": document_id,
            "chunk_index": chunk_index,
            "purpose": f"Text chunk from document {document_id}",
        }

        return self.create_manifest(
            entity_id=chunk_id,
            entity_type=EntityType.CHUNK,
            data=data,
            project_id=project_id,
        )

    def calculate_confidence(self, data: Dict[str, Any]) -> float:
        """Calculate confidence score for entity data.

        Args:
            data: Entity data dictionary

        Returns:
            Confidence score (0.0-1.0)
        """
        return self.confidence_scorer.score_manifest(data)

    def calculate_criticality(
        self,
        impact: float = 5.0,
        visibility: float = 0.5,
        pii: bool = False,
        dependents: Optional[List[str]] = None,
    ) -> float:
        """Calculate criticality score.

        Args:
            impact: Business impact (1-10)
            visibility: User visibility (0.0-1.0)
            pii: PII handling flag
            dependents: Dependent entity IDs

        Returns:
            Criticality score (0.0-1.0)
        """
        return self.criticality_calculator.calculate(
            impact=impact,
            visibility=visibility,
            pii=pii,
            dependents=dependents,
        )

    def generate_urn(
        self,
        entity_type: Union[str, EntityType],
        entity_id: str,
    ) -> str:
        """Generate URN string for an entity.

        Args:
            entity_type: Type of entity
            entity_id: Entity ID

        Returns:
            URN string
        """
        return str(self.urn_generator.generate(entity_type, entity_id))

    # ------------------------------------------------------------------
    # Private Extraction Methods
    # ------------------------------------------------------------------

    def _extract_governance(
        self,
        data: Dict[str, Any],
        dependents: Optional[List[str]] = None,
    ) -> GovernanceMetadata:
        """Extract governance metadata from entity data."""
        governance = data.get("governance") or {}

        # Check for PII handling
        pii = self._detect_pii(data)

        # Get business impact
        impact = (
            governance.get("businessImpact") or
            governance.get("business_impact") or
            data.get("governance_impact") or
            5
        )

        # Get visibility
        status = str(data.get("status") or "unknown").lower()
        visibility = governance.get("userVisibility") or governance.get("user_visibility")
        if visibility is None:
            visibility = 1.0 if status == "complete" else 0.5

        # Calculate blast radius from dependents
        blast_radius = _normalized_blast_radius(dependents)

        return GovernanceMetadata(
            pii_handling=pii,
            business_impact=int(impact),
            user_visibility=float(visibility),
            blast_radius=blast_radius,
        )

    def _detect_pii(self, data: Dict[str, Any]) -> bool:
        """Detect PII handling flag from entity data."""
        # Check explicit governance flags
        governance = data.get("governance") or {}
        for key in ("pii", "piiHandling", "pii_handling", "pii_flag"):
            if governance.get(key):
                return True
            if data.get(key):
                return True

        # Check tags
        tags = data.get("tags") or []
        pii_tags = {"pii", "privacy", "redaction", "sensitive"}
        for tag in tags:
            if isinstance(tag, str) and tag.lower() in pii_tags:
                return True

        return False

    def _extract_purpose(self, data: Dict[str, Any]) -> str:
        """Extract purpose/objective from entity data."""
        # Try various locations
        if data.get("purpose"):
            return str(data["purpose"])
        if data.get("objective"):
            return str(data["objective"])

        research = data.get("researchStatement") or data.get("research_statement") or {}
        if research.get("objective"):
            return str(research["objective"])

        semantics = data.get("semantics") or {}
        if semantics.get("purpose"):
            return str(semantics["purpose"])

        return data.get("title") or data.get("name") or ""

    def _extract_description(self, data: Dict[str, Any]) -> str:
        """Extract description from entity data."""
        if data.get("description"):
            return str(data["description"])
        if data.get("summary"):
            return str(data["summary"])
        if data.get("content"):
            content = str(data["content"])
            return content[:500] + "..." if len(content) > 500 else content
        return data.get("title") or data.get("name") or ""

    def _extract_tags(self, data: Dict[str, Any]) -> List[str]:
        """Extract tags from entity data."""
        tags = data.get("tags") or []
        if isinstance(tags, list):
            return [str(t) for t in tags if t]
        return []

    def _extract_role(self, data: Dict[str, Any], entity_type: str) -> str:
        """Extract role from entity data."""
        element = data.get("element") or {}
        if element.get("role"):
            return str(element["role"])

        # Default roles by type
        role_map = {
            "mission": "knowledge_artifact",
            "document": "source_material",
            "insight": "derived_knowledge",
            "chunk": "text_fragment",
            "project": "research_container",
            "collection": "artifact_group",
            "report": "synthesis_output",
        }
        return role_map.get(entity_type, "unknown")

    def _extract_relationships(
        self,
        data: Dict[str, Any],
        project_id: Optional[str],
    ) -> Dict[str, List[str]]:
        """Extract relationships from entity data."""
        relationships: Dict[str, List[str]] = {}

        # Project relationship
        if project_id:
            relationships["belongs_to"] = [f"urn:research:project:{project_id}"]

        # Evidence/source relationships
        evidence = data.get("evidence") or []
        if isinstance(evidence, list):
            refs = []
            for item in evidence:
                if isinstance(item, dict):
                    chunk_id = item.get("chunk_id") or item.get("chunkId")
                    if chunk_id:
                        refs.append(f"urn:research:chunk:{chunk_id}")
            if refs:
                relationships["references"] = refs

        # Source chunks (for insights)
        sources = data.get("sources") or data.get("source_chunks") or []
        if isinstance(sources, list):
            derived = []
            for src in sources:
                if isinstance(src, str):
                    if src.startswith("urn:"):
                        derived.append(src)
                    else:
                        derived.append(f"urn:research:chunk:{src}")
            if derived:
                relationships["derived_from"] = derived

        # Document relationship (for chunks)
        if data.get("document_id"):
            relationships["part_of"] = [f"urn:research:document:{data['document_id']}"]

        # Related missions
        related = data.get("related_missions") or []
        if isinstance(related, list):
            relationships["related_to"] = [f"urn:research:mission:{m}" for m in related if m]

        return relationships

    def _build_context(
        self,
        data: Dict[str, Any],
        project_id: Optional[str],
    ) -> Dict[str, Any]:
        """Build context dictionary for manifest."""
        context: Dict[str, Any] = {
            "domain": "research",
        }

        if project_id:
            context["project_id"] = project_id

        if data.get("status"):
            context["status"] = data["status"]

        if data.get("created_at"):
            context["created_at"] = data["created_at"]
        elif data.get("metadata", {}).get("created"):
            context["created_at"] = data["metadata"]["created"]

        if data.get("updated_at"):
            context["updated_at"] = data["updated_at"]

        return context

    def _extract_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant metadata to store with manifest."""
        metadata: Dict[str, Any] = {}

        # Store IDs
        for key in ("id", "mission_id", "missionId", "document_id", "insight_id"):
            if data.get(key):
                metadata[key] = data[key]

        # Store status
        if data.get("status"):
            metadata["status"] = data["status"]

        # Store quality gates
        if data.get("quality_gates"):
            metadata["quality_gates"] = data["quality_gates"]

        # Store research statement
        research = data.get("researchStatement") or data.get("research_statement")
        if research:
            metadata["research_statement"] = research

        return metadata

    def _sorted_strings(self, values: Sequence[Any]) -> List[str]:
        """Return sorted, non-empty string values."""
        return sorted(str(value) for value in values if value)

    def _build_node_shape(self, manifest: ProtocolManifest) -> Dict[str, Any]:
        """Build the stable node shape for deterministic hashing."""
        return {
            "urn": str(manifest.urn),
            "version": manifest.version,
            "element": {
                "type": manifest.element.element_type,
                "role": manifest.element.role,
                "intent": manifest.element.intent.value if manifest.element.intent else None,
                "criticality": manifest.element.criticality,
            },
            "semantics": {
                "purpose": manifest.semantics.purpose,
                "tags": self._sorted_strings(manifest.semantics.tags),
            },
            "context": {
                "domain": manifest.context.get("domain"),
                "flow": manifest.context.get("flow"),
                "step": manifest.context.get("step"),
            },
            "governance": {
                "piiHandling": bool(manifest.governance.pii_handling),
                "businessImpact": manifest.governance.business_impact,
                "userVisibility": manifest.governance.user_visibility,
            },
        }

    def _build_edges_shape(self, edges: Sequence[Edge]) -> List[Dict[str, Any]]:
        """Build the stable edges shape for deterministic hashing."""
        return [
            {
                "type": edge.edge_type,
                "from": edge.from_urn,
                "to": edge.to_urn,
                "direction": edge.direction,
                "weight": edge.weight,
                "via": edge.via,
            }
            for edge in edges
        ]

    def _build_embedding_text(self, manifest: ProtocolManifest) -> str:
        """Build canonical embedding text for text hashing."""
        parts = [
            str(manifest.urn),
            manifest.element.element_type,
            manifest.element.role,
            manifest.semantics.purpose,
            manifest.semantics.description,
            *self._sorted_strings(manifest.semantics.tags),
            manifest.context.get("domain"),
            manifest.context.get("flow"),
            manifest.context.get("step"),
        ]
        return " | ".join(part for part in parts if part)

    def _apply_hashes(self, manifest: ProtocolManifest) -> None:
        """Compute deterministic hashes for a manifest."""
        manifest.normalize_edges()
        node_shape = self._build_node_shape(manifest)
        edges_shape = self._build_edges_shape(manifest.edges)
        text = self._build_embedding_text(manifest)

        manifest.node_hash = fnv1a_64_hash(node_shape)
        manifest.graph_hash = fnv1a_64_hash(edges_shape)
        manifest.text_hash = fnv1a_64_hash(text)
        manifest.sig_hash = fnv1a_64_hash({
            "node": manifest.node_hash,
            "graph": manifest.graph_hash,
        })
        manifest.signature = manifest.sig_hash


# ------------------------------------------------------------------
# Singleton Access
# ------------------------------------------------------------------

_semantic_protocol: Optional[SemanticProtocol] = None


def get_semantic_protocol() -> SemanticProtocol:
    """Return singleton Semantic Protocol instance."""
    global _semantic_protocol
    if _semantic_protocol is None:
        _semantic_protocol = SemanticProtocol()
    return _semantic_protocol


__all__ = [
    # Core classes
    "URN",
    "URNGenerator",
    "GovernanceMetadata",
    "SemanticFeatures",
    "ElementMetadata",
    "ProtocolManifest",
    # Edge classes (v3.3.0)
    "Edge",
    # Edge functions (v3.3.0)
    "normalize_edges",
    "sort_edges",
    "normalize_and_sort_edges",
    # Scoring classes
    "ConfidenceScorer",
    "CriticalityCalculator",
    "IntentResolver",
    "SemanticVectorGenerator",
    # Main service
    "SemanticProtocol",
    "get_semantic_protocol",
    # Enums
    "EntityType",
    "SemanticIntent",
    # Constants
    "PROTOCOL_VERSION",
    "CRITICALITY_WEIGHTS",
    "CONFIDENCE_PRIOR",
    "EDGE_TYPES",
]
