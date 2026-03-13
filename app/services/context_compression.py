"""Context compression utilities for filtering retrieved chunks by relevance."""

from __future__ import annotations

import math
import time
from collections.abc import Iterable


def compress_context(
    chunks: list[dict],
    query_embedding: Iterable[float],
    threshold: float = 0.7,
) -> tuple[list[dict], dict[str, float]]:
    """
    Filter retrieved chunks using cosine similarity against the query embedding.

    Args:
        chunks: Retrieved chunk payloads including embeddings or similarity scores.
        query_embedding: Embedding vector for the query.
        threshold: Minimum cosine similarity required to retain a chunk.

    Returns:
        A tuple of (filtered_chunks, metrics) where metrics include token reduction,
        chunk counts, threshold used, and compression latency.
    """
    start = time.perf_counter()
    query_vector = list(query_embedding)
    if not query_vector:
        return chunks, _build_metrics(chunks, chunks, threshold, start=start)

    scored_chunks: list[tuple[dict, float]] = []
    for chunk in chunks:
        similarity = _compute_similarity(query_vector, chunk)
        scored_chunk = dict(chunk)
        scored_chunk["similarity"] = similarity
        scored_chunks.append((scored_chunk, similarity))

    scored_chunks.sort(key=lambda item: item[1], reverse=True)

    filtered_chunks = [
        chunk for chunk, similarity in scored_chunks if similarity >= threshold
    ]

    # Ensure at least one chunk survives to prevent empty context.
    if not filtered_chunks and scored_chunks:
        filtered_chunks = [scored_chunks[0][0]]

    metrics = _build_metrics(
        [chunk for chunk, _ in scored_chunks],
        filtered_chunks,
        threshold,
        start=start,
    )
    return filtered_chunks, metrics


def _compute_similarity(query_vector: list[float], chunk: dict) -> float:
    """Compute cosine similarity using chunk embedding or fall back to score."""
    embedding = chunk.get("embedding")
    if isinstance(embedding, dict):
        embedding = next(iter(embedding.values()), None)

    if embedding:
        return _cosine_similarity(query_vector, embedding)

    # Fall back to provided retrieval score when embeddings are unavailable.
    score = chunk.get("score")
    if isinstance(score, (int, float)):
        return float(score)
    return 0.0


def _cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    """Compute cosine similarity between two vectors."""
    numerator = 0.0
    denominator_a = 0.0
    denominator_b = 0.0

    for x, y in zip(a, b):
        numerator += x * y
        denominator_a += x * x
        denominator_b += y * y

    if denominator_a <= 0.0 or denominator_b <= 0.0:
        return 0.0

    return numerator / math.sqrt(denominator_a * denominator_b)


def _estimate_tokens(text: str) -> int:
    """Estimate token usage assuming ~4 characters per token."""
    if not text:
        return 0
    # Guard against division by zero for very short snippets.
    return max(1, round(len(text) / 4))


def _build_metrics(
    original_chunks: list[dict],
    filtered_chunks: list[dict],
    threshold: float,
    start: float,
) -> dict[str, float]:
    """Assemble compression metrics for observability."""
    original_tokens = sum(
        _estimate_tokens(chunk.get("content", "")) for chunk in original_chunks
    )
    filtered_tokens = sum(
        _estimate_tokens(chunk.get("content", "")) for chunk in filtered_chunks
    )

    reduction_ratio = (
        0.0 if original_tokens == 0 else 1.0 - (filtered_tokens / original_tokens)
    )

    duration_ms = (time.perf_counter() - start) * 1000

    return {
        "original_chunks": len(original_chunks),
        "filtered_chunks": len(filtered_chunks),
        "original_tokens": original_tokens,
        "filtered_tokens": filtered_tokens,
        "reduction_ratio": round(reduction_ratio, 4),
        "threshold": float(threshold),
        "compression_ms": round(duration_ms, 3),
    }
