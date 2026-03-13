"""Unit tests for the context compression utilities."""

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
