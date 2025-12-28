#!/usr/bin/env python3
"""Run PEDR offline benchmarks, track history, and detect regressions."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts import pedr_validation_benchmark as pvb  # noqa: E402
from scripts import rag_baseline_benchmark as rbb  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_PATH = PROJECT_ROOT / "telemetry/events/benchmark-history.jsonl"
DEFAULT_REGRESSION_BASELINE_PATH = PROJECT_ROOT / "telemetry/events/benchmark-baseline.json"
DEFAULT_COMPARISON_OUTPUT = (
    PROJECT_ROOT / "telemetry/events/.artifacts/pedr-benchmark-comparison.json"
)
DEFAULT_REGRESSION_THRESHOLD = 0.05


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_metrics(summary: Dict[str, Any]) -> Dict[str, float]:
    return {
        "precision_at_k": float(summary.get("precision_at_k", 0.0)),
        "recall_at_k": float(summary.get("recall_at_k", 0.0)),
        "ndcg_at_k": float(summary.get("ndcg_at_k", 0.0)),
    }


def compare_metrics(
    *,
    current: Dict[str, float],
    baseline: Dict[str, float],
    threshold: float,
) -> Dict[str, Any]:
    deltas: Dict[str, float] = {}
    pct_changes: Dict[str, Optional[float]] = {}
    for key, current_value in current.items():
        baseline_value = baseline.get(key, 0.0)
        deltas[key] = current_value - baseline_value
        pct_changes[key] = (deltas[key] / baseline_value) if baseline_value else None

    ndcg_baseline = baseline.get("ndcg_at_k", 0.0)
    regression_alert = bool(
        ndcg_baseline and current.get("ndcg_at_k", 0.0) < ndcg_baseline * (1 - threshold)
    )
    return {
        "baseline": baseline,
        "current": current,
        "delta": deltas,
        "pct_change": pct_changes,
        "regression_alert": regression_alert,
        "threshold": threshold,
    }


def build_baseline_payload(
    *,
    metrics: Dict[str, float],
    benchmark: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "generated_at": _now_iso(),
        "metrics": metrics,
        "benchmark": benchmark,
        "config": config,
    }


def append_history(path: Path, entry: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def ensure_corpus(corpus_dir: Path, *, rebuild: bool) -> Dict[str, Any]:
    manifest_path = corpus_dir / "corpus_manifest.json"
    if rebuild or not manifest_path.exists():
        return rbb.build_corpus(corpus_dir, sources=rbb.SOURCE_DOCS, overwrite=True)
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def ensure_queries(
    queries_path: Path,
    *,
    rebuild: bool,
    top_k: int,
) -> Dict[str, Any]:
    if rebuild or not queries_path.exists():
        return rbb.write_queries(queries_path, sources=rbb.SOURCE_DOCS, top_k=top_k)
    return json.loads(queries_path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run PEDR benchmark, append history, and detect regressions."
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=rbb.DEFAULT_CORPUS_DIR,
        help="Benchmark corpus directory.",
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=rbb.DEFAULT_QUERIES_PATH,
        help="Benchmark queries JSON path.",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY_PATH,
        help="History JSONL path.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_REGRESSION_BASELINE_PATH,
        help="Regression baseline JSON path.",
    )
    parser.add_argument(
        "--comparison-output",
        type=Path,
        default=DEFAULT_COMPARISON_OUTPUT,
        help="Comparison output JSON path.",
    )
    parser.add_argument(
        "--regression-threshold",
        type=float,
        default=DEFAULT_REGRESSION_THRESHOLD,
        help="Regression threshold for nDCG drop (default: 0.05).",
    )
    parser.add_argument(
        "--rebuild-corpus",
        action="store_true",
        help="Regenerate corpus documents and manifest before running.",
    )
    parser.add_argument(
        "--rebuild-queries",
        action="store_true",
        help="Regenerate queries JSON before running.",
    )
    parser.add_argument(
        "--rebuild-baseline",
        action="store_true",
        help="Regenerate baseline (rag/hybrid) metrics before running.",
    )
    parser.add_argument(
        "--init-baseline",
        action="store_true",
        help="Write regression baseline if missing.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite regression baseline with current metrics.",
    )
    parser.add_argument(
        "--metadata-source",
        choices=["synthetic", "postgres"],
        default="synthetic",
        help="Quality metadata source (default: synthetic).",
    )
    parser.add_argument(
        "--mission-map",
        type=Path,
        default=pvb.DEFAULT_MISSION_MAP_PATH,
        help="Doc-to-mission mapping JSON for postgres metadata.",
    )
    parser.add_argument(
        "--governance-mode",
        default=pvb.DEFAULT_GOVERNANCE_MODE,
        help="Governance mode for PEDR scoring.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=pvb.DEFAULT_TOP_K,
        help="Top-K results to evaluate.",
    )
    parser.add_argument(
        "--semantic-weight",
        type=float,
        default=pvb.DEFAULT_SEMANTIC_WEIGHT,
        help="Semantic weight for hybrid baseline.",
    )
    parser.add_argument(
        "--keyword-weight",
        type=float,
        default=pvb.DEFAULT_KEYWORD_WEIGHT,
        help="Keyword weight for hybrid baseline.",
    )
    parser.add_argument(
        "--candidate-multiplier",
        type=int,
        default=pvb.DEFAULT_CANDIDATE_MULTIPLIER,
        help="Candidate multiplier for PEDR ranking.",
    )
    parser.add_argument(
        "--rebuild-metadata",
        action="store_true",
        help="Rebuild quality metadata mapping for the corpus.",
    )
    parser.add_argument(
        "--rebuild-relationships",
        action="store_true",
        help="Rebuild relationship mapping for the corpus.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=pvb.DEFAULT_OUTPUT_PATH,
        help="Output path for detailed PEDR benchmark JSON.",
    )
    parser.add_argument(
        "--comparison-md",
        type=Path,
        default=pvb.DEFAULT_COMPARISON_MD,
        help="Output path for PEDR vs baseline comparison markdown.",
    )
    parser.add_argument(
        "--baseline-metrics",
        type=Path,
        default=pvb.DEFAULT_BASELINE_METRICS_PATH,
        help="Output path for baseline (rag/hybrid) metrics JSON.",
    )

    args = parser.parse_args()

    manifest = ensure_corpus(args.corpus_dir, rebuild=args.rebuild_corpus)
    queries_payload = ensure_queries(
        args.queries, rebuild=args.rebuild_queries, top_k=args.top_k
    )

    if args.rebuild_baseline or not args.baseline_metrics.exists():
        rbb.run_benchmark(
            corpus_dir=args.corpus_dir,
            queries_path=args.queries,
            output_path=args.baseline_metrics,
            top_k=args.top_k,
            semantic_weight=args.semantic_weight,
            keyword_weight=args.keyword_weight,
        )

    pedr_output = pvb.run_benchmark(
        corpus_dir=args.corpus_dir,
        queries_path=args.queries,
        output_path=args.output,
        comparison_path=args.comparison_md,
        baseline_metrics_path=args.baseline_metrics,
        top_k=args.top_k,
        semantic_weight=args.semantic_weight,
        keyword_weight=args.keyword_weight,
        candidate_multiplier=args.candidate_multiplier,
        metadata_source=args.metadata_source,
        mission_map_path=args.mission_map,
        governance_mode=args.governance_mode,
        rebuild_metadata=args.rebuild_metadata,
        rebuild_relationships=args.rebuild_relationships,
    )

    pedr_summary = pedr_output["pedr_results"]["pedr_quality"]["summary"]
    current_metrics = _extract_metrics(pedr_summary)

    baseline_payload = _load_json(args.baseline)
    if args.update_baseline or (baseline_payload is None and args.init_baseline):
        baseline_payload = build_baseline_payload(
            metrics=current_metrics,
            benchmark=pedr_output["benchmark"],
            config={
                "candidate_multiplier": args.candidate_multiplier,
                "governance_mode": args.governance_mode,
                "metadata_source": args.metadata_source,
                "top_k": args.top_k,
                "semantic_weight": args.semantic_weight,
                "keyword_weight": args.keyword_weight,
            },
        )
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(
            json.dumps(baseline_payload, indent=2), encoding="utf-8"
        )

    baseline_metrics: Dict[str, float] = {}
    if baseline_payload:
        baseline_metrics = baseline_payload.get("metrics", {})

    comparison = (
        compare_metrics(
            current=current_metrics,
            baseline=baseline_metrics,
            threshold=args.regression_threshold,
        )
        if baseline_metrics
        else {
            "baseline": {},
            "current": current_metrics,
            "delta": {},
            "pct_change": {},
            "regression_alert": False,
            "threshold": args.regression_threshold,
            "baseline_missing": True,
        }
    )

    args.comparison_output.parent.mkdir(parents=True, exist_ok=True)
    args.comparison_output.write_text(
        json.dumps(
            {
                "generated_at": _now_iso(),
                "comparison": comparison,
                "benchmark": pedr_output["benchmark"],
                "baseline_summary": pedr_output["baseline_comparison"]["baseline_summary"],
                "pedr_summary": pedr_summary,
                "quality_boost_analysis": pedr_output["quality_boost_analysis"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    history_entry = {
        "ts": _now_iso(),
        "metrics": current_metrics,
        "comparison": comparison,
        "benchmark": pedr_output["benchmark"],
        "config": {
            "candidate_multiplier": args.candidate_multiplier,
            "governance_mode": args.governance_mode,
            "metadata_source": args.metadata_source,
            "top_k": args.top_k,
            "semantic_weight": args.semantic_weight,
            "keyword_weight": args.keyword_weight,
        },
        "corpus": {
            "manifest_path": str(args.corpus_dir / "corpus_manifest.json"),
            "queries_path": str(args.queries),
            "doc_count": manifest.get("document_count"),
            "query_count": len(queries_payload.get("queries", [])),
        },
    }
    append_history(args.history, history_entry)

    print("PEDR benchmark summary:")
    print(f"  Precision@{args.top_k}: {current_metrics['precision_at_k']:.3f}")
    print(f"  Recall@{args.top_k}:    {current_metrics['recall_at_k']:.3f}")
    print(f"  nDCG@{args.top_k}:      {current_metrics['ndcg_at_k']:.3f}")

    if comparison.get("baseline_missing"):
        print("  Baseline missing; run with --init-baseline to set one.")
        return 1

    if comparison.get("regression_alert"):
        print(
            "  WARNING: Regression detected (nDCG drop exceeds threshold)."
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
