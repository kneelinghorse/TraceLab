#!/usr/bin/env python3
"""PEDR Latency Benchmark Suite (B19.6)

Runs standardized queries against the PEDR search API and captures latency metrics.
Outputs JSON for telemetry and comparison with Sprint 18 baseline.

Supports both rerank modes:
- full: Standard 5-layer PEDR search (default)
- hybrid: FTS-first with semantic reranking (<300ms target)

Usage:
    # Basic benchmark (requires server running on localhost:8000)
    python scripts/pedr_latency_benchmark.py

    # Save results to telemetry
    python scripts/pedr_latency_benchmark.py -o cmos/telemetry/events/pedr-benchmark-$(date +%Y%m%d).json

    # Compare to Sprint 18 baseline
    python scripts/pedr_latency_benchmark.py -c cmos/reports/sprint-18/pedr-baseline-capture.json

    # Run hybrid mode benchmark
    python scripts/pedr_latency_benchmark.py --mode hybrid

    # Adjust runs per query for statistical significance
    python scripts/pedr_latency_benchmark.py --runs 5
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


# Standard test queries from R19.0 research
# Covers UX research, technical, process, and domain-specific topics
TEST_QUERIES = [
    "usability testing best practices",
    "mission protocol validation",
    "participant recruitment strategy",
    "sprint planning backlog",
    "deployment pipeline CI/CD",
    "authentication security",
    "document ingestion",
    "semantic search optimization",
    "quality gates research",
    "API endpoint design",
]

# Default API configuration
DEFAULT_API_BASE = os.environ.get("TRACELAB_API_BASE", "http://localhost:8000/api/v1")
DEFAULT_TOP_K = 10


@dataclass
class LayerTimings:
    """Per-query layer timing breakdown."""

    lexical_ms: float = 0.0
    semantic_ms: float = 0.0
    syntactic_ms: float = 0.0
    pragmatic_ms: float = 0.0
    governance_ms: float = 0.0
    fusion_ms: float = 0.0
    relational_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class QueryResult:
    """Single query benchmark result."""

    query: str
    runs: int
    latencies_ms: List[float] = field(default_factory=list)
    p50_ms: float = 0.0
    mean_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    layer_timings: Optional[LayerTimings] = None
    result_count: int = 0
    intent: Optional[str] = None
    detected_type: Optional[str] = None
    cache_hit: bool = False
    error: Optional[str] = None


@dataclass
class BenchmarkResult:
    """Complete benchmark results."""

    timestamp: str
    sprint: str
    benchmark_type: str
    rerank_mode: str
    queries: List[Dict[str, Any]]
    aggregate: Dict[str, Any]
    comparison: Optional[Dict[str, Any]] = None


def get_auth_headers(api_base: str) -> Dict[str, str]:
    """Get authentication headers for API requests.

    Checks for JWT token in environment or attempts to get one.
    """
    token = os.environ.get("TRACELAB_JWT_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}

    # Try to authenticate with test credentials for local dev
    username = os.environ.get("TRACELAB_USERNAME", "testuser")
    password = os.environ.get("TRACELAB_PASSWORD", "testpass")

    try:
        # Extract base URL without /api/v1
        base_url = api_base.replace("/api/v1", "")
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{base_url}/api/v1/auth/token",
                data={"username": username, "password": password},
            )
            if response.status_code == 200:
                token_data = response.json()
                return {"Authorization": f"Bearer {token_data['access_token']}"}
    except Exception:
        pass

    return {}


def run_single_query(
    client: httpx.Client,
    api_base: str,
    query: str,
    top_k: int,
    headers: Dict[str, str],
    rerank_mode: str = "full",
    hnsw_ef: int = 128,
) -> tuple[float, Dict[str, Any]]:
    """Execute a single search query and return latency + response data.

    Args:
        client: HTTP client instance.
        api_base: API base URL.
        query: Search query string.
        top_k: Number of results to return.
        headers: Auth headers.
        rerank_mode: "full" or "hybrid".
        hnsw_ef: HNSW ef parameter for Qdrant.

    Returns:
        Tuple of (latency_ms, response_data).
    """
    payload = {
        "query": query,
        "top_k": top_k,
        "rerank_mode": rerank_mode,
        "hnsw_ef": hnsw_ef,
    }

    start = time.perf_counter()
    response = client.post(
        f"{api_base}/pedr/search",
        json=payload,
        headers=headers,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    response.raise_for_status()
    return elapsed_ms, response.json()


def run_benchmark(
    queries: List[str],
    runs_per_query: int = 3,
    api_base: str = DEFAULT_API_BASE,
    top_k: int = DEFAULT_TOP_K,
    rerank_mode: str = "full",
    hnsw_ef: int = 128,
    verbose: bool = True,
) -> BenchmarkResult:
    """Run benchmark across all queries and collect metrics.

    Args:
        queries: List of search queries to benchmark.
        runs_per_query: Number of times to run each query (for statistical stability).
        api_base: API base URL.
        top_k: Number of results to retrieve.
        rerank_mode: "full" or "hybrid".
        hnsw_ef: HNSW ef parameter.
        verbose: Print progress messages.

    Returns:
        BenchmarkResult with all collected metrics.
    """
    headers = get_auth_headers(api_base)
    results: List[QueryResult] = []
    all_latencies: List[float] = []

    if verbose:
        print(f"PEDR Latency Benchmark Suite")
        print("=" * 60)
        print(f"API:       {api_base}")
        print(f"Mode:      {rerank_mode}")
        print(f"Queries:   {len(queries)}")
        print(f"Runs/query:{runs_per_query}")
        print(f"Top K:     {top_k}")
        print(f"HNSW ef:   {hnsw_ef}")
        print()

    with httpx.Client(timeout=60.0) as client:
        for i, query in enumerate(queries, 1):
            query_result = QueryResult(query=query, runs=0)
            query_latencies: List[float] = []
            last_response: Optional[Dict[str, Any]] = None

            if verbose:
                print(f"[{i:2d}/{len(queries)}] {query[:45]:<45}", end=" ")

            for run in range(runs_per_query):
                try:
                    elapsed_ms, data = run_single_query(
                        client, api_base, query, top_k, headers, rerank_mode, hnsw_ef
                    )
                    query_latencies.append(elapsed_ms)
                    all_latencies.append(elapsed_ms)
                    last_response = data
                    query_result.runs += 1

                except httpx.HTTPStatusError as e:
                    error_msg = f"HTTP {e.response.status_code}"
                    query_result.error = error_msg
                    if verbose:
                        print(f" ERROR: {error_msg}")
                    break
                except httpx.RequestError as e:
                    error_msg = f"Connection error: {e}"
                    query_result.error = error_msg
                    if verbose:
                        print(f" ERROR: {error_msg}")
                    break
                except Exception as e:
                    error_msg = str(e)
                    query_result.error = error_msg
                    if verbose:
                        print(f" ERROR: {error_msg}")
                    break

            if query_latencies:
                query_result.latencies_ms = query_latencies
                query_result.p50_ms = statistics.median(query_latencies)
                query_result.mean_ms = statistics.mean(query_latencies)
                query_result.min_ms = min(query_latencies)
                query_result.max_ms = max(query_latencies)

                # Extract metadata from last successful response
                if last_response:
                    metadata = last_response.get("metadata", {})
                    timings = metadata.get("timings", {})

                    query_result.layer_timings = LayerTimings(
                        lexical_ms=timings.get("lexical_ms", 0.0),
                        semantic_ms=timings.get("semantic_ms", 0.0),
                        syntactic_ms=timings.get("syntactic_ms", 0.0),
                        pragmatic_ms=timings.get("pragmatic_ms", 0.0),
                        governance_ms=timings.get("governance_ms", 0.0),
                        fusion_ms=timings.get("fusion_ms", 0.0),
                        relational_ms=timings.get("relational_ms", 0.0),
                        total_ms=timings.get("total_ms", 0.0),
                    )
                    query_result.result_count = metadata.get(
                        "result_count", len(last_response.get("results", []))
                    )
                    query_result.intent = metadata.get("intent")
                    query_result.detected_type = metadata.get("detected_type")

                if verbose:
                    print(f"P50={query_result.p50_ms:6.0f}ms  n={query_result.runs}")

            results.append(query_result)

    # Calculate aggregate metrics
    aggregate = _compute_aggregate(all_latencies)

    # Add layer timing breakdown aggregation
    layer_timing_agg = _compute_layer_timing_aggregate(results)
    aggregate["layer_breakdown"] = layer_timing_agg

    if verbose:
        print()
        print("=" * 60)
        print("AGGREGATE RESULTS")
        print("=" * 60)
        print(f"  P50:    {aggregate.get('p50_ms', 0):>6.0f} ms")
        print(f"  P95:    {aggregate.get('p95_ms', 0):>6.0f} ms")
        print(f"  P99:    {aggregate.get('p99_ms', 0):>6.0f} ms")
        print(f"  Mean:   {aggregate.get('mean_ms', 0):>6.0f} ms")
        print(f"  Min:    {aggregate.get('min_ms', 0):>6.0f} ms")
        print(f"  Max:    {aggregate.get('max_ms', 0):>6.0f} ms")
        print(f"  Count:  {aggregate.get('total_queries', 0)}")

        if layer_timing_agg:
            print()
            print("LAYER BREAKDOWN (avg per query):")
            print(f"  Lexical:    {layer_timing_agg.get('lexical_ms', 0):>6.1f} ms")
            print(f"  Semantic:   {layer_timing_agg.get('semantic_ms', 0):>6.1f} ms")
            print(f"  Syntactic:  {layer_timing_agg.get('syntactic_ms', 0):>6.1f} ms")
            print(f"  Pragmatic:  {layer_timing_agg.get('pragmatic_ms', 0):>6.1f} ms")
            print(f"  Governance: {layer_timing_agg.get('governance_ms', 0):>6.1f} ms")
            print(f"  Fusion:     {layer_timing_agg.get('fusion_ms', 0):>6.1f} ms")

    # Convert QueryResult objects to dicts for JSON serialization
    query_dicts = []
    for r in results:
        d = {
            "query": r.query,
            "runs": r.runs,
            "p50_ms": r.p50_ms,
            "mean_ms": r.mean_ms,
            "min_ms": r.min_ms,
            "max_ms": r.max_ms,
            "result_count": r.result_count,
        }
        if r.layer_timings:
            d["layer_timings"] = {
                "lexical_ms": r.layer_timings.lexical_ms,
                "semantic_ms": r.layer_timings.semantic_ms,
                "syntactic_ms": r.layer_timings.syntactic_ms,
                "pragmatic_ms": r.layer_timings.pragmatic_ms,
                "governance_ms": r.layer_timings.governance_ms,
                "fusion_ms": r.layer_timings.fusion_ms,
                "relational_ms": r.layer_timings.relational_ms,
                "total_ms": r.layer_timings.total_ms,
            }
        if r.intent:
            d["intent"] = r.intent
        if r.detected_type:
            d["detected_type"] = r.detected_type
        if r.error:
            d["error"] = r.error
        query_dicts.append(d)

    return BenchmarkResult(
        timestamp=datetime.now(timezone.utc).isoformat(),
        sprint="sprint-19",
        benchmark_type="pedr_latency",
        rerank_mode=rerank_mode,
        queries=query_dicts,
        aggregate=aggregate,
    )


def _compute_aggregate(latencies: List[float]) -> Dict[str, Any]:
    """Compute aggregate statistics from latency list."""
    if not latencies:
        return {"error": "No successful queries"}

    sorted_latencies = sorted(latencies)
    n = len(sorted_latencies)

    return {
        "p50_ms": sorted_latencies[n // 2],
        "p95_ms": sorted_latencies[int(n * 0.95)] if n >= 20 else sorted_latencies[-1],
        "p99_ms": sorted_latencies[int(n * 0.99)] if n >= 100 else sorted_latencies[-1],
        "mean_ms": statistics.mean(latencies),
        "min_ms": min(latencies),
        "max_ms": max(latencies),
        "stdev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0.0,
        "total_queries": n,
    }


def _compute_layer_timing_aggregate(results: List[QueryResult]) -> Dict[str, float]:
    """Compute average layer timings across all queries."""
    timing_sums = {
        "lexical_ms": 0.0,
        "semantic_ms": 0.0,
        "syntactic_ms": 0.0,
        "pragmatic_ms": 0.0,
        "governance_ms": 0.0,
        "fusion_ms": 0.0,
    }
    count = 0

    for r in results:
        if r.layer_timings and r.runs > 0:
            timing_sums["lexical_ms"] += r.layer_timings.lexical_ms
            timing_sums["semantic_ms"] += r.layer_timings.semantic_ms
            timing_sums["syntactic_ms"] += r.layer_timings.syntactic_ms
            timing_sums["pragmatic_ms"] += r.layer_timings.pragmatic_ms
            timing_sums["governance_ms"] += r.layer_timings.governance_ms
            timing_sums["fusion_ms"] += r.layer_timings.fusion_ms
            count += 1

    if count == 0:
        return {}

    return {k: v / count for k, v in timing_sums.items()}


def compare_to_baseline(
    current: BenchmarkResult,
    baseline_path: str,
) -> Dict[str, Any]:
    """Compare current benchmark results to Sprint 18 baseline.

    Args:
        current: Current benchmark results.
        baseline_path: Path to baseline JSON file.

    Returns:
        Comparison dictionary with improvement metrics.
    """
    try:
        with open(baseline_path) as f:
            baseline = json.load(f)
    except FileNotFoundError:
        return {"error": f"Baseline file not found: {baseline_path}"}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON in baseline: {e}"}

    # Extract baseline P50 - handle both old and new format
    baseline_summary = baseline.get("summary", baseline.get("aggregate", {}))
    baseline_p50 = (
        baseline_summary.get("latency_p50_ms") or baseline_summary.get("p50_ms") or 0
    )

    current_p50 = current.aggregate.get("p50_ms", 0)
    current_p95 = current.aggregate.get("p95_ms", 0)

    # Calculate improvement percentage
    if baseline_p50 > 0:
        improvement_pct = ((baseline_p50 - current_p50) / baseline_p50) * 100
    else:
        improvement_pct = 0

    # Sprint 19 targets
    target_p50 = 500  # ms
    target_p95 = 1000  # ms
    target_improvement = 50  # %

    return {
        "baseline_source": baseline_path,
        "baseline_timestamp": baseline_summary.get("capture_timestamp", "unknown"),
        "baseline_p50_ms": baseline_p50,
        "baseline_mean_ms": baseline_summary.get("latency_mean_ms")
        or baseline_summary.get("mean_ms")
        or 0,
        "current_p50_ms": current_p50,
        "current_p95_ms": current_p95,
        "current_mean_ms": current.aggregate.get("mean_ms", 0),
        "improvement_pct": round(improvement_pct, 1),
        "targets": {
            "p50_target_ms": target_p50,
            "p95_target_ms": target_p95,
            "improvement_target_pct": target_improvement,
            "p50_target_met": current_p50 < target_p50,
            "p95_target_met": current_p95 < target_p95,
            "improvement_target_met": improvement_pct >= target_improvement,
        },
        "regression_alert": current_p50
        > baseline_p50 * 1.1,  # 10% regression threshold
    }


def save_results(
    result: BenchmarkResult,
    output_path: str,
    verbose: bool = True,
) -> None:
    """Save benchmark results to JSON file.

    Args:
        result: Benchmark results to save.
        output_path: Path for output JSON file.
        verbose: Print confirmation message.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict for JSON serialization
    data = {
        "timestamp": result.timestamp,
        "sprint": result.sprint,
        "benchmark_type": result.benchmark_type,
        "rerank_mode": result.rerank_mode,
        "queries": result.queries,
        "aggregate": result.aggregate,
    }
    if result.comparison:
        data["comparison"] = result.comparison

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    if verbose:
        print(f"\nResults saved to: {path}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PEDR Latency Benchmark Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output JSON file path for results",
    )
    parser.add_argument(
        "--compare",
        "-c",
        help="Baseline JSON file to compare against",
    )
    parser.add_argument(
        "--runs",
        "-r",
        type=int,
        default=3,
        help="Number of runs per query (default: 3)",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["full", "hybrid"],
        default="full",
        help="PEDR rerank mode: full (5-layer) or hybrid (FTS+semantic)",
    )
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help=f"API base URL (default: {DEFAULT_API_BASE})",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Number of results to retrieve (default: {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--hnsw-ef",
        type=int,
        default=128,
        help="HNSW ef parameter for Qdrant (default: 128)",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--queries",
        help="Comma-separated list of custom queries (overrides defaults)",
    )

    args = parser.parse_args()

    # Use custom queries if provided
    queries = TEST_QUERIES
    if args.queries:
        queries = [q.strip() for q in args.queries.split(",")]

    # Run benchmark
    result = run_benchmark(
        queries=queries,
        runs_per_query=args.runs,
        api_base=args.api_base,
        top_k=args.top_k,
        rerank_mode=args.mode,
        hnsw_ef=args.hnsw_ef,
        verbose=not args.quiet,
    )

    # Compare to baseline if provided
    if args.compare:
        if not args.quiet:
            print()
            print("=" * 60)
            print("BASELINE COMPARISON")
            print("=" * 60)

        comparison = compare_to_baseline(result, args.compare)
        result.comparison = comparison

        if not args.quiet and "error" not in comparison:
            print(f"  Baseline P50:  {comparison['baseline_p50_ms']:>6.0f} ms")
            print(f"  Current P50:   {comparison['current_p50_ms']:>6.0f} ms")
            print(f"  Improvement:   {comparison['improvement_pct']:>+5.1f} %")
            print()
            targets = comparison["targets"]
            print("  TARGETS:")
            status = "PASS" if targets["p50_target_met"] else "FAIL"
            print(f"    P50 < {targets['p50_target_ms']}ms:        [{status}]")
            status = "PASS" if targets["p95_target_met"] else "FAIL"
            print(f"    P95 < {targets['p95_target_ms']}ms:       [{status}]")
            status = "PASS" if targets["improvement_target_met"] else "FAIL"
            print(
                f"    Improvement >= {targets['improvement_target_pct']}%:  [{status}]"
            )

            if comparison["regression_alert"]:
                print()
                print(
                    "  WARNING: Regression detected! Current P50 is >10% worse than baseline."
                )
        elif not args.quiet and "error" in comparison:
            print(f"  Comparison error: {comparison['error']}")

    # Save results if output specified
    if args.output:
        save_results(result, args.output, verbose=not args.quiet)

    # Return exit code based on target achievement
    if result.comparison and "targets" in result.comparison:
        targets = result.comparison["targets"]
        if not targets["p50_target_met"]:
            return 1
        if result.comparison["regression_alert"]:
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
