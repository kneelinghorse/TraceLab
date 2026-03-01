import pytest

from scripts.rag_baseline_benchmark import (
    bm25_scores,
    build_documents_from_texts,
    build_index,
    evaluate_queries,
    sanitize_ascii,
    tfidf_scores,
    tokenize,
)


def test_sanitize_ascii_strips_unicode() -> None:
    text = "alpha\u2014beta\u2192gamma"
    sanitized = sanitize_ascii(text)
    assert all(ord(ch) < 128 for ch in sanitized)


def test_rank_prefers_relevant_doc() -> None:
    texts = {
        "doc-a": "alpha beta gamma",
        "doc-b": "delta epsilon zeta",
    }
    docs = build_documents_from_texts(texts)
    index = build_index(docs)
    query_tokens = tokenize("alpha gamma")

    bm25 = bm25_scores(query_tokens, index=index)
    tfidf = tfidf_scores(query_tokens, index=index)

    assert max(bm25, key=bm25.get) == "doc-a"
    assert max(tfidf, key=tfidf.get) == "doc-a"


def test_evaluate_queries_metrics() -> None:
    texts = {
        "doc-a": "alpha beta gamma",
        "doc-b": "delta epsilon zeta",
    }
    docs = build_documents_from_texts(texts)
    index = build_index(docs)
    queries = [
        {
            "query_id": "Q1",
            "query": "alpha",
            "relevance": [{"doc_id": "doc-a", "relevance": 2}],
        }
    ]

    results = evaluate_queries(
        index=index,
        queries=queries,
        top_k=1,
        semantic_weight=0.7,
        keyword_weight=0.3,
    )

    semantic_summary = results["rag_semantic"]["summary"]
    hybrid_summary = results["hybrid_baseline"]["summary"]

    assert semantic_summary["precision_at_k"] == pytest.approx(1.0)
    assert semantic_summary["recall_at_k"] == pytest.approx(1.0)
    assert semantic_summary["ndcg_at_k"] == pytest.approx(1.0)

    assert hybrid_summary["precision_at_k"] == pytest.approx(1.0)
    assert hybrid_summary["recall_at_k"] == pytest.approx(1.0)
    assert hybrid_summary["ndcg_at_k"] == pytest.approx(1.0)
