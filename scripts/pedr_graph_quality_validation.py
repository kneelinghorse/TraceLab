#!/usr/bin/env python3
"""Graph L6 quality validation: analyze existing telemetry and run live comparisons.

This script operates in two modes:

1. ANALYZE mode (default): Parse existing graph telemetry JSONL files and produce
   a quality comparison report without requiring a running database.

2. LIVE mode (--live): Run queries through the PEDR orchestrator with graph
   disabled (baseline) and multiple graph configurations, then compare results.

Usage:
    # Analyze existing telemetry files
    python scripts/pedr_graph_quality_validation.py

    # Analyze specific files
    python scripts/pedr_graph_quality_validation.py --telemetry-files \
        cmos/telemetry/events/graph-tuning-baseline.jsonl \
        cmos/telemetry/events/graph-tuning-depth1-seeds5.jsonl

    # Run live comparison (requires database)
    python scripts/pedr_graph_quality_validation.py --live \
        --queries "how does tracelab work,what is QPF" \
        --configs default,aggressive,conservative

    # Output report to file
    python scripts/pedr_graph_quality_validation.py --output reports/graph-quality-report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_TELEMETRY_FILES = [
    "cmos/telemetry/events/graph-tuning-baseline.jsonl",
    "cmos/telemetry/events/graph-tuning-depth1-seeds5.jsonl",
    "cmos/telemetry/events/sprint-26-graph-telemetry.jsonl",
]

DEFAULT_OUTPUT = Path("cmos/telemetry/events/graph-quality-report.json")


# ---------------------------------------------------------------------------
# Named configuration presets for live comparison
# ---------------------------------------------------------------------------

GRAPH_CONFIGS = {
    "disabled": {"enable_graph": False},
    "default": {
        "enable_graph": True,
        "graph_weight": 0.12,
        "graph_depth": 2,
        "graph_decay": 0.7,
        "graph_top_k_seeds": 10,
    },
    "sprint25_original": {
        "enable_graph": True,
        "graph_weight": 0.12,
        "graph_depth": 2,
        "graph_decay": 0.7,
        "graph_top_k_seeds": 10,
    },
    "aggressive": {
        "enable_graph": True,
        "graph_weight": 0.15,
        "graph_depth": 3,
        "graph_decay": 0.5,
        "graph_top_k_seeds": 10,
    },
    "conservative": {
        "enable_graph": True,
        "graph_weight": 0.05,
        "graph_depth": 1,
        "graph_decay": 0.8,
        "graph_top_k_seeds": 3,
    },
    "high_weight": {
        "enable_graph": True,
        "graph_weight": 0.20,
        "graph_depth": 2,
        "graph_decay": 0.6,
        "graph_top_k_seeds": 5,
    },
}


# ---------------------------------------------------------------------------
# Data classes for structured analysis
# ---------------------------------------------------------------------------


@dataclass
class QueryMetrics:
    """Metrics for a single query execution."""

    query: str
    config_name: str
    graph_depth: int
    graph_decay: float
    graph_weight: float
    graph_top_k_seeds: int
    seed_count: Optional[int]
    total_candidates: Optional[int]
    graph_candidates_expanded: int
    results_with_graph: int
    result_share: float
    top_5_with_graph: int
    top_5_share: float
    graph_ms: float
    fusion_ms: float
    total_ms: float
    layers_used: List[str]
    graph_contribution_rate: float
    multi_layer_result_rate: float
    rrf_score_avg: Optional[float] = None
    rrf_score_max: Optional[float] = None


@dataclass
class ConfigSummary:
    """Aggregated summary for a single configuration."""

    config_name: str
    query_count: int
    graph_depth: int
    graph_decay: float
    graph_weight: float
    graph_top_k_seeds: int
    avg_graph_candidates: float
    avg_results_with_graph: float
    avg_result_share: float
    avg_top_5_with_graph: float
    avg_top_5_share: float
    avg_graph_ms: float
    avg_total_ms: float
    avg_graph_contribution_rate: float
    queries_with_any_graph_impact: int
    graph_impact_rate: float


@dataclass
class QualityReport:
    """Full quality validation report."""

    generated_at: str
    mode: str
    telemetry_files_analyzed: List[str]
    total_events_analyzed: int
    config_summaries: List[Dict[str, Any]]
    graph_edge_assessment: Dict[str, Any]
    recommendations: List[str]
    config_comparison: List[Dict[str, Any]]
    raw_metrics: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Telemetry analysis (ANALYZE mode)
# ---------------------------------------------------------------------------


def parse_telemetry_event(event: Dict[str, Any]) -> Optional[QueryMetrics]:
    """Parse a single telemetry JSONL event into QueryMetrics."""
    if event.get("event") != "pedr_graph_telemetry":
        return None

    graph = event.get("graph", {})
    rrf = event.get("rrf", {})
    ranking = event.get("ranking", {})
    timings = event.get("timings", {})
    graph_impact = ranking.get("graph_impact", {})
    rrf_telemetry = rrf.get("telemetry", {})
    rrf_score_stats = rrf_telemetry.get("rrf_score_stats", {})
    layer_contribution_rates = rrf_telemetry.get("layer_contribution_rates", {})

    config_name = _infer_config_name(graph)

    return QueryMetrics(
        query=event.get("query", ""),
        config_name=config_name,
        graph_depth=graph.get("depth", 0),
        graph_decay=graph.get("decay", 0.0),
        graph_weight=graph.get("weight", 0.0),
        graph_top_k_seeds=graph.get("top_k_seeds", 0),
        seed_count=graph.get("seed_count"),
        total_candidates=graph.get("total_candidates"),
        graph_candidates_expanded=graph.get("graph_candidates_expanded", 0),
        results_with_graph=graph_impact.get("results_with_graph", 0),
        result_share=graph_impact.get("result_share", 0.0),
        top_5_with_graph=graph_impact.get("top_5_with_graph", 0),
        top_5_share=graph_impact.get("top_5_share", 0.0),
        graph_ms=timings.get("graph_ms", 0.0),
        fusion_ms=timings.get("fusion_ms", 0.0),
        total_ms=timings.get("total_ms", 0.0),
        layers_used=rrf.get("layers_used", []),
        graph_contribution_rate=layer_contribution_rates.get("graph", 0.0),
        multi_layer_result_rate=rrf_telemetry.get("multi_layer_result_rate", 0.0),
        rrf_score_avg=rrf_score_stats.get("avg"),
        rrf_score_max=rrf_score_stats.get("max"),
    )


def _infer_config_name(graph: Dict[str, Any]) -> str:
    """Infer the configuration preset name from graph parameters."""
    depth = graph.get("depth", 0)
    decay = graph.get("decay", 0.0)
    weight = graph.get("weight", 0.0)
    seeds = graph.get("top_k_seeds", 0)

    for name, cfg in GRAPH_CONFIGS.items():
        if name == "disabled":
            continue
        if (
            cfg.get("graph_depth") == depth
            and cfg.get("graph_decay") == decay
            and abs(cfg.get("graph_weight", 0) - weight) < 0.001
            and cfg.get("graph_top_k_seeds") == seeds
        ):
            return name
    return f"custom_d{depth}_w{weight:.2f}_k{seeds}"


def load_telemetry_events(paths: Sequence[Path]) -> List[QueryMetrics]:
    """Load and parse telemetry events from JSONL files."""
    metrics: List[QueryMetrics] = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            parsed = parse_telemetry_event(event)
            if parsed:
                metrics.append(parsed)
    return metrics


def summarize_config(config_name: str, metrics: List[QueryMetrics]) -> ConfigSummary:
    """Compute aggregate summary for a configuration group."""
    n = len(metrics)
    if n == 0:
        return ConfigSummary(
            config_name=config_name,
            query_count=0,
            graph_depth=0,
            graph_decay=0.0,
            graph_weight=0.0,
            graph_top_k_seeds=0,
            avg_graph_candidates=0.0,
            avg_results_with_graph=0.0,
            avg_result_share=0.0,
            avg_top_5_with_graph=0.0,
            avg_top_5_share=0.0,
            avg_graph_ms=0.0,
            avg_total_ms=0.0,
            avg_graph_contribution_rate=0.0,
            queries_with_any_graph_impact=0,
            graph_impact_rate=0.0,
        )

    first = metrics[0]
    impacted = sum(1 for m in metrics if m.graph_candidates_expanded > 0)

    return ConfigSummary(
        config_name=config_name,
        query_count=n,
        graph_depth=first.graph_depth,
        graph_decay=first.graph_decay,
        graph_weight=first.graph_weight,
        graph_top_k_seeds=first.graph_top_k_seeds,
        avg_graph_candidates=_safe_avg([m.graph_candidates_expanded for m in metrics]),
        avg_results_with_graph=_safe_avg([m.results_with_graph for m in metrics]),
        avg_result_share=_safe_avg([m.result_share for m in metrics]),
        avg_top_5_with_graph=_safe_avg([m.top_5_with_graph for m in metrics]),
        avg_top_5_share=_safe_avg([m.top_5_share for m in metrics]),
        avg_graph_ms=_safe_avg([m.graph_ms for m in metrics]),
        avg_total_ms=_safe_avg([m.total_ms for m in metrics]),
        avg_graph_contribution_rate=_safe_avg(
            [m.graph_contribution_rate for m in metrics]
        ),
        queries_with_any_graph_impact=impacted,
        graph_impact_rate=impacted / n,
    )


def _safe_avg(values: List[float]) -> float:
    """Average of a list, returning 0.0 for empty lists."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def assess_graph_edges(metrics: List[QueryMetrics]) -> Dict[str, Any]:
    """Assess graph edge density from telemetry metrics."""
    total_queries = len(metrics)
    total_seeds = sum(m.seed_count or 0 for m in metrics)
    total_candidates = sum(m.graph_candidates_expanded for m in metrics)
    queries_with_candidates = sum(
        1 for m in metrics if m.graph_candidates_expanded > 0
    )

    seed_scores = [
        m.seed_count for m in metrics if m.seed_count is not None and m.seed_count > 0
    ]

    return {
        "total_queries_analyzed": total_queries,
        "total_seeds_attempted": total_seeds,
        "total_candidates_found": total_candidates,
        "queries_with_graph_results": queries_with_candidates,
        "queries_with_graph_results_pct": (
            queries_with_candidates / total_queries * 100 if total_queries else 0.0
        ),
        "avg_seeds_per_query": _safe_avg(seed_scores) if seed_scores else 0.0,
        "edge_density_verdict": (
            "EMPTY"
            if total_candidates == 0
            else "SPARSE"
            if queries_with_candidates / max(total_queries, 1) < 0.1
            else "MODERATE"
            if queries_with_candidates / max(total_queries, 1) < 0.5
            else "HEALTHY"
        ),
        "latency_cost_ms_avg": _safe_avg([m.graph_ms for m in metrics]),
        "latency_cost_ms_p90": _percentile(
            sorted([m.graph_ms for m in metrics]), 0.90
        ),
    }


def _percentile(sorted_values: List[float], p: float) -> float:
    """Simple percentile calculation on pre-sorted list."""
    if not sorted_values:
        return 0.0
    idx = max(0, min(int(len(sorted_values) * p), len(sorted_values) - 1))
    return sorted_values[idx]


def generate_recommendations(
    edge_assessment: Dict[str, Any],
    config_summaries: List[ConfigSummary],
) -> List[str]:
    """Generate actionable recommendations based on analysis."""
    recs: List[str] = []
    verdict = edge_assessment.get("edge_density_verdict", "UNKNOWN")

    if verdict == "EMPTY":
        recs.append(
            "CRITICAL: Graph edges table appears empty. No graph candidates were "
            "expanded across any query. Before tuning weight/depth/decay parameters, "
            "the graph_edges table must be populated with document relationships."
        )
        recs.append(
            "The graph layer currently adds ~{:.0f}ms avg latency per query with "
            "zero quality contribution. Consider disabling graph until edges are "
            "populated (set enable_graph=False or graph_weight=0).".format(
                edge_assessment.get("latency_cost_ms_avg", 0)
            )
        )
        recs.append(
            "ACTION: Run a graph edge population pipeline to build relationships "
            "between documents and chunks. Potential edge types: 'contains' "
            "(project->doc->chunk), 'references' (citation links), 'related_to' "
            "(semantic similarity), 'cites' (bibliography references)."
        )
        recs.append(
            "Once edges exist, re-run this validation script to measure actual "
            "quality impact and tune parameters."
        )
    elif verdict == "SPARSE":
        recs.append(
            "Graph edges are sparse — only {:.1f}% of queries found graph candidates. "
            "Tuning parameters is premature; focus on expanding edge coverage first.".format(
                edge_assessment.get("queries_with_graph_results_pct", 0)
            )
        )
    else:
        best = max(config_summaries, key=lambda s: s.avg_result_share, default=None)
        if best and best.avg_result_share > 0:
            recs.append(
                f"Best performing config: {best.config_name} "
                f"(depth={best.graph_depth}, weight={best.graph_weight:.2f}, "
                f"decay={best.graph_decay:.1f}) with {best.avg_result_share:.1%} "
                f"avg result share."
            )

    # Config note (discrepancy resolved in T36.2/T36.4)
    recs.append(
        "NOTE: Code defaults (depth=2, decay=0.7, weight=0.12, seeds=10) are the "
        "authoritative graph config, validated by T36.2 quality proof against "
        "33,780 production edges."
    )

    return recs


def build_config_comparison(
    config_summaries: List[ConfigSummary],
) -> List[Dict[str, Any]]:
    """Build a comparison table across configurations."""
    rows: List[Dict[str, Any]] = []
    for s in config_summaries:
        rows.append(
            {
                "config": s.config_name,
                "queries": s.query_count,
                "depth": s.graph_depth,
                "weight": s.graph_weight,
                "decay": s.graph_decay,
                "seeds": s.graph_top_k_seeds,
                "avg_candidates": round(s.avg_graph_candidates, 2),
                "avg_results_with_graph": round(s.avg_results_with_graph, 2),
                "avg_result_share": round(s.avg_result_share, 4),
                "avg_top5_share": round(s.avg_top_5_share, 4),
                "impact_rate": round(s.graph_impact_rate, 4),
                "avg_graph_ms": round(s.avg_graph_ms, 2),
                "avg_total_ms": round(s.avg_total_ms, 2),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def analyze_telemetry(
    telemetry_paths: List[Path],
    include_raw: bool = False,
) -> QualityReport:
    """Main analysis pipeline for ANALYZE mode."""
    metrics = load_telemetry_events(telemetry_paths)

    # Group by config
    by_config: Dict[str, List[QueryMetrics]] = defaultdict(list)
    for m in metrics:
        by_config[m.config_name].append(m)

    summaries = [summarize_config(name, group) for name, group in by_config.items()]
    summaries.sort(key=lambda s: -s.query_count)

    edge_assessment = assess_graph_edges(metrics)
    recommendations = generate_recommendations(edge_assessment, summaries)
    comparison = build_config_comparison(summaries)

    files_analyzed = [str(p) for p in telemetry_paths if p.exists()]

    return QualityReport(
        generated_at=datetime.utcnow().isoformat() + "Z",
        mode="analyze",
        telemetry_files_analyzed=files_analyzed,
        total_events_analyzed=len(metrics),
        config_summaries=[asdict(s) for s in summaries],
        graph_edge_assessment=edge_assessment,
        recommendations=recommendations,
        config_comparison=comparison,
        raw_metrics=[asdict(m) for m in metrics] if include_raw else None,
    )


# ---------------------------------------------------------------------------
# Live comparison (LIVE mode)
# ---------------------------------------------------------------------------


def run_live_comparison(
    queries: List[str],
    configs: List[str],
    top_k: int = 10,
    verbose: bool = True,
) -> QualityReport:
    """Run live queries with multiple configs and compare results."""
    # Lazy import to avoid requiring database for analyze mode
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app.core.config import settings
    from app.services.pedr.search_orchestrator import create_pedr_orchestrator

    settings.pedr_cache_enabled = False
    orchestrator = create_pedr_orchestrator()

    all_metrics: List[QueryMetrics] = []
    results_by_query: Dict[str, Dict[str, List[str]]] = defaultdict(dict)

    for config_name in configs:
        cfg = GRAPH_CONFIGS.get(config_name)
        if cfg is None:
            print(f"Unknown config: {config_name}, skipping", file=sys.stderr)
            continue

        for idx, query in enumerate(queries, start=1):
            if verbose:
                print(f"[{config_name}] [{idx}/{len(queries)}] {query[:60]}")

            try:
                response = orchestrator.search(query=query, top_k=top_k, **cfg)
            except Exception as exc:
                print(f"  ERROR: {exc}", file=sys.stderr)
                continue

            chunk_ids = [
                str(r.chunk_id) for r in response.results if r.chunk_id
            ]
            results_by_query[query][config_name] = chunk_ids

            meta = response.metadata
            m = QueryMetrics(
                query=query,
                config_name=config_name,
                graph_depth=cfg.get("graph_depth", 0),
                graph_decay=cfg.get("graph_decay", 0.0),
                graph_weight=cfg.get("graph_weight", 0.0),
                graph_top_k_seeds=cfg.get("graph_top_k_seeds", 0),
                seed_count=None,
                total_candidates=meta.graph_candidates_expanded if hasattr(meta, "graph_candidates_expanded") else 0,
                graph_candidates_expanded=meta.graph_candidates_expanded if hasattr(meta, "graph_candidates_expanded") else 0,
                results_with_graph=sum(
                    1 for r in response.results if "graph" in (r.contributing_layers or [])
                ),
                result_share=0.0,
                top_5_with_graph=sum(
                    1
                    for r in response.results[:5]
                    if "graph" in (r.contributing_layers or [])
                ),
                top_5_share=0.0,
                graph_ms=meta.timings.graph_ms if hasattr(meta.timings, "graph_ms") else 0.0,
                fusion_ms=meta.timings.fusion_ms if hasattr(meta.timings, "fusion_ms") else 0.0,
                total_ms=meta.timings.total_ms if hasattr(meta.timings, "total_ms") else 0.0,
                layers_used=meta.layers_used or [],
                graph_contribution_rate=0.0,
                multi_layer_result_rate=0.0,
            )
            if response.results:
                m.result_share = m.results_with_graph / len(response.results)
                m.top_5_share = m.top_5_with_graph / min(5, len(response.results))

            all_metrics.append(m)

    # Build comparison including result-set overlap
    by_config: Dict[str, List[QueryMetrics]] = defaultdict(list)
    for m in all_metrics:
        by_config[m.config_name].append(m)

    summaries = [summarize_config(name, group) for name, group in by_config.items()]
    summaries.sort(key=lambda s: -s.query_count)

    edge_assessment = assess_graph_edges(all_metrics)
    recommendations = generate_recommendations(edge_assessment, summaries)
    comparison = build_config_comparison(summaries)

    # Add result-set overlap analysis
    overlap_analysis = _compute_result_overlap(results_by_query, configs)
    if overlap_analysis:
        comparison.append({"result_overlap_analysis": overlap_analysis})

    return QualityReport(
        generated_at=datetime.utcnow().isoformat() + "Z",
        mode="live",
        telemetry_files_analyzed=[],
        total_events_analyzed=len(all_metrics),
        config_summaries=[asdict(s) for s in summaries],
        graph_edge_assessment=edge_assessment,
        recommendations=recommendations,
        config_comparison=comparison,
        raw_metrics=[asdict(m) for m in all_metrics],
    )


def _compute_result_overlap(
    results_by_query: Dict[str, Dict[str, List[str]]],
    configs: List[str],
) -> List[Dict[str, Any]]:
    """Compute Jaccard similarity between disabled and enabled configs."""
    if "disabled" not in configs:
        return []

    overlaps: List[Dict[str, Any]] = []
    for query, config_results in results_by_query.items():
        baseline = set(config_results.get("disabled", []))
        if not baseline:
            continue

        for config_name, results in config_results.items():
            if config_name == "disabled":
                continue
            enabled_set = set(results)
            intersection = baseline & enabled_set
            union = baseline | enabled_set
            jaccard = len(intersection) / len(union) if union else 1.0
            unique_from_graph = enabled_set - baseline

            overlaps.append(
                {
                    "query": query[:80],
                    "config": config_name,
                    "baseline_results": len(baseline),
                    "enabled_results": len(enabled_set),
                    "shared_results": len(intersection),
                    "unique_from_graph": len(unique_from_graph),
                    "jaccard_similarity": round(jaccard, 4),
                }
            )
    return overlaps


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Graph L6 quality validation and comparison report."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live comparison mode (requires database)",
    )
    parser.add_argument(
        "--telemetry-files",
        type=Path,
        nargs="+",
        default=None,
        help="JSONL telemetry files to analyze (analyze mode)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output report path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--queries",
        type=str,
        default=None,
        help="Comma-separated query list for live mode",
    )
    parser.add_argument(
        "--configs",
        type=str,
        default="disabled,default,sprint25_original,aggressive,conservative",
        help="Comma-separated config names for live mode",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top-K results per query (live mode)",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Include raw per-query metrics in report",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.live:
        if not args.queries:
            print("--queries required for live mode", file=sys.stderr)
            return 1
        queries = [q.strip() for q in args.queries.split(",") if q.strip()]
        configs = [c.strip() for c in args.configs.split(",") if c.strip()]
        report = run_live_comparison(
            queries=queries,
            configs=configs,
            top_k=args.top_k,
            verbose=not args.quiet,
        )
    else:
        telemetry_paths = args.telemetry_files or [
            Path(p) for p in DEFAULT_TELEMETRY_FILES
        ]
        report = analyze_telemetry(
            telemetry_paths=telemetry_paths,
            include_raw=args.include_raw,
        )

    # Write report
    report_dict = asdict(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report_dict, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    # Print summary to stdout
    print(f"\n{'='*70}")
    print("GRAPH L6 QUALITY VALIDATION REPORT")
    print(f"{'='*70}")
    print(f"Mode: {report.mode}")
    print(f"Events analyzed: {report.total_events_analyzed}")
    print(f"Generated: {report.generated_at}")
    print()

    edge = report.graph_edge_assessment
    print(f"Graph Edge Assessment: {edge['edge_density_verdict']}")
    print(f"  Total seeds attempted: {edge['total_seeds_attempted']}")
    print(f"  Total candidates found: {edge['total_candidates_found']}")
    print(f"  Queries with results: {edge['queries_with_graph_results']}/{edge['total_queries_analyzed']} ({edge['queries_with_graph_results_pct']:.1f}%)")
    print(f"  Avg latency cost: {edge['latency_cost_ms_avg']:.1f}ms")
    print()

    print("Configuration Comparison:")
    print(f"{'Config':<25} {'Queries':>7} {'Impact%':>8} {'AvgGraphMS':>10} {'AvgTotalMS':>10}")
    print("-" * 65)
    for row in report.config_comparison:
        if isinstance(row, dict) and "config" in row:
            print(
                f"{row['config']:<25} {row.get('queries', 0):>7} "
                f"{row.get('impact_rate', 0)*100:>7.1f}% "
                f"{row.get('avg_graph_ms', 0):>10.1f} "
                f"{row.get('avg_total_ms', 0):>10.1f}"
            )
    print()

    print("Recommendations:")
    for i, rec in enumerate(report.recommendations, 1):
        print(f"  {i}. {rec}")
    print()

    print(f"Full report written to: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
