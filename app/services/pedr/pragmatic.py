"""Pragmatic layer for PEDR search - intent classification and routing.

This module implements Layer 4 of the 6-layer PEDR architecture, providing
intent awareness to search. It classifies what the user wants to DO with
the search results, not just what they're searching for.

Intent types:
- SEARCH: Find/retrieve information (queries, research, exploration)
- CREATE: Create new content (add documents, new projects)
- UPDATE: Modify existing content (edit, update, change)
- DELETE: Remove content (delete, remove, archive)
- EXECUTE: Run/trigger operations (run analysis, execute mission)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.pedr.score_utils import ensure_base_score


class QueryIntent(str, Enum):
    """User intent classification for search queries."""

    SEARCH = "search"  # Find, show, list, retrieve, research
    CREATE = "create"  # Add, new, create, make
    UPDATE = "update"  # Edit, modify, update, change
    DELETE = "delete"  # Delete, remove, archive
    EXECUTE = "execute"  # Run, execute, trigger, start


@dataclass(frozen=True)
class IntentDetectionResult:
    """Result of intent classification from a query."""

    intent: QueryIntent
    confidence: float  # 0.0 to 1.0
    signals: List[str] = field(default_factory=list)
    query_normalized: str = ""
    is_action_query: bool = False  # True for CREATE/UPDATE/DELETE/EXECUTE


@dataclass(frozen=True)
class PragmaticFilters:
    """Filters and metadata from the pragmatic layer."""

    intent: QueryIntent
    confidence: float = 0.0
    is_action_query: bool = False
    intent_boost_enabled: bool = True
    # Routing hints
    route_to_search: bool = True
    route_to_action_handler: bool = False


# Intent detection patterns - ordered by specificity
INTENT_DETECTION_PATTERNS: Dict[QueryIntent, List[Tuple[str, float]]] = {
    QueryIntent.SEARCH: [
        # High confidence search patterns
        (r"^(?:find|search|show|list|get|display)\b", 0.95),
        (r"\bwhat\s+(?:is|are|was|were)\b", 0.90),
        (r"\bwhere\s+(?:is|are|can\s+i\s+find)\b", 0.90),
        (r"\bhow\s+(?:to|do|does|can)\b", 0.85),
        (r"\bwhich\s+(?:\w+)\s+(?:has|have|contains?|includes?)\b", 0.85),
        (r"\b(?:research|explore|investigate|look\s+for)\b", 0.90),
        (r"\b(?:about|related\s+to|regarding|concerning)\b", 0.75),
        # Medium confidence patterns
        (r"\b(?:tell\s+me|explain|describe)\b", 0.80),
        (r"\bwho\s+(?:is|are|was|were)\b", 0.80),
        (r"\bwhen\s+(?:did|was|were|is)\b", 0.75),
        (r"\bwhy\s+(?:is|are|did|does)\b", 0.75),
        (r"^[^?]*\?$", 0.70),  # Ends with question mark
    ],
    QueryIntent.CREATE: [
        # High confidence create patterns
        (r"^(?:create|add|make|new)\b", 0.95),
        (r"\b(?:create|add)\s+(?:a\s+)?(?:new\s+)?(?:document|project|mission|collection|report)\b", 0.95),
        (r"\b(?:start|begin|initialize)\s+(?:a\s+)?(?:new\s+)?(?:project|mission|research|workspace)\b", 0.90),
        (r"^(?:start|begin|initialize)\s+(?:a\s+)?(?:new\s+)?(?:\w+\s+)?(?:project|mission|workspace)\b", 0.96),
        (r"\bupload\s+(?:a\s+)?(?:new\s+)?(?:document|file)\b", 0.90),
        (r"\b(?:generate|produce|build)\s+(?:a\s+)?(?:new\s+)?(?:report|summary)\b", 0.85),
        # Medium confidence patterns
        (r"\bset\s+up\b", 0.75),
        (r"\binitiate\b", 0.75),
        (r"\bestablish\b", 0.70),
    ],
    QueryIntent.UPDATE: [
        # High confidence update patterns
        (r"^(?:update|edit|modify|change|revise)\b", 0.95),
        (r"\b(?:update|edit|modify|change)\s+(?:the\s+)?(?:document|project|mission|report)\b", 0.95),
        (r"\b(?:rename|revise|amend)\s+(?:the\s+)?", 0.95),
        (r"\b(?:fix|correct|adjust)\b", 0.85),
        # Medium confidence patterns
        (r"\b(?:replace|swap)\b", 0.80),
        (r"\b(?:alter|transform)\b", 0.75),
        (r"\bmake\s+changes?\s+to\b", 0.96),  # Higher priority than CREATE's "make"
    ],
    QueryIntent.DELETE: [
        # High confidence delete patterns
        (r"^(?:delete|remove|erase)\b", 0.95),
        (r"\b(?:delete|remove)\s+(?:the\s+)?(?:document|project|mission|collection|report)\b", 0.95),
        (r"\b(?:archive|discard|purge)\b", 0.85),
        (r"\b(?:trash|eliminate|destroy)\b", 0.85),
        # Medium confidence patterns
        (r"\bget\s+rid\s+of\b", 0.96),  # High confidence - clearly DELETE intent
        (r"\bclean\s+up\b", 0.70),
        (r"\bclear\b", 0.65),
    ],
    QueryIntent.EXECUTE: [
        # High confidence execute patterns
        (r"^(?:run|execute|trigger)\b", 0.95),
        (r"^start\s+(?:the\s+)?(?:\w+\s+)?(?:workflow|process|pipeline|analysis)\b", 0.95),
        (r"\b(?:run|execute)\s+(?:the\s+)?(?:mission|analysis|search|sync)\b", 0.95),
        (r"\b(?:launch|activate|kick\s+off)\b", 0.90),
        (r"\b(?:submit|process|perform)\b", 0.85),
        (r"\b(?:synthesize|analyze)\s+(?:the\s+)?(?:\w+\s+)?(?:data|documents?|results|findings)\b", 0.95),
        (r"^(?:synthesize|analyze)\b", 0.91),  # Action verbs at start of query
        # Medium confidence patterns
        (r"\binitiate\s+(?:the\s+)?(?:process|workflow)\b", 0.80),
        (r"\bbegin\s+(?:the\s+)?(?:analysis|research)\b", 0.75),
    ],
}

# Intent-based result boost weights
INTENT_BOOST_WEIGHTS: Dict[QueryIntent, Dict[str, float]] = {
    QueryIntent.SEARCH: {
        "research": 0.15,  # Boost research artifacts
        "insight": 0.15,  # Boost insights
        "document": 0.10,  # Boost documents
        "chunk": 0.08,  # Small boost for chunks
        "mission": 0.05,  # Light boost for missions
    },
    QueryIntent.CREATE: {
        # No boost for search results when intent is to create
    },
    QueryIntent.UPDATE: {
        # Boost items that can be updated
        "document": 0.10,
        "mission": 0.10,
    },
    QueryIntent.DELETE: {
        # Boost items that can be deleted
        "document": 0.10,
        "mission": 0.10,
    },
    QueryIntent.EXECUTE: {
        "mission": 0.15,  # Boost executable missions
    },
}


class PragmaticService:
    """Service for pragmatic analysis and intent-aware routing.

    The pragmatic layer provides:
    1. Intent classification (Search, Create, Update, Delete, Execute)
    2. Routing hints for action vs search queries
    3. Intent-aware result boosting
    """

    def __init__(
        self,
        *,
        patterns: Optional[Dict[QueryIntent, List[Tuple[str, float]]]] = None,
        boost_weights: Optional[Dict[QueryIntent, Dict[str, float]]] = None,
        confidence_threshold: float = 0.5,
    ) -> None:
        """Initialize the pragmatic service.

        Args:
            patterns: Custom intent detection patterns. Defaults to built-in patterns.
            boost_weights: Custom intent boost weights. Defaults to built-in weights.
            confidence_threshold: Minimum confidence for classification to apply.
        """
        self._patterns = patterns or INTENT_DETECTION_PATTERNS
        self._boost_weights = boost_weights or INTENT_BOOST_WEIGHTS
        self._confidence_threshold = confidence_threshold
        self._compiled_patterns: Dict[QueryIntent, List[Tuple[re.Pattern, float]]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance."""
        for intent, pattern_list in self._patterns.items():
            compiled = []
            for pattern, confidence in pattern_list:
                try:
                    compiled.append((re.compile(pattern, re.IGNORECASE), confidence))
                except re.error:
                    continue
            self._compiled_patterns[intent] = compiled

    def classify_intent(self, query: str) -> IntentDetectionResult:
        """Classify the intent of a query.

        Args:
            query: The search query to analyze.

        Returns:
            IntentDetectionResult with classified intent, confidence, and signals.
        """
        if not query or not query.strip():
            return IntentDetectionResult(
                intent=QueryIntent.SEARCH,
                confidence=0.5,  # Default to search with medium confidence
                signals=["empty_query:default_search"],
                query_normalized="",
                is_action_query=False,
            )

        normalized = query.strip().lower()
        best_intent: QueryIntent = QueryIntent.SEARCH
        best_confidence: float = 0.0
        signals: List[str] = []

        for intent, pattern_list in self._compiled_patterns.items():
            for pattern, confidence in pattern_list:
                match = pattern.search(normalized)
                if match:
                    signal = f"{intent.value}:{match.group()}:{confidence:.2f}"
                    signals.append(signal)
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_intent = intent

        # If no patterns matched with sufficient confidence, default to search
        if best_confidence < self._confidence_threshold:
            best_intent = QueryIntent.SEARCH
            best_confidence = max(best_confidence, 0.5)
            signals.append("default:search:0.50")

        is_action = best_intent in {
            QueryIntent.CREATE,
            QueryIntent.UPDATE,
            QueryIntent.DELETE,
            QueryIntent.EXECUTE,
        }

        return IntentDetectionResult(
            intent=best_intent,
            confidence=best_confidence,
            signals=signals,
            query_normalized=normalized,
            is_action_query=is_action,
        )

    def create_filters(
        self,
        *,
        query: str,
        intent_boost_enabled: bool = True,
    ) -> PragmaticFilters:
        """Create pragmatic filters for a search request.

        Args:
            query: Search query to analyze.
            intent_boost_enabled: Whether to enable intent-based boost scoring.

        Returns:
            PragmaticFilters with intent and routing hints.
        """
        result = self.classify_intent(query)

        return PragmaticFilters(
            intent=result.intent,
            confidence=result.confidence,
            is_action_query=result.is_action_query,
            intent_boost_enabled=intent_boost_enabled,
            route_to_search=result.intent == QueryIntent.SEARCH or not result.is_action_query,
            route_to_action_handler=result.is_action_query,
        )

    def apply_intent_boost(
        self,
        results: Sequence[Dict[str, Any]],
        *,
        filters: PragmaticFilters,
    ) -> List[Dict[str, Any]]:
        """Apply intent-based boost to search results.

        Results are boosted based on their type and the detected intent.
        For example, search intent boosts insights and research artifacts.

        Args:
            results: Search results to boost.
            filters: Pragmatic filters with intent.

        Returns:
            Results with intent_boost and updated combined_score.
        """
        if not results:
            return []

        if not filters.intent_boost_enabled:
            # No boost to apply, just annotate
            boosted = []
            for result in results:
                entry = dict(result)
                base_score = ensure_base_score(entry)
                entry["intent_boost"] = 0.0
                entry["query_intent"] = filters.intent.value
                entry["intent_adjusted_score"] = base_score
                entry["combined_score"] = base_score
                entry["score"] = base_score
                boosted.append(entry)
            return boosted

        intent_weights = self._boost_weights.get(filters.intent, {})
        boosted: List[Dict[str, Any]] = []

        for result in results:
            entry = dict(result)
            entry["query_intent"] = filters.intent.value

            # Get result type for boost lookup
            result_type = self._infer_result_type(entry)
            boost_weight = intent_weights.get(result_type, 0.0) if result_type else 0.0

            entry["intent_boost"] = boost_weight
            base_score = ensure_base_score(entry)

            if boost_weight > 0:
                # Apply boost relative to the original fused score.
                entry["intent_adjusted_score"] = base_score * (1.0 + boost_weight)
                entry["combined_score"] = entry["intent_adjusted_score"]
                entry["score"] = entry["intent_adjusted_score"]
            else:
                entry["intent_adjusted_score"] = base_score
                entry["combined_score"] = base_score
                entry["score"] = base_score

            boosted.append(entry)

        return boosted

    def apply(
        self,
        results: Sequence[Dict[str, Any]],
        *,
        filters: PragmaticFilters,
    ) -> List[Dict[str, Any]]:
        """Apply pragmatic processing to search results.

        This is the main entry point that combines intent detection
        and boosting into a single operation.

        Args:
            results: Search results to process.
            filters: Pragmatic filters configuration.

        Returns:
            Processed results with intent annotations and optional boosting.
        """
        if not results:
            return []

        # Apply intent boost
        processed = self.apply_intent_boost(results, filters=filters)

        return processed

    @staticmethod
    def _infer_result_type(result: Dict[str, Any]) -> Optional[str]:
        """Infer the type of a search result for boost lookup.

        Args:
            result: Search result with metadata.

        Returns:
            Inferred type string or None.
        """
        # Check explicit element_type
        if result.get("element_type"):
            etype = str(result["element_type"]).lower()
            # Map element types to boost categories
            if etype in ("insight", "finding"):
                return "insight"
            if etype in ("document", "file"):
                return "document"
            if etype in ("chunk", "fragment"):
                return "chunk"
            if etype in ("mission", "task"):
                return "mission"
            return etype

        # Infer from metadata
        if result.get("insight_id") or result.get("insight_type"):
            return "insight"
        if result.get("mission_id") and (
            result.get("objective") or result.get("success_criteria")
        ):
            return "mission"
        if result.get("document_id") and not result.get("chunk_id"):
            return "document"
        if result.get("chunk_id"):
            return "chunk"

        return None


# Singleton instance
_pragmatic_service: Optional[PragmaticService] = None


def get_pragmatic_service() -> PragmaticService:
    """Return singleton pragmatic service instance."""
    global _pragmatic_service
    if _pragmatic_service is None:
        _pragmatic_service = PragmaticService()
    return _pragmatic_service


__all__ = [
    "QueryIntent",
    "IntentDetectionResult",
    "PragmaticFilters",
    "PragmaticService",
    "get_pragmatic_service",
    "INTENT_DETECTION_PATTERNS",
    "INTENT_BOOST_WEIGHTS",
]
