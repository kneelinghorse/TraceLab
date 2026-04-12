"""Shared PEDR score helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

BASE_SCORE_KEY = "pedr_base_score"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def ensure_base_score(payload: dict[str, Any]) -> float:
    """Persist and return the canonical pre-boost score for a payload."""
    if BASE_SCORE_KEY in payload:
        base_score = _to_float(payload.get(BASE_SCORE_KEY), 0.0)
    else:
        base_score = _to_float(
            payload.get(
                "rrf_score", payload.get("combined_score", payload.get("score", 0.0))
            ),
            0.0,
        )
        payload[BASE_SCORE_KEY] = base_score
    return base_score


def fuse_independent_adjustments(payload: dict[str, Any]) -> float:
    """Fuse syntactic/pragmatic boosts + quality multiplier against base score."""
    base_score = ensure_base_score(payload)
    type_boost = _to_float(payload.get("type_boost"), 0.0)
    intent_boost = _to_float(payload.get("intent_boost"), 0.0)
    quality_multiplier = _to_float(payload.get("quality_score"), 1.0)
    if quality_multiplier <= 0.0:
        quality_multiplier = 1.0

    additive_boost_factor = max(0.0, 1.0 + type_boost + intent_boost)
    fused_score = base_score * additive_boost_factor * quality_multiplier

    payload["combined_score"] = fused_score
    payload["score"] = fused_score
    payload["score_fusion"] = {
        "base_score": base_score,
        "type_boost": type_boost,
        "intent_boost": intent_boost,
        "additive_boost_factor": additive_boost_factor,
        "quality_multiplier": quality_multiplier,
    }
    return fused_score


def summarize_scores(scores: Sequence[float]) -> dict[str, float]:
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


__all__ = [
    "BASE_SCORE_KEY",
    "ensure_base_score",
    "fuse_independent_adjustments",
    "summarize_scores",
]
