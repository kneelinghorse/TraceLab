#!/usr/bin/env python3
"""Benchmark helper that sweeps Qdrant HNSW parameters and quantization."""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.qdrant_service import QdrantService, get_qdrant_service


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(percentile * (len(ordered) - 1)))))
    return ordered[idx]


def _scroll_for_vectors(service: QdrantService, sample_size: int) -> List[List[float]]:
    vectors: List[List[float]] = []
    offset: Optional[Dict[str, Any]] = None
    while len(vectors) < sample_size:
        limit = min(64, sample_size - len(vectors))
        try:
            points, offset = service.client.scroll(  # type: ignore[attr-defined]
                collection_name=service.collection_name,
                limit=limit,
                with_vectors=True,
                with_payload=False,
                offset=offset,
            )
        except Exception:
            break
        if not points:
            break
        for point in points:
            vector = getattr(point, "vector", None)
            if isinstance(vector, dict):
                vector = next(iter(vector.values()), None)
            if vector is None:
                continue
            vectors.append(list(vector))
        if offset is None:
            break
    return vectors


def _synthetic_vectors(dimension: int, count: int, seed: int = 13) -> List[List[float]]:
    rng = random.Random(seed)
    return [[rng.random() for _ in range(dimension)] for _ in range(count)]


def _run_single_search(
    service: QdrantService,
    vector: List[float],
    *,
    top_k: int,
    ef: int,
) -> tuple[float, List[str]]:
    start = time.perf_counter()
    results = service.search_chunks(query_vector=vector, top_k=top_k, hnsw_ef=ef)
    elapsed = (time.perf_counter() - start) * 1000
    ids = [str(entry.get("chunk_id")) for entry in results if entry.get("chunk_id")]
    return elapsed, ids


def _benchmark_grid(
    service: QdrantService,
    sample_vectors: Sequence[List[float]],
    ef_values: Sequence[int],
    *,
    top_k: int,
) -> List[Dict[str, Any]]:
    baseline_ef = max(ef_values)
    baseline_latencies: List[float] = []
    baseline_results: List[List[str]] = []
    for vector in sample_vectors:
        latency, ids = _run_single_search(service, vector, top_k=top_k, ef=baseline_ef)
        baseline_latencies.append(latency)
        baseline_results.append(ids)

    results: List[Dict[str, Any]] = []
    for ef in sorted(set(ef_values)):
        if ef == baseline_ef:
            latencies = baseline_latencies
            recall = 1.0
        else:
            latencies = []
            correct = 0
            for idx, vector in enumerate(sample_vectors):
                latency, ids = _run_single_search(service, vector, top_k=top_k, ef=ef)
                latencies.append(latency)
                correct += len(set(ids) & set(baseline_results[idx]))
            recall = correct / max(1, len(sample_vectors) * top_k)

        results.append(
            {
                "hnsw_ef": ef,
                "avg_latency_ms": statistics.mean(latencies) if latencies else 0.0,
                "p95_latency_ms": _percentile(latencies, 0.95),
                "p99_latency_ms": _percentile(latencies, 0.99),
                "recall": round(recall, 4),
                "trials": len(latencies),
            }
        )

    return sorted(results, key=lambda entry: entry["hnsw_ef"])


def run_sweep(
    *,
    top_k: int,
    trials: int,
    ef_values: Sequence[int],
    output_path: Path,
    service: Optional[QdrantService] = None,
    sample_vectors: Optional[Sequence[List[float]]] = None,
) -> Dict[str, Any]:
    """Execute the benchmark and persist a JSON artifact."""

    service = service or get_qdrant_service()
    normalized_ef = sorted({int(value) for value in ef_values})
    vectors = list(sample_vectors) if sample_vectors is not None else []
    if not vectors:
        vectors = _scroll_for_vectors(service, trials)
    if len(vectors) < trials:
        vectors.extend(_synthetic_vectors(service.vector_size, trials - len(vectors)))
    vectors = vectors[:trials]

    sweep_results = _benchmark_grid(service, vectors, normalized_ef, top_k=top_k)
    diagnostics = service.get_collection_diagnostics()
    target_latency = 10.0
    recall_threshold = 0.99

    recommendation = next(
        (
            entry
            for entry in sweep_results
            if entry["p99_latency_ms"] <= target_latency and entry["recall"] >= recall_threshold
        ),
        sweep_results[-1],
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "collection": diagnostics["collection"],
        "points_count": diagnostics["points_count"],
        "vectors_count": diagnostics["vectors_count"],
        "memory_estimate_gb": diagnostics["memory_estimate_gb"],
        "trials": len(vectors),
        "top_k": top_k,
        "ef_values": normalized_ef,
        "target_latency_ms": target_latency,
        "recall_threshold": recall_threshold,
        "results": sweep_results,
        "recommendation": recommendation,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sweep Qdrant HNSW parameters and log metrics.")
    parser.add_argument("--top-k", type=int, default=10, help="Result count for evaluation queries")
    parser.add_argument("--trials", type=int, default=12, help="Number of random queries to execute")
    parser.add_argument(
        "--ef-values",
        type=int,
        nargs="+",
        default=[64, 96, 128, 160],
        help="Candidate hnsw_ef values to benchmark",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "artifacts" / "qdrant_parameter_sweep.json",
        help="Destination for the JSON report",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> None:
    args = _parse_args(argv)
    payload = run_sweep(
        top_k=args.top_k,
        trials=args.trials,
        ef_values=args.ef_values,
        output_path=args.output,
    )
    recommendation = payload["recommendation"]
    print(
        f"Benchmark complete: hnsw_ef={recommendation['hnsw_ef']} "
        f"p99={recommendation['p99_latency_ms']:.2f}ms recall={recommendation['recall']:.3f}"
    )
    print(f"Report written to {args.output}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
