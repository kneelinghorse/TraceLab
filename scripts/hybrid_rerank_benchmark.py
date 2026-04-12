#!/usr/bin/env python3
"""Hybrid Rerank Benchmark - Compare hybrid vs full PEDR search modes (B19.4).

This script benchmarks the hybrid rerank architecture against full semantic search
to validate the latency targets from the B19.4 mission:
- FTS returns top-50 candidates in <100ms
- Semantic rerank of top-50 in <200ms
- Combined P50 latency <300ms
- Precision comparable to full PEDR (>90% overlap)

Usage:
    python scripts/hybrid_rerank_benchmark.py --output cmos/reports/sprint-19/hybrid-rerank-benchmark.json

Requires:
    - PostgreSQL database with document_chunks table (content_tsv column)
    - Qdrant vector database with embeddings
    - OpenAI API key for embedding generation
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# Benchmark queries (mix of different query types)
BENCHMARK_QUERIES = [
    "user research interview methodology",
    "usability testing best practices",
    "participant recruitment strategy",
    "API integration authentication",
    "database schema design patterns",
    "embedding service configuration",
    "sprint planning backlog prioritization",
    "code review quality checklist",
    "deployment pipeline CI/CD",
    "mission protocol validation",
    "document processing pipeline",
    "search optimization strategies",
]


def run_mode_benchmark(
    mode: str,
    queries: List[str],
    top_k: int = 10,
    candidate_pool: int = 50,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Run benchmark for a specific search mode.

    Args:
        mode: "full" or "hybrid"
        queries: List of query strings
        top_k: Number of results per query
        candidate_pool: FTS candidate pool size (hybrid mode only)
        verbose: Print progress

    Returns:
        Benchmark results dictionary
    """
    from app.services.pedr.hybrid_rerank import get_hybrid_reranker

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"Running {mode.upper()} mode benchmark ({len(queries)} queries)")
        print(f"{'=' * 60}")

    try:
        reranker = get_hybrid_reranker()
    except Exception as e:
        return {
            "error": f"Could not initialize reranker: {e}",
            "mode": mode,
        }

    results = []
    latencies = []
    fts_latencies = []
    rerank_latencies = []

    for i, query in enumerate(queries, 1):
        if verbose:
            print(f"  [{i}/{len(queries)}] {query[:50]}...")

        try:
            result = reranker.search(
                query=query,
                top_k=top_k,
                candidate_pool=candidate_pool,
                mode=mode,
            )

            latencies.append(result.timings.total_ms)
            if mode == "hybrid":
                fts_latencies.append(result.timings.fts_ms)
                rerank_latencies.append(
                    result.timings.embedding_ms + result.timings.rerank_ms
                )

            # Record result details
            results.append(
                {
                    "query": query,
                    "mode": mode,
                    "latency_ms": result.timings.total_ms,
                    "fts_ms": result.timings.fts_ms,
                    "embedding_ms": result.timings.embedding_ms,
                    "rerank_ms": result.timings.rerank_ms,
                    "result_count": len(result.results),
                    "fts_candidates": result.fts_candidates_count,
                    "fallback_used": result.fallback_used,
                    "chunk_ids": [r.get("chunk_id") for r in result.results],
                }
            )

            if verbose:
                print(
                    f"      → {result.timings.total_ms:.1f}ms, {len(result.results)} results"
                )

        except Exception as e:
            print(f"    Error: {e}")
            results.append(
                {
                    "query": query,
                    "mode": mode,
                    "error": str(e),
                }
            )

    # Calculate statistics
    stats = _calculate_statistics(latencies)

    return {
        "mode": mode,
        "config": {
            "top_k": top_k,
            "candidate_pool": candidate_pool if mode == "hybrid" else None,
        },
        "statistics": stats,
        "fts_statistics": _calculate_statistics(fts_latencies)
        if fts_latencies
        else None,
        "rerank_statistics": _calculate_statistics(rerank_latencies)
        if rerank_latencies
        else None,
        "results": results,
    }


def _calculate_statistics(latencies: List[float]) -> Optional[Dict[str, float]]:
    """Calculate latency statistics."""
    if not latencies:
        return None

    sorted_latencies = sorted(latencies)
    n = len(sorted_latencies)

    return {
        "count": n,
        "min_ms": sorted_latencies[0],
        "max_ms": sorted_latencies[-1],
        "mean_ms": sum(latencies) / n,
        "p50_ms": sorted_latencies[int(n * 0.5)],
        "p90_ms": sorted_latencies[int(n * 0.9)] if n >= 10 else sorted_latencies[-1],
        "p95_ms": sorted_latencies[int(n * 0.95)] if n >= 20 else sorted_latencies[-1],
    }


def calculate_precision_overlap(
    full_results: List[Dict],
    hybrid_results: List[Dict],
) -> Dict[str, Any]:
    """Calculate result overlap between full and hybrid modes.

    Args:
        full_results: Results from full mode
        hybrid_results: Results from hybrid mode

    Returns:
        Overlap statistics
    """
    overlaps = []
    query_comparisons = []

    for full, hybrid in zip(full_results, hybrid_results):
        if "error" in full or "error" in hybrid:
            continue

        full_ids: Set[str] = set(full.get("chunk_ids", []))
        hybrid_ids: Set[str] = set(hybrid.get("chunk_ids", []))

        if not full_ids:
            continue

        intersection = full_ids & hybrid_ids
        overlap_pct = len(intersection) / len(full_ids) * 100 if full_ids else 0

        overlaps.append(overlap_pct)
        query_comparisons.append(
            {
                "query": full["query"],
                "full_count": len(full_ids),
                "hybrid_count": len(hybrid_ids),
                "overlap_count": len(intersection),
                "overlap_pct": overlap_pct,
            }
        )

    if not overlaps:
        return {"error": "No valid comparisons"}

    return {
        "mean_overlap_pct": sum(overlaps) / len(overlaps),
        "min_overlap_pct": min(overlaps),
        "max_overlap_pct": max(overlaps),
        "queries_above_90_pct": sum(1 for o in overlaps if o >= 90),
        "total_queries": len(overlaps),
        "query_comparisons": query_comparisons,
    }


def run_benchmark(
    queries: List[str],
    top_k: int = 10,
    candidate_pool: int = 50,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Run complete benchmark comparing hybrid vs full modes.

    Args:
        queries: List of query strings
        top_k: Number of results per query
        candidate_pool: FTS candidate pool size
        verbose: Print progress

    Returns:
        Complete benchmark results
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Run full mode benchmark
    full_results = run_mode_benchmark(
        mode="full",
        queries=queries,
        top_k=top_k,
        verbose=verbose,
    )

    # Run hybrid mode benchmark
    hybrid_results = run_mode_benchmark(
        mode="hybrid",
        queries=queries,
        top_k=top_k,
        candidate_pool=candidate_pool,
        verbose=verbose,
    )

    # Calculate precision overlap
    precision = calculate_precision_overlap(
        full_results.get("results", []),
        hybrid_results.get("results", []),
    )

    # Build summary
    full_stats = full_results.get("statistics", {})
    hybrid_stats = hybrid_results.get("statistics", {})
    fts_stats = hybrid_results.get("fts_statistics", {})
    rerank_stats = hybrid_results.get("rerank_statistics", {})

    summary = {
        "timestamp": timestamp,
        "query_count": len(queries),
        "success_criteria": {
            "fts_under_100ms": {
                "target": 100,
                "actual": fts_stats.get("p50_ms") if fts_stats else None,
                "pass": (fts_stats.get("p50_ms") or float("inf")) < 100
                if fts_stats
                else False,
            },
            "rerank_under_200ms": {
                "target": 200,
                "actual": rerank_stats.get("p50_ms") if rerank_stats else None,
                "pass": (rerank_stats.get("p50_ms") or float("inf")) < 200
                if rerank_stats
                else False,
            },
            "combined_under_300ms": {
                "target": 300,
                "actual": hybrid_stats.get("p50_ms") if hybrid_stats else None,
                "pass": (hybrid_stats.get("p50_ms") or float("inf")) < 300
                if hybrid_stats
                else False,
            },
            "precision_above_90pct": {
                "target": 90,
                "actual": precision.get("mean_overlap_pct"),
                "pass": (precision.get("mean_overlap_pct") or 0) >= 90,
            },
        },
        "latency_comparison": {
            "full_p50_ms": full_stats.get("p50_ms"),
            "hybrid_p50_ms": hybrid_stats.get("p50_ms"),
            "speedup_pct": (
                (
                    (full_stats.get("p50_ms", 0) - hybrid_stats.get("p50_ms", 0))
                    / full_stats.get("p50_ms", 1)
                    * 100
                )
                if full_stats.get("p50_ms")
                else None
            ),
        },
    }

    return {
        "summary": summary,
        "full_mode": full_results,
        "hybrid_mode": hybrid_results,
        "precision_analysis": precision,
    }


def main():
    parser = argparse.ArgumentParser(description="Hybrid Rerank Benchmark (B19.4)")
    parser.add_argument(
        "--output",
        "-o",
        default="cmos/reports/sprint-19/hybrid-rerank-benchmark.json",
        help="Output path for benchmark results",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of results per query",
    )
    parser.add_argument(
        "--candidate-pool",
        type=int,
        default=50,
        help="FTS candidate pool size for hybrid mode",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output",
    )
    args = parser.parse_args()

    print("Hybrid Rerank Benchmark (B19.4)")
    print("=" * 60)

    # Run benchmark
    results = run_benchmark(
        BENCHMARK_QUERIES,
        top_k=args.top_k,
        candidate_pool=args.candidate_pool,
        verbose=not args.quiet,
    )

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Benchmark complete. Results written to {output_path}")

    # Print summary
    summary = results.get("summary", {})
    print(f"\nSummary:")
    print(f"  Queries: {summary.get('query_count', 0)}")

    criteria = summary.get("success_criteria", {})
    print(f"\nSuccess Criteria:")
    for name, criterion in criteria.items():
        status = "✓ PASS" if criterion.get("pass") else "✗ FAIL"
        actual = criterion.get("actual")
        target = criterion.get("target")
        actual_str = f"{actual:.1f}" if actual is not None else "N/A"
        print(f"  {name}: {status} (target: {target}, actual: {actual_str})")

    comparison = summary.get("latency_comparison", {})
    print(f"\nLatency Comparison:")
    print(f"  Full mode P50: {comparison.get('full_p50_ms', 'N/A')}ms")
    print(f"  Hybrid mode P50: {comparison.get('hybrid_p50_ms', 'N/A')}ms")
    if comparison.get("speedup_pct"):
        print(f"  Speedup: {comparison['speedup_pct']:.1f}%")


if __name__ == "__main__":
    main()
