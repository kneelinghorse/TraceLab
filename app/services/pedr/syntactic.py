"""Syntactic layer for PEDR search - type detection and filtering.

This module implements Layer 3 of the 6-layer PEDR architecture, providing
structural/type awareness to search results. It enables queries to target
specific entity types and auto-detects expected types from query phrasing.

Entity types:
- mission: Research missions with objectives and deliverables
- document: Source documents (transcripts, surveys, PDFs)
- insight: Synthesized findings and observations
- chunk: Raw text fragments from documents
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


class ElementType(str, Enum):
    """Searchable entity types in TraceLab."""

    MISSION = "mission"
    DOCUMENT = "document"
    INSIGHT = "insight"
    CHUNK = "chunk"

    @classmethod
    def values(cls) -> Set[str]:
        """Return all valid element type values."""
        return {e.value for e in cls}


@dataclass(frozen=True)
class TypeDetectionResult:
    """Result of auto-detecting element type from a query."""

    detected_type: Optional[ElementType]
    confidence: float  # 0.0 to 1.0
    signals: List[str] = field(default_factory=list)
    query_normalized: str = ""


@dataclass(frozen=True)
class SyntacticFilters:
    """Filters applied by the syntactic layer."""

    element_types: Tuple[ElementType, ...] = field(default_factory=tuple)
    detected_type: Optional[ElementType] = None
    detection_confidence: float = 0.0
    type_boost_enabled: bool = True


# Type detection patterns - ordered by specificity
TYPE_DETECTION_PATTERNS: Dict[ElementType, List[Tuple[str, float]]] = {
    ElementType.MISSION: [
        # High confidence patterns
        (r"\b(?:find|show|list|get)\s+(?:all\s+)?missions?\b", 0.95),
        (r"\bmissions?\s+(?:about|for|related|on)\b", 0.90),
        (r"\bresearch\s+missions?\b", 0.90),
        (r"\bmission\s+(?:protocol|objective|status|deliverable)s?\b", 0.85),
        (r"\bwhat\s+missions?\b", 0.85),
        (r"\bwhich\s+missions?\b", 0.85),
        # Medium confidence patterns
        (r"\bobjectives?\s+(?:for|about|related)\b", 0.70),
        (r"\bdeliverables?\s+(?:for|from)\b", 0.70),
        (r"\bresearch\s+(?:objective|goal|plan)s?\b", 0.65),
        (r"\bsuccess\s+criteria\b", 0.60),
    ],
    ElementType.DOCUMENT: [
        # High confidence patterns
        (r"\b(?:find|show|list|get)\s+(?:all\s+)?documents?\b", 0.95),
        (r"\bdocuments?\s+(?:about|containing|with|related|on)\b", 0.90),
        (r"\bsource\s+documents?\b", 0.90),
        (r"\b(?:transcript|survey|pdf|file)s?\s+(?:about|containing|with)\b", 0.85),
        (r"\bwhat\s+documents?\b", 0.85),
        (r"\bwhich\s+documents?\b", 0.85),
        # Medium confidence patterns
        (r"\b(?:uploaded|imported)\s+(?:files?|documents?)\b", 0.75),
        (r"\bsource\s+(?:material|files?)\b", 0.70),
        (r"\braw\s+(?:data|text|content)\b", 0.65),
    ],
    ElementType.INSIGHT: [
        # High confidence patterns
        (r"\b(?:find|show|list|get)\s+(?:all\s+)?insights?\b", 0.95),
        (r"\binsights?\s+(?:about|from|related|on)\b", 0.90),
        (r"\bkey\s+(?:findings?|insights?|takeaways?)\b", 0.90),
        (r"\bwhat\s+(?:did\s+we\s+)?(?:learn|find|discover)\b", 0.85),
        (r"\bwhat\s+insights?\b", 0.85),
        # Medium confidence patterns
        (r"\bsynthesize[ds]?\s+(?:findings?|observations?)\b", 0.75),
        (r"\b(?:main|key|important)\s+(?:points?|observations?)\b", 0.70),
        (r"\bsummary\s+of\s+(?:findings?|research)\b", 0.65),
        (r"\bconclusions?\s+(?:from|about)\b", 0.60),
    ],
    ElementType.CHUNK: [
        # High confidence patterns
        (r"\b(?:find|show|list|get)\s+(?:all\s+)?chunks?\b", 0.95),
        (r"\btext\s+chunks?\b", 0.90),
        (r"\bchunks?\s+(?:containing|with|about)\b", 0.90),
        (r"\braw\s+chunks?\b", 0.85),
        # Medium confidence patterns
        (r"\btext\s+fragments?\b", 0.75),
        (r"\b(?:specific|exact)\s+(?:quote|passage|text)\b", 0.70),
        (r"\bverbatim\s+(?:text|content)\b", 0.65),
    ],
}

# Type boost weights applied when scoring results
TYPE_BOOST_WEIGHTS: Dict[ElementType, float] = {
    ElementType.MISSION: 0.15,
    ElementType.DOCUMENT: 0.12,
    ElementType.INSIGHT: 0.15,
    ElementType.CHUNK: 0.10,
}


class SyntacticService:
    """Service for syntactic analysis and type-aware filtering.

    The syntactic layer provides:
    1. Auto-detection of expected entity type from query phrasing
    2. Type-based filtering of search results
    3. Type boost scoring to rank matching types higher
    """

    def __init__(
        self,
        *,
        patterns: Optional[Dict[ElementType, List[Tuple[str, float]]]] = None,
        boost_weights: Optional[Dict[ElementType, float]] = None,
        confidence_threshold: float = 0.5,
    ) -> None:
        """Initialize the syntactic service.

        Args:
            patterns: Custom type detection patterns. Defaults to built-in patterns.
            boost_weights: Custom type boost weights. Defaults to built-in weights.
            confidence_threshold: Minimum confidence for auto-detection to apply.
        """
        self._patterns = patterns or TYPE_DETECTION_PATTERNS
        self._boost_weights = boost_weights or TYPE_BOOST_WEIGHTS
        self._confidence_threshold = confidence_threshold
        self._compiled_patterns: Dict[ElementType, List[Tuple[re.Pattern, float]]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance."""
        for element_type, pattern_list in self._patterns.items():
            compiled = []
            for pattern, confidence in pattern_list:
                try:
                    compiled.append((re.compile(pattern, re.IGNORECASE), confidence))
                except re.error:
                    continue
            self._compiled_patterns[element_type] = compiled

    def detect_type(self, query: str) -> TypeDetectionResult:
        """Auto-detect the expected element type from query phrasing.

        Args:
            query: The search query to analyze.

        Returns:
            TypeDetectionResult with detected type, confidence, and signals.
        """
        if not query or not query.strip():
            return TypeDetectionResult(
                detected_type=None,
                confidence=0.0,
                signals=[],
                query_normalized="",
            )

        normalized = query.strip().lower()
        best_type: Optional[ElementType] = None
        best_confidence: float = 0.0
        signals: List[str] = []

        for element_type, pattern_list in self._compiled_patterns.items():
            for pattern, confidence in pattern_list:
                match = pattern.search(normalized)
                if match:
                    signal = f"{element_type.value}:{match.group()}:{confidence:.2f}"
                    signals.append(signal)
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_type = element_type

        return TypeDetectionResult(
            detected_type=best_type if best_confidence >= self._confidence_threshold else None,
            confidence=best_confidence,
            signals=signals,
            query_normalized=normalized,
        )

    def create_filters(
        self,
        *,
        element_type: Optional[str] = None,
        element_types: Optional[List[str]] = None,
        query: Optional[str] = None,
        auto_detect: bool = True,
        type_boost_enabled: bool = True,
    ) -> SyntacticFilters:
        """Create syntactic filters for a search request.

        Args:
            element_type: Single element type to filter by.
            element_types: List of element types to filter by.
            query: Search query (used for auto-detection if no type specified).
            auto_detect: Whether to auto-detect type from query.
            type_boost_enabled: Whether to enable type boost scoring.

        Returns:
            SyntacticFilters with normalized types and detection results.
        """
        # Collect explicit types
        types: Set[ElementType] = set()

        if element_type:
            normalized = element_type.strip().lower()
            if normalized in ElementType.values():
                types.add(ElementType(normalized))

        if element_types:
            for t in element_types:
                normalized = t.strip().lower()
                if normalized in ElementType.values():
                    types.add(ElementType(normalized))

        # Auto-detect if no explicit types and query provided
        detected_type: Optional[ElementType] = None
        detection_confidence: float = 0.0

        if not types and query and auto_detect:
            result = self.detect_type(query)
            if result.detected_type:
                detected_type = result.detected_type
                detection_confidence = result.confidence
                types.add(result.detected_type)

        return SyntacticFilters(
            element_types=tuple(sorted(types, key=lambda x: x.value)),
            detected_type=detected_type,
            detection_confidence=detection_confidence,
            type_boost_enabled=type_boost_enabled,
        )

    def apply_type_boost(
        self,
        results: Sequence[Dict[str, Any]],
        *,
        filters: SyntacticFilters,
    ) -> List[Dict[str, Any]]:
        """Apply type boost to search results.

        Results matching the target element type(s) receive a score boost.

        Args:
            results: Search results to boost.
            filters: Syntactic filters with target types.

        Returns:
            Results with type_boost and updated combined_score.
        """
        if not results:
            return []

        if not filters.type_boost_enabled or not filters.element_types:
            # No boost to apply, just annotate
            boosted = []
            for result in results:
                entry = dict(result)
                entry["type_boost"] = 0.0
                entry["element_type_match"] = False
                boosted.append(entry)
            return boosted

        target_types = {t.value for t in filters.element_types}
        boosted: List[Dict[str, Any]] = []

        for result in results:
            entry = dict(result)
            result_type = self._infer_element_type(entry)
            is_match = result_type in target_types

            if is_match and result_type:
                boost_weight = self._boost_weights.get(
                    ElementType(result_type), 0.10
                )
                entry["type_boost"] = boost_weight
                entry["element_type_match"] = True

                # Apply boost to combined_score
                base_score = float(entry.get("combined_score") or entry.get("score") or 0.0)
                entry["combined_score"] = base_score * (1.0 + boost_weight)
                entry["score"] = entry["combined_score"]
            else:
                entry["type_boost"] = 0.0
                entry["element_type_match"] = False

            entry["element_type"] = result_type
            boosted.append(entry)

        return boosted

    def filter_by_type(
        self,
        results: Sequence[Dict[str, Any]],
        *,
        filters: SyntacticFilters,
    ) -> List[Dict[str, Any]]:
        """Filter results to only include matching element types.

        Args:
            results: Search results to filter.
            filters: Syntactic filters with target types.

        Returns:
            Filtered results matching target element type(s).
        """
        if not results:
            return []

        if not filters.element_types:
            # No type filter, return all
            return list(results)

        target_types = {t.value for t in filters.element_types}
        filtered: List[Dict[str, Any]] = []

        for result in results:
            result_type = self._infer_element_type(result)
            if result_type and result_type in target_types:
                entry = dict(result)
                entry["element_type"] = result_type
                filtered.append(entry)

        return filtered

    def apply(
        self,
        results: Sequence[Dict[str, Any]],
        *,
        filters: SyntacticFilters,
        filter_mode: bool = False,
    ) -> List[Dict[str, Any]]:
        """Apply syntactic processing to search results.

        This is the main entry point that combines type detection, filtering,
        and boosting into a single operation.

        Args:
            results: Search results to process.
            filters: Syntactic filters configuration.
            filter_mode: If True, filter out non-matching types. If False, only boost.

        Returns:
            Processed results with type annotations and optional filtering/boosting.
        """
        if not results:
            return []

        processed = list(results)

        if filter_mode and filters.element_types:
            processed = self.filter_by_type(processed, filters=filters)

        if filters.type_boost_enabled:
            processed = self.apply_type_boost(processed, filters=filters)

        return processed

    @staticmethod
    def _infer_element_type(result: Dict[str, Any]) -> Optional[str]:
        """Infer the element type from a search result.

        Uses available metadata to determine if result is a mission,
        document, insight, or chunk.

        Args:
            result: Search result with metadata.

        Returns:
            Inferred element type string or None if unknown.
        """
        # Check for explicit element_type
        if result.get("element_type"):
            return str(result["element_type"]).lower()

        # Check for mission indicators
        if result.get("mission_id") or result.get("quality_mission_id"):
            # Has mission association - could be mission result or mission-linked chunk
            if result.get("objective") or result.get("success_criteria"):
                return ElementType.MISSION.value

        # Check for insight indicators
        if result.get("insight_id") or result.get("insight_type"):
            return ElementType.INSIGHT.value

        # Check for document vs chunk
        if result.get("document_id"):
            # Has document association
            if result.get("chunk_id") or result.get("chunk_index") is not None:
                return ElementType.CHUNK.value
            # Pure document result
            if result.get("file_type") or result.get("source_type"):
                return ElementType.DOCUMENT.value

        # Default to chunk for search results with content
        if result.get("content") and result.get("chunk_id"):
            return ElementType.CHUNK.value

        return None


# Singleton instance
_syntactic_service: Optional[SyntacticService] = None


def get_syntactic_service() -> SyntacticService:
    """Return singleton syntactic service instance."""
    global _syntactic_service
    if _syntactic_service is None:
        _syntactic_service = SyntacticService()
    return _syntactic_service


__all__ = [
    "ElementType",
    "TypeDetectionResult",
    "SyntacticFilters",
    "SyntacticService",
    "get_syntactic_service",
    "TYPE_DETECTION_PATTERNS",
    "TYPE_BOOST_WEIGHTS",
]
