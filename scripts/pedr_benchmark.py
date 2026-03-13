#!/usr/bin/env python3
"""PEDR Search Benchmark - Compare PEDR unified search against baseline.

This script runs the same queries from R18.0 baseline capture through the PEDR
unified search API and compares results.

Usage:
    python scripts/pedr_benchmark.py --output cmos/reports/sprint-18/pedr-benchmark.json
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.pedr.search_orchestrator import create_pedr_orchestrator
from app.services.pedr.fusion import RRFFusion


# Baseline queries from R18.0
BASELINE_QUERIES = [
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
]


def run_pedr_benchmark(
    queries: List[str],
    top_k: int = 5,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Run PEDR unified search on benchmark queries.

    Args:
        queries: List of query strings
        top_k: Number of results per query
        verbose: Print progress

    Returns:
        Benchmark results dictionary
    """
    if verbose:
        print(f"Running PEDR benchmark with {len(queries)} queries...")

    try:
        orchestrator = create_pedr_orchestrator()
    except Exception as e:
        print(f"Warning: Could not create orchestrator with DB: {e}")
        print("Running in mock mode for testing...")
        return _run_mock_benchmark(queries, top_k)

    results = []
    latencies = []
    total_candidates = 0

    for i, query in enumerate(queries, 1):
        if verbose:
            print(f"  [{i}/{len(queries)}] {query[:40]}...")

        try:
            response = orchestrator.search(query=query, top_k=top_k)

            latency_ms = response.metadata.timings.total_ms
            latencies.append(latency_ms)
            total_candidates += response.metadata.total_candidates

            # Build result summary
            top_results = []
            for r in response.results[:3]:
                top_results.append(
                    {
                        "rank": r.rrf_rank,
                        "rrf_score": r.rrf_score,
                        "contributing_layers": r.contributing_layers,
                        "element_type": r.element_type,
                        "document_id": r.document_id,
                        "content_preview": r.content[:100] if r.content else "",
                    }
                )

            results.append(
                {
                    "query": query,
                    "latency_ms": latency_ms,
                    "result_count": len(response.results),
                    "intent": response.metadata.intent,
                    "intent_confidence": response.metadata.intent_confidence,
                    "detected_type": response.metadata.detected_type,
                    "type_confidence": response.metadata.type_confidence,
                    "layers_used": response.metadata.layers_used,
                    "layer_timings": {
                        "lexical_ms": response.metadata.timings.lexical_ms,
                        "semantic_ms": response.metadata.timings.semantic_ms,
                        "syntactic_ms": response.metadata.timings.syntactic_ms,
                        "pragmatic_ms": response.metadata.timings.pragmatic_ms,
                        "governance_ms": response.metadata.timings.governance_ms,
                        "fusion_ms": response.metadata.timings.fusion_ms,
                    },
                    "top_results": top_results,
                }
            )

        except Exception as e:
            print(f"    Error: {e}")
            results.append(
                {
                    "query": query,
                    "error": str(e),
                    "latency_ms": 0,
                    "result_count": 0,
                }
            )
            latencies.append(0)

    # Calculate summary statistics
    valid_latencies = [l for l in latencies if l > 0]
    if valid_latencies:
        latencies_sorted = sorted(valid_latencies)
        p50_idx = int(len(latencies_sorted) * 0.5)
        p90_idx = int(len(latencies_sorted) * 0.9)
        p95_idx = int(len(latencies_sorted) * 0.95)

        summary = {
            "capture_timestamp": datetime.now(timezone.utc).isoformat(),
            "query_count": len(queries),
            "successful_queries": len(valid_latencies),
            "latency_p50_ms": latencies_sorted[p50_idx]
            if p50_idx < len(latencies_sorted)
            else 0,
            "latency_p90_ms": latencies_sorted[p90_idx]
            if p90_idx < len(latencies_sorted)
            else 0,
            "latency_p95_ms": latencies_sorted[
                max(0, min(p95_idx, len(latencies_sorted) - 1))
            ],
            "latency_mean_ms": sum(valid_latencies) / len(valid_latencies),
            "avg_results_per_query": sum(r.get("result_count", 0) for r in results)
            / len(results),
            "total_candidates": total_candidates,
        }
    else:
        summary = {
            "capture_timestamp": datetime.now(timezone.utc).isoformat(),
            "query_count": len(queries),
            "successful_queries": 0,
            "error": "No successful queries",
        }

    return {
        "summary": summary,
        "results": results,
        "search_config": {
            "search_mode": "PEDR unified (5-layer RRF fusion)",
            "top_k": top_k,
            "layers": ["lexical", "semantic", "syntactic", "pragmatic", "governance"],
            "rrf_k": 60,
        },
    }


def _run_mock_benchmark(queries: List[str], top_k: int) -> Dict[str, Any]:
    """Run mock benchmark when DB is not available."""
    from app.services.pedr.syntactic import get_syntactic_service
    from app.services.pedr.pragmatic import get_pragmatic_service

    syntactic = get_syntactic_service()
    pragmatic = get_pragmatic_service()

    results = []
    for query in queries:
        start = time.perf_counter()

        # Run pre-analysis layers only
        syn_filters = syntactic.create_filters(query=query, auto_detect=True)
        prag_filters = pragmatic.create_filters(query=query)

        latency = (time.perf_counter() - start) * 1000

        results.append(
            {
                "query": query,
                "latency_ms": latency,
                "result_count": 0,
                "intent": prag_filters.intent.value,
                "intent_confidence": prag_filters.confidence,
                "detected_type": syn_filters.detected_type.value
                if syn_filters.detected_type
                else None,
                "type_confidence": syn_filters.detection_confidence,
                "note": "Mock benchmark - no DB search",
            }
        )

    return {
        "summary": {
            "capture_timestamp": datetime.now(timezone.utc).isoformat(),
            "query_count": len(queries),
            "successful_queries": len(queries),
            "note": "Mock benchmark without database",
        },
        "results": results,
        "search_config": {
            "search_mode": "PEDR pre-analysis only (mock)",
        },
    }


def compare_with_baseline(
    pedr_results: Dict[str, Any],
    baseline_path: str = "cmos/reports/sprint-18/pedr-baseline-capture.json",
) -> Dict[str, Any]:
    """Compare PEDR results with baseline.

    Args:
        pedr_results: PEDR benchmark results
        baseline_path: Path to baseline JSON

    Returns:
        Comparison report
    """
    try:
        with open(baseline_path) as f:
            baseline = json.load(f)
    except FileNotFoundError:
        return {"error": f"Baseline not found: {baseline_path}"}

    baseline_summary = baseline.get("summary", {})
    pedr_summary = pedr_results.get("summary", {})

    # Calculate improvements
    baseline_p50 = baseline_summary.get("latency_p50_ms", 0)
    pedr_p50 = pedr_summary.get("latency_p50_ms", 0)

    comparison = {
        "baseline": {
            "search_mode": baseline.get("search_config", {}).get(
                "search_mode", "unknown"
            ),
            "latency_p50_ms": baseline_p50,
            "latency_mean_ms": baseline_summary.get("latency_mean_ms", 0),
            "avg_results": baseline_summary.get("avg_results_per_query", 0),
        },
        "pedr": {
            "search_mode": pedr_results.get("search_config", {}).get(
                "search_mode", "unknown"
            ),
            "latency_p50_ms": pedr_p50,
            "latency_p95_ms": pedr_summary.get("latency_p95_ms", 0),
            "latency_mean_ms": pedr_summary.get("latency_mean_ms", 0),
            "avg_results": pedr_summary.get("avg_results_per_query", 0),
        },
        "improvements": {
            "latency_change_pct": (
                ((pedr_p50 - baseline_p50) / baseline_p50 * 100)
                if baseline_p50 > 0
                else None
            ),
            "additional_capabilities": [
                "RRF fusion across 5 layers",
                "Intent classification",
                "Element type detection",
                "Quality scoring integration",
                "Semantic Protocol URNs",
            ],
        },
    }

    return comparison


def main():
    parser = argparse.ArgumentParser(description="PEDR Search Benchmark")
    parser.add_argument(
        "--output",
        "-o",
        default="cmos/reports/sprint-18/pedr-benchmark.json",
        help="Output path for benchmark results",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of results per query",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Compare results with baseline",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output",
    )
    args = parser.parse_args()

    # Run benchmark
    results = run_pedr_benchmark(
        BASELINE_QUERIES,
        top_k=args.top_k,
        verbose=not args.quiet,
    )

    # Add comparison if requested
    if args.compare_baseline:
        comparison = compare_with_baseline(results)
        results["comparison"] = comparison

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nBenchmark complete. Results written to {output_path}")

    # Print summary
    summary = results.get("summary", {})
    print(f"\nSummary:")
    print(f"  Queries: {summary.get('query_count', 0)}")
    print(f"  Successful: {summary.get('successful_queries', 0)}")
    if "latency_p50_ms" in summary:
        print(f"  P50 latency: {summary['latency_p50_ms']:.1f}ms")
        print(f"  P95 latency: {summary.get('latency_p95_ms', 0):.1f}ms")
        print(f"  Mean latency: {summary.get('latency_mean_ms', 0):.1f}ms")
        print(f"  Avg results: {summary.get('avg_results_per_query', 0):.1f}")

    if "comparison" in results:
        comp = results["comparison"]
        print(f"\nBaseline Comparison:")
        print(f"  Baseline P50: {comp['baseline']['latency_p50_ms']:.1f}ms")
        print(f"  PEDR P50: {comp['pedr']['latency_p50_ms']:.1f}ms")
        if comp["improvements"].get("latency_change_pct") is not None:
            change = comp["improvements"]["latency_change_pct"]
            direction = "slower" if change > 0 else "faster"
            print(f"  Change: {abs(change):.1f}% {direction}")


if __name__ == "__main__":
    main()
