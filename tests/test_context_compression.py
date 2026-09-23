"""Unit tests for the context compression utilities."""

import math

from app.core.config import Settings
from app.services.context_compression import compress_context


def test_compress_context_filters_by_threshold():
    query = [1.0, 0.2]
    chunks = [
        {"chunk_id": "c1", "content": "A" * 400, "embedding": [0.9, 0.2]},
        {"chunk_id": "c2", "content": "B" * 400, "embedding": [0.2, 0.9]},
    ]

    filtered, metrics = compress_context(chunks, query_embedding=query, threshold=0.7)

    assert [chunk["chunk_id"] for chunk in filtered] == ["c1"]
    assert metrics["original_chunks"] == 2
    assert metrics["filtered_chunks"] == 1
    assert 0.4 < metrics["reduction_ratio"] < 0.6


def test_compress_context_falls_back_to_top_chunk():
    query = [1.0, 0.2]
    chunks = [
        {"chunk_id": "c1", "content": "A" * 400, "embedding": [0.3, 0.1]},
        {"chunk_id": "c2", "content": "B" * 400, "embedding": [0.2, 0.2]},
    ]

    filtered, metrics = compress_context(chunks, query_embedding=query, threshold=0.95)

    assert len(filtered) == 1
    assert filtered[0]["chunk_id"] == "c1"
    assert metrics["filtered_chunks"] == 1
    assert metrics["threshold"] == 0.95


def test_compress_context_uses_scores_when_embeddings_missing():
    query = [1.0, 0.2]
    chunks = [
        {"chunk_id": "c1", "content": "A" * 400, "score": 0.85},
        {"chunk_id": "c2", "content": "B" * 400, "score": 0.45},
    ]

    filtered, metrics = compress_context(chunks, query_embedding=query, threshold=0.7)

    assert [chunk["chunk_id"] for chunk in filtered] == ["c1"]
    assert metrics["original_tokens"] > metrics["filtered_tokens"]


def test_production_similarities_reach_the_model_and_unrelated_chunks_do_not():
    """RAG-4: the configured cut keeps every chunk at production similarity.

    On production text-embedding-3-large gave the chunks that answer a question
    cosines of 0.425-0.664, unrelated chunks 0.399 at most and off-topic questions
    about 0.15, so the old 0.7 cut let only compression's one survivor through.
    The code default is what production runs: Railway does not set the variable.
    """
    threshold = Settings.model_fields["rag_context_threshold"].default
    query = [1.0, 0.0]

    def chunk(chunk_id, cosine):
        return {
            "chunk_id": chunk_id,
            "content": "A" * 400,
            "embedding": [cosine, math.sqrt(1 - cosine**2)],
        }

    relevant = [chunk(f"relevant-{c}", c) for c in (0.66, 0.62, 0.58, 0.55)]
    unrelated = chunk("unrelated", 0.15)

    filtered, metrics = compress_context(
        [unrelated, *relevant], query_embedding=query, threshold=threshold
    )

    assert [c["chunk_id"] for c in filtered] == [c["chunk_id"] for c in relevant]
    assert metrics["filtered_chunks"] == 4
