"""Reciprocal Rank Fusion (RRF) implementation for PEDR multi-layer search.

RRF is a rank-aggregation method that combines results from multiple retrieval
systems without requiring score normalization. It's particularly effective for
heterogeneous rankers (semantic, keyword, etc.) with different score distributions.

Formula: RRF(d) = sum(1 / (k + r_i(d))) for each ranker i
where:
  - d is a document
  - k is a constant (typically 60) to mitigate outlier sensitivity
  - r_i(d) is the rank of document d in ranker i's results

Reference: Cormack, Clarke & Buettcher (2009) "Reciprocal Rank Fusion outperforms
Condorcet and individual Rank Learning Methods"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# Default constant for RRF formula
RRF_K = 60


@dataclass(frozen=True)
class RRFConfig:
    """Configuration for RRF fusion."""

    k: int = RRF_K
    # Layer weights for weighted RRF variant
    layer_weights: Dict[str, float] = field(default_factory=dict)
    # Minimum score threshold for inclusion
    min_score: float = 0.0
    # Whether to include layer-specific scores in output
    include_layer_scores: bool = True


@dataclass
class LayerResult:
    """Results from a single search layer."""

    layer_name: str
    results: List[Dict[str, Any]]
    weight: float = 1.0
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FusedResult:
    """A single result after RRF fusion."""

    id: str
    rrf_score: float
    rank: int
    # Layer contributions
    layer_ranks: Dict[str, int]  # layer_name -> rank (0 if not present)
    layer_scores: Dict[str, float]  # layer_name -> original score
    # Original data from best-ranked layer
    data: Dict[str, Any]
    # Metadata
    contributing_layers: List[str]


@dataclass
class FusionOutput:
    """Output from RRF fusion."""

    results: List[FusedResult]
    total_unique: int
    layers_used: List[str]
    config: RRFConfig
    fusion_latency_ms: float = 0.0
    telemetry: Dict[str, Any] = field(default_factory=dict)


class RRFFusion:
    """Reciprocal Rank Fusion for combining multi-layer search results.

    Supports:
    - Standard RRF with configurable k constant
    - Weighted RRF where layers have different influence
    - Layer-specific metadata tracking
    """

    def __init__(
        self,
        *,
        k: int = RRF_K,
        layer_weights: Optional[Dict[str, float]] = None,
        min_score: float = 0.0,
        include_layer_scores: bool = True,
    ) -> None:
        """Initialize RRF fusion.

        Args:
            k: The k constant in RRF formula. Default 60.
            layer_weights: Optional weights per layer for weighted RRF.
            min_score: Minimum RRF score for inclusion in final results.
            include_layer_scores: Whether to include original layer scores.
        """
        self.config = RRFConfig(
            k=k,
            layer_weights=layer_weights or {},
            min_score=min_score,
            include_layer_scores=include_layer_scores,
        )

    def fuse(
        self,
        layer_results: Sequence[LayerResult],
        *,
        id_key: str = "chunk_id",
        limit: Optional[int] = None,
    ) -> FusionOutput:
        """Fuse results from multiple layers using RRF.

        Args:
            layer_results: Results from each search layer.
            id_key: Key to use for identifying unique results.
            limit: Maximum number of results to return.

        Returns:
            FusionOutput with fused and ranked results.
        """
        import time

        start = time.perf_counter()

        # Collect all unique result IDs and their layer contributions
        result_data: Dict[str, Dict[str, Any]] = {}  # id -> best result data
        layer_ranks: Dict[str, Dict[str, int]] = {}  # id -> {layer: rank}
        layer_scores: Dict[str, Dict[str, float]] = {}  # id -> {layer: score}

        for layer in layer_results:
            layer_name = layer.layer_name
            weight = self.config.layer_weights.get(layer_name, layer.weight)

            for rank_idx, result in enumerate(layer.results, start=1):
                result_id = self._extract_id(result, id_key)
                if not result_id:
                    continue

                # Initialize tracking dicts for this ID
                if result_id not in layer_ranks:
                    layer_ranks[result_id] = {}
                    layer_scores[result_id] = {}
                    result_data[result_id] = {}

                # Store rank and score
                layer_ranks[result_id][layer_name] = rank_idx
                layer_scores[result_id][layer_name] = float(
                    result.get("score") or result.get("combined_score") or 0.0
                )

                # Keep best (lowest rank) result data
                if not result_data[result_id] or rank_idx < min(
                    layer_ranks[result_id].get(ln, float("inf"))
                    for ln in layer_ranks[result_id]
                    if ln != layer_name
                ):
                    result_data[result_id] = dict(result)

        # Calculate RRF scores
        fused_results: List[Tuple[str, float, Dict[str, int], Dict[str, float]]] = []
        layers_used = [lr.layer_name for lr in layer_results]

        for result_id in result_data:
            rrf_score = 0.0
            for layer in layer_results:
                layer_name = layer.layer_name
                weight = self.config.layer_weights.get(layer_name, layer.weight)
                rank = layer_ranks[result_id].get(layer_name, 0)
                if rank > 0:
                    # RRF formula: 1 / (k + rank), weighted
                    rrf_score += weight * (1.0 / (self.config.k + rank))

            if rrf_score >= self.config.min_score:
                fused_results.append(
                    (
                        result_id,
                        rrf_score,
                        layer_ranks[result_id],
                        layer_scores[result_id],
                    )
                )

        # Sort by RRF score descending
        fused_results.sort(key=lambda x: x[1], reverse=True)

        # Apply limit
        if limit:
            fused_results = fused_results[:limit]

        # Build output
        output_results: List[FusedResult] = []
        for rank, (result_id, rrf_score, ranks, scores) in enumerate(
            fused_results, start=1
        ):
            contributing = [ln for ln, r in ranks.items() if r > 0]
            output_results.append(
                FusedResult(
                    id=result_id,
                    rrf_score=round(rrf_score, 6),
                    rank=rank,
                    layer_ranks=ranks,
                    layer_scores=scores if self.config.include_layer_scores else {},
                    data=result_data[result_id],
                    contributing_layers=contributing,
                )
            )

        elapsed_ms = (time.perf_counter() - start) * 1000

        telemetry = _build_fusion_telemetry(fused_results, layers_used)

        return FusionOutput(
            results=output_results,
            total_unique=len(result_data),
            layers_used=layers_used,
            config=self.config,
            fusion_latency_ms=round(elapsed_ms, 2),
            telemetry=telemetry,
        )

    def fuse_simple(
        self,
        *layer_dicts: List[Dict[str, Any]],
        layer_names: Optional[List[str]] = None,
        id_key: str = "chunk_id",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Simplified fusion that returns enriched result dicts directly.

        This is a convenience method that wraps fuse() for simpler use cases.

        Args:
            *layer_dicts: Variable number of result lists from different layers.
            layer_names: Optional names for each layer.
            id_key: Key to identify unique results.
            limit: Maximum results to return.

        Returns:
            List of result dicts with RRF scores and metadata added.
        """
        if not layer_names:
            layer_names = [f"layer_{i}" for i in range(len(layer_dicts))]

        layer_results = [
            LayerResult(layer_name=name, results=results)
            for name, results in zip(layer_names, layer_dicts)
        ]

        output = self.fuse(layer_results, id_key=id_key, limit=limit)

        # Convert to enriched dicts
        enriched: List[Dict[str, Any]] = []
        for fused in output.results:
            entry = dict(fused.data)
            entry["rrf_score"] = fused.rrf_score
            entry["rrf_rank"] = fused.rank
            entry["contributing_layers"] = fused.contributing_layers
            entry["layer_ranks"] = fused.layer_ranks
            if self.config.include_layer_scores:
                entry["layer_scores"] = fused.layer_scores
            # Set combined_score to RRF score for downstream compatibility
            entry["combined_score"] = fused.rrf_score
            entry["score"] = fused.rrf_score
            enriched.append(entry)

        return enriched

    @staticmethod
    def _extract_id(result: Dict[str, Any], id_key: str) -> Optional[str]:
        """Extract the unique identifier from a result.

        Args:
            result: Search result dict.
            id_key: Primary key to look for.

        Returns:
            ID string or None if not found.
        """
        # Try the specified key first
        if result.get(id_key):
            return str(result[id_key])

        # Fallback to common ID fields
        for key in ("chunk_id", "id", "document_id", "mission_id"):
            if result.get(key):
                return str(result[key])

        return None


# Singleton instance
_rrf_fusion: Optional[RRFFusion] = None


def get_rrf_fusion() -> RRFFusion:
    """Return singleton RRF fusion instance."""
    global _rrf_fusion
    if _rrf_fusion is None:
        _rrf_fusion = RRFFusion()
    return _rrf_fusion


def rrf_score(ranks: Sequence[int], *, k: int = RRF_K) -> float:
    """Calculate RRF score for a document given its ranks across rankers.

    Args:
        ranks: List of ranks (1-indexed). Use 0 for not present.
        k: The k constant. Default 60.

    Returns:
        RRF score.
    """
    score = 0.0
    for rank in ranks:
        if rank > 0:
            score += 1.0 / (k + rank)
    return score


def _summarize_scores(scores: Sequence[float]) -> Dict[str, float]:
    values = [float(value) for value in scores if value is not None]
    if not values:
        return {}
    values.sort()
    count = len(values)
    mid = count // 2
    if count % 2 == 1:
        median = values[mid]
    else:
        median = (values[mid - 1] + values[mid]) / 2
    p90_index = int(0.9 * (count - 1))
    return {
        "min": round(values[0], 6),
        "max": round(values[-1], 6),
        "avg": round(sum(values) / count, 6),
        "p50": round(median, 6),
        "p90": round(values[p90_index], 6),
    }


def _build_fusion_telemetry(
    fused_results: Sequence[Tuple[str, float, Dict[str, int], Dict[str, float]]],
    layers_used: Sequence[str],
) -> Dict[str, Any]:
    total = len(fused_results)
    if total == 0:
        return {}

    layer_counts = {layer: 0 for layer in layers_used}
    multi_layer_count = 0
    scores = []

    for _, score, ranks, _ in fused_results:
        scores.append(score)
        contributed = 0
        for layer in layers_used:
            if ranks.get(layer, 0) > 0:
                layer_counts[layer] += 1
                contributed += 1
        if contributed > 1:
            multi_layer_count += 1

    layer_rates = {
        layer: round(count / total, 4) for layer, count in layer_counts.items()
    }

    return {
        "rrf_score_stats": _summarize_scores(scores),
        "layer_contribution_counts": layer_counts,
        "layer_contribution_rates": layer_rates,
        "multi_layer_result_count": multi_layer_count,
        "multi_layer_result_rate": round(multi_layer_count / total, 4),
    }


__all__ = [
    "RRFConfig",
    "LayerResult",
    "FusedResult",
    "FusionOutput",
    "RRFFusion",
    "get_rrf_fusion",
    "rrf_score",
    "RRF_K",
]
