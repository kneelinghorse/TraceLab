#!/usr/bin/env python3
"""Benchmark semantic retrieval quality and latency for a Qdrant collection.

This script evaluates one collection/model pair at a time and is intended for
embedding migration comparisons such as 1536d -> 3072d upgrades.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from openai import OpenAI
from sqlalchemy import func

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.chunk import DocumentChunk
from app.services.qdrant_service import QdrantService


def precision_at_k(
    retrieved_doc_ids: Sequence[str], target_doc_id: str, top_k: int
) -> float:
    if top_k <= 0:
        return 0.0
    relevant = sum(1 for doc_id in retrieved_doc_ids if doc_id == target_doc_id)
    return relevant / top_k


def recall_at_k(retrieved_doc_ids: Sequence[str], target_doc_id: str) -> float:
    return 1.0 if target_doc_id in retrieved_doc_ids else 0.0


def ndcg_at_k(retrieved_doc_ids: Sequence[str], target_doc_id: str) -> float:
    for rank, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id == target_doc_id:
            return 1.0 / math.log2(rank + 1)
    return 0.0


def percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return float(ordered[lower])
    lower_value = float(ordered[lower])
    upper_value = float(ordered[upper])
    return lower_value + (upper_value - lower_value) * (rank - lower)


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _sample_chunks(sample_size: int, max_query_chars: int) -> List[Dict[str, str]]:
    session = SessionLocal()
    try:
        rows = (
            session.query(DocumentChunk.document_id, DocumentChunk.content)
            .filter(DocumentChunk.content.isnot(None), DocumentChunk.content != "")
            .order_by(func.random())
            .limit(sample_size)
            .all()
        )
    finally:
        session.close()

    samples = []
    for row in rows:
        text = (row.content or "").strip()
        if not text:
            continue
        samples.append(
            {
                "document_id": str(row.document_id),
                "query": text[:max_query_chars],
            }
        )
    return samples


def _embed_queries(
    client: OpenAI, model: str, queries: Sequence[str], batch_size: int
) -> List[List[float]]:
    vectors: List[List[float]] = []
    for start in range(0, len(queries), batch_size):
        batch = list(queries[start : start + batch_size])
        response = client.embeddings.create(model=model, input=batch)
        vectors.extend([item.embedding for item in response.data])
    return vectors


def run_benchmark(
    *,
    collection_name: str,
    embedding_model: str,
    embedding_dimension: int,
    sample_size: int,
    top_k: int,
    max_query_chars: int,
    batch_size: int,
    hnsw_ef: int | None,
) -> Dict[str, Any]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for benchmark embeddings.")

    samples = _sample_chunks(sample_size=sample_size, max_query_chars=max_query_chars)
    if not samples:
        raise RuntimeError("No chunk samples available to benchmark.")

    openai_client = OpenAI(api_key=settings.openai_api_key)
    qdrant_service = QdrantService(
        collection_name=collection_name,
        vector_size=embedding_dimension,
    )

    query_vectors = _embed_queries(
        client=openai_client,
        model=embedding_model,
        queries=[item["query"] for item in samples],
        batch_size=batch_size,
    )

    if len(query_vectors) != len(samples):
        raise RuntimeError(
            "Embedding count mismatch while preparing benchmark queries."
        )

    invalid_dims = sorted(
        {len(vector) for vector in query_vectors if len(vector) != embedding_dimension}
    )
    if invalid_dims:
        raise RuntimeError(
            f"Embedding dimension mismatch for model {embedding_model}: {invalid_dims} != {embedding_dimension}"
        )

    precisions: List[float] = []
    recalls: List[float] = []
    ndcgs: List[float] = []
    latencies_ms: List[float] = []

    for sample, vector in zip(samples, query_vectors):
        started = time.perf_counter()
        results = qdrant_service.search_chunks(
            query_vector=vector,
            top_k=top_k,
            hnsw_ef=hnsw_ef,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        latencies_ms.append(latency_ms)

        retrieved_doc_ids = [
            str(item.get("document_id")) for item in results if item.get("document_id")
        ]
        target_doc_id = sample["document_id"]
        precisions.append(precision_at_k(retrieved_doc_ids, target_doc_id, top_k))
        recalls.append(recall_at_k(retrieved_doc_ids, target_doc_id))
        ndcgs.append(ndcg_at_k(retrieved_doc_ids, target_doc_id))

    return {
        "generated_at": _utc_now(),
        "collection_name": collection_name,
        "embedding_model": embedding_model,
        "embedding_dimension": embedding_dimension,
        "sample_size": len(samples),
        "top_k": top_k,
        "hnsw_ef": hnsw_ef,
        "metrics": {
            "precision_at_k": round(statistics.mean(precisions), 4),
            "recall_at_k": round(statistics.mean(recalls), 4),
            "ndcg_at_k": round(statistics.mean(ndcgs), 4),
            "search_latency_ms": {
                "avg": round(statistics.mean(latencies_ms), 3),
                "p95": round(percentile(latencies_ms, 0.95), 3),
                "p99": round(percentile(latencies_ms, 0.99), 3),
            },
        },
    }


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark one embedding collection/model pair."
    )
    parser.add_argument(
        "--collection", required=True, help="Qdrant collection name to evaluate"
    )
    parser.add_argument("--model", required=True, help="OpenAI embedding model name")
    parser.add_argument(
        "--dimension",
        type=int,
        required=True,
        help="Expected embedding vector dimension",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=150,
        help="Number of chunk-derived queries to evaluate",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Top-k retrieval depth")
    parser.add_argument(
        "--max-query-chars",
        type=int,
        default=280,
        help="Max chars from chunk content per query",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Embedding batch size per OpenAI request",
    )
    parser.add_argument(
        "--hnsw-ef", type=int, default=None, help="Optional hnsw_ef override for search"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "artifacts" / "benchmarks" / "embedding-benchmark.json",
        help="Destination for benchmark JSON output",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = _parse_args(argv)
    payload = run_benchmark(
        collection_name=args.collection,
        embedding_model=args.model,
        embedding_dimension=args.dimension,
        sample_size=args.sample_size,
        top_k=args.top_k,
        max_query_chars=args.max_query_chars,
        batch_size=args.batch_size,
        hnsw_ef=args.hnsw_ef,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    metrics = payload["metrics"]
    latency = metrics["search_latency_ms"]
    print(
        "Benchmark complete: "
        f"precision@{payload['top_k']}={metrics['precision_at_k']:.4f}, "
        f"recall@{payload['top_k']}={metrics['recall_at_k']:.4f}, "
        f"nDCG@{payload['top_k']}={metrics['ndcg_at_k']:.4f}, "
        f"p95={latency['p95']:.2f}ms"
    )
    print(f"Report written to {args.output}")


if __name__ == "__main__":  # pragma: no cover
    main()
