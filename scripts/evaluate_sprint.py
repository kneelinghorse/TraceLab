#!/usr/bin/env python3
"""
Sprint Efficacy Evaluator (B1.6 & B2.5)

Evaluates sprint missions against their success criteria and produces planning feedback.
Consumes mission metadata (backlog.yaml, mission YAMLs) and telemetry artifacts.
Generates Markdown/JSON report highlighting met vs unmet targets and recommended follow-ups.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKLOG_PATH = REPO_ROOT / "cmos" / "missions" / "backlog.yaml"


def load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML file. Handles multi-document YAML by taking the mission document."""
    with open(path, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
        for doc in docs:
            if doc and isinstance(doc, dict) and ("missionId" in doc or "domainFields" in doc):
                return doc
        return docs[-1] if docs else {}


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON file, return None if missing."""
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_sprint_missions(backlog: Dict[str, Any], sprint_id: str) -> List[Dict[str, Any]]:
    """Extract missions for a specific sprint."""
    for sprint in backlog.get("domainFields", {}).get("sprints", []):
        if sprint.get("sprintId") == sprint_id:
            return sprint.get("missions", [])
    return []


def evaluate_presidio_metric(
    baseline: Optional[Dict[str, Any]],
    tuned: Optional[Dict[str, Any]],
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Evaluate: Presidio recall ≥ 0.95 on synthetic corpus priority entities.

    Priority entities: PARTICIPANT_ID, PROJECT_ID, EMAIL_ADDRESS, PHONE_NUMBER, PERSON
    """
    if not tuned:
        return False, "presidio_tuned_results.json missing", {}

    priority_entities = ["PARTICIPANT_ID", "PROJECT_ID", "EMAIL_ADDRESS", "PHONE_NUMBER", "PERSON"]
    per_entity = tuned.get("per_entity_metrics", {})

    results = {}
    min_recall = 1.0

    for entity in priority_entities:
        if entity in per_entity:
            recall = per_entity[entity].get("recall", 0.0)
            results[entity] = {"recall": recall, "met": recall >= 0.95}
            min_recall = min(min_recall, recall)
        else:
            results[entity] = {"recall": None, "met": False, "note": "Entity not found in metrics"}
            min_recall = 0.0

    met = min_recall >= 0.95
    details = {
        "min_recall": min_recall,
        "target": 0.95,
        "per_entity": results,
        "overall_recall": tuned.get("tuned_metrics", {}).get("overall", {}).get("recall", 0.0),
    }

    return met, f"Min priority entity recall: {min_recall:.4f} (target: ≥0.95)", details


def evaluate_ingestion_metric(coverage: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Evaluate: Five priority formats ingested end-to-end with sanitized chunks in PostgreSQL.

    Priority formats: PDF, DOCX, PPTX, CSV, XLSX
    """
    if not coverage:
        return False, "ingestion_format_coverage.json missing", {}

    priority_formats = ["PDF", "DOCX", "PPTX", "CSV", "XLSX"]
    formats_data = coverage.get("formats", {})

    results = {}
    success_count = 0

    for fmt in priority_formats:
        if fmt in formats_data:
            fmt_data = formats_data[fmt]
            total = fmt_data.get("total_uploaded", 0)
            chunked = fmt_data.get("chunked", 0)
            success = total > 0 and chunked > 0
            results[fmt] = {"total_uploaded": total, "chunked": chunked, "met": success}
            if success:
                success_count += 1
        else:
            results[fmt] = {
                "total_uploaded": 0,
                "chunked": 0,
                "met": False,
                "note": "Format not found in coverage report",
            }

    met = success_count >= 5
    details = {"formats_met": success_count, "target": 5, "per_format": results}

    return met, f"{success_count}/5 priority formats successfully ingested and chunked", details


def evaluate_qdrant_metric(performance: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
    """Evaluate: Embedding pipeline stores ≥1 sample project in Qdrant with <10ms p99 query latency (local)."""
    if not performance:
        return False, "qdrant_performance.json missing", {}

    collection_info = performance.get("collection_info", {})
    points_count = collection_info.get("points_count", 0)

    query_latency = performance.get("query_latency", [])
    p99_latency = None

    if query_latency:
        latencies = [q.get("latency_ms", 0) for q in query_latency]
        p99_latency = max(latencies) if latencies else None

    has_data = points_count >= 1
    latency_met = p99_latency is not None and p99_latency < 10.0

    met = has_data and latency_met

    details = {
        "points_count": points_count,
        "target_points": 1,
        "query_latencies": query_latency,
        "max_latency_ms": p99_latency,
        "target_latency_ms": 10.0,
        "has_data": has_data,
        "latency_met": latency_met,
    }

    status_parts = []
    if not has_data:
        status_parts.append(f"Points stored: {points_count} (need ≥1)")
    if p99_latency is None:
        status_parts.append("Query latency data missing")
    elif not latency_met:
        status_parts.append(f"Max latency: {p99_latency:.2f}ms (target: <10ms)")
    else:
        status_parts.append(f"✓ {points_count} points stored, max latency {p99_latency:.2f}ms")

    return met, " | ".join(status_parts), details


def evaluate_script_metric() -> Tuple[bool, str, Dict[str, Any]]:
    """Evaluate: Sprint evaluation script executes and produces retrospective report."""
    return True, "Script executed successfully", {}


def evaluate_rag_query_metric(metrics: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
    """Evaluate Sprint 02 RAG query accuracy and citation coverage."""
    if not metrics:
        return False, "rag_query_metrics.json missing", {}

    total_queries = metrics.get("queries_evaluated", 0)
    if total_queries == 0:
        return False, "No RAG query evaluations recorded", metrics

    recall = metrics.get("relevant_chunk_recall", 0.0)
    answers_with_citations = metrics.get("answers_with_citations", 0)
    citation_rate = answers_with_citations / total_queries

    met = recall >= 0.95 and citation_rate >= 0.95
    status = (
        f"Relevant chunk recall {recall:.1%}, citations on {answers_with_citations}/{total_queries} "
        f"queries ({citation_rate:.1%})"
    )

    details = {
        "total_queries": total_queries,
        "relevant_chunk_recall": recall,
        "answers_with_citations": answers_with_citations,
        "citation_rate": citation_rate,
        "failed_queries": metrics.get("failed_queries", []),
    }

    return met, status, details


def evaluate_context_compression_metric(metrics: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
    """Evaluate Sprint 02 context compression reduction targets."""
    if not metrics:
        return False, "context_compression_metrics.json missing", {}

    baseline = metrics.get("baseline_tokens_avg", 0)
    compressed = metrics.get("compressed_tokens_avg", 0)
    if baseline <= 0 or compressed <= 0:
        return False, "Invalid token averages recorded", metrics

    reduction = 1 - (compressed / baseline)
    target_low, target_high = 0.60, 0.70
    within_range = target_low <= reduction <= target_high

    status = (
        f"Average reduction {reduction:.1%} "
        f"(baseline {baseline:.0f} tokens → compressed {compressed:.0f} tokens)"
    )

    details = {
        "baseline_tokens_avg": baseline,
        "compressed_tokens_avg": compressed,
        "reduction": reduction,
        "samples": metrics.get("compression_samples"),
        "distribution": metrics.get("token_reduction_distribution", {}),
        "target_range": {"min": target_low, "max": target_high},
    }

    return within_range, status, details


def evaluate_semantic_cache_metric(metrics: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
    """Evaluate Sprint 02 semantic cache hit rate target."""
    if not metrics:
        return False, "semantic_cache_metrics.json missing", {}

    hit_rate = metrics.get("hit_rate", 0.0)
    met = hit_rate >= 0.15
    status = f"Cache hit rate {hit_rate:.1%} (target ≥15%)"

    details = {
        "queries_total": metrics.get("queries_total"),
        "cache_hits": metrics.get("cache_hits"),
        "cache_misses": metrics.get("cache_misses"),
        "hit_rate": hit_rate,
        "target": 0.15,
        "observation_window": metrics.get("observation_window"),
    }

    return met, status, details


def evaluate_tiered_routing_metric(metrics: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
    """Evaluate Sprint 02 tiered routing escalation rate."""
    if not metrics:
        return False, "tiered_routing_metrics.json missing", {}

    escalation_rate = metrics.get("escalation_rate", 1.0)
    met = escalation_rate < 0.10
    status = f"Escalation rate {escalation_rate:.1%} (target <10%)"

    details = {
        "total_queries": metrics.get("total_queries"),
        "fallback_queries": metrics.get("fallback_queries"),
        "escalation_rate": escalation_rate,
        "primary_model": metrics.get("primary_model"),
        "fallback_model": metrics.get("fallback_model"),
    }

    return met, status, details


def evaluate_cost_metric(metrics: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
    """Evaluate Sprint 02 cost per query target."""
    if not metrics:
        return False, "cost_metrics.json missing", {}

    avg_cost = metrics.get("average_cost_per_query", 1.0)
    met = avg_cost < 0.0003
    status = f"Average cost per query ${avg_cost:.6f} (target <$0.0003)"

    details = {
        "total_queries": metrics.get("total_queries"),
        "total_cost_usd": metrics.get("total_cost_usd"),
        "average_cost_per_query": avg_cost,
        "cost_components": metrics.get("cost_components", {}),
    }

    return met, status, details


def evaluate_latency_metric(metrics: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
    """Evaluate Sprint 02 RAG query latency targets."""
    if not metrics:
        return False, "query_latency_metrics.json missing", {}

    p95_latency = metrics.get("p95_latency_seconds")
    if p95_latency is None:
        return False, "p95 latency not recorded", metrics

    met = p95_latency <= 5.0
    status = f"P95 latency {p95_latency:.2f}s (target ≤5s)"

    details = {
        "p50_latency_seconds": metrics.get("p50_latency_seconds"),
        "p95_latency_seconds": p95_latency,
        "p99_latency_seconds": metrics.get("p99_latency_seconds"),
        "max_latency_seconds": metrics.get("max_latency_seconds"),
        "samples": metrics.get("samples"),
    }

    return met, status, details


def generate_report(
    sprint_id: str,
    missions: List[Dict[str, Any]],
    evaluations: List[Tuple[str, bool, str, Dict[str, Any]]],
    output_dir: Path,
) -> Path:
    """Generate Markdown report for a sprint."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{sprint_id.lower().replace(' ', '-')}-summary.md"

    timestamp = datetime.utcnow().isoformat() + "Z"

    lines = [
        f"# {sprint_id} Efficacy Report",
        "",
        f"**Generated:** {timestamp}",
        "",
        "## Executive Summary",
        "",
    ]

    met_count = sum(1 for _, met, _, _ in evaluations if met)
    total_count = len(evaluations)

    lines.append(f"- **Metrics Met:** {met_count}/{total_count}")
    lines.append(f"- **Metrics Unmet:** {total_count - met_count}/{total_count}")
    lines.append("")

    completed = [m for m in missions if m.get("status") == "Completed"]
    in_progress = [m for m in missions if m.get("status") == "In Progress"]
    current = [m for m in missions if m.get("status") == "Current"]
    queued = [m for m in missions if m.get("status") == "Queued"]

    lines.extend(
        [
            "## Mission Status",
            "",
            f"- **Completed:** {len(completed)}",
            f"- **In Progress:** {len(in_progress)}",
            f"- **Current:** {len(current)}",
            f"- **Queued:** {len(queued)}",
            "",
        ]
    )

    lines.extend(["## Success Criteria Evaluation", ""])

    for metric_text, met, status, details in evaluations:
        status_icon = "✅" if met else "❌"
        lines.append(f"### {status_icon} {metric_text}")
        lines.append("")
        lines.append(f"**Status:** {status}")
        lines.append("")

        if details:
            lines.append("**Details:**")
            lines.append("```json")
            lines.append(json.dumps(details, indent=2))
            lines.append("```")
            lines.append("")

    lines.extend(["## Recommendations", ""])

    unmet = [(metric, status, details) for metric, met, status, details in evaluations if not met]

    if not unmet:
        lines.append("- ✅ All success criteria met. Sprint objectives achieved.")
    else:
        lines.append("### Unmet Criteria:")
        for metric, status, details in unmet:
            lines.append(f"- **{metric}**")
            lines.append(f"  - Status: {status}")
            if details:
                if "recall" in str(details):
                    lines.append("  - Tune recognizers or adjust thresholds for better recall")
                if "formats" in str(details):
                    lines.append("  - Ensure all priority formats have ingestion coverage")
                if "latency" in str(details):
                    lines.append("  - Review latency contributors (cache, routing, embeddings)")
                if "cost" in str(details):
                    lines.append("  - Investigate high-cost components and optimize usage")

    lines.append("")

    lines.extend(["## Mission Completion Summary", ""])

    for mission in missions:
        mission_id = mission.get("id", "Unknown")
        mission_name = mission.get("name", "Unknown")
        status = mission.get("status", "Unknown")
        completed_at = mission.get("completed_at", "")
        notes = mission.get("notes", "")

        lines.append(f"### {mission_id}: {mission_name}")
        lines.append(f"- **Status:** {status}")
        if completed_at:
            lines.append(f"- **Completed:** {completed_at}")
        if notes:
            lines.append(f"- **Notes:** {notes}")
        lines.append("")

    report_content = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    return report_path


def _format_artifact_key(key: str) -> str:
    """Present telemetry key names nicely for CLI status output."""
    return key.replace("_", " ").title()


SPRINT_CONFIG = {
    "Sprint 01": {
        "reports_dir": REPO_ROOT / "cmos" / "reports" / "sprint-01",
        "missions_dir": REPO_ROOT / "cmos" / "missions" / "sprint-01",
        "telemetry_paths": {
            "presidio_baseline": REPO_ROOT / "cmos" / "reports" / "sprint-01" / "presidio_corpus_baseline.json",
            "presidio_tuned": REPO_ROOT / "cmos" / "reports" / "sprint-01" / "presidio_tuned_results.json",
            "ingestion_coverage": REPO_ROOT / "cmos" / "reports" / "sprint-01" / "ingestion_format_coverage.json",
            "qdrant_performance": REPO_ROOT / "cmos" / "reports" / "sprint-01" / "qdrant_performance.json",
        },
        "evaluations": [
            {
                "metric": "Sprint 1: Presidio recall ≥ 0.95 on synthetic corpus priority entities.",
                "func": evaluate_presidio_metric,
                "inputs": ["presidio_baseline", "presidio_tuned"],
            },
            {
                "metric": "Sprint 1: Five priority formats ingested end-to-end with sanitized chunks in PostgreSQL.",
                "func": evaluate_ingestion_metric,
                "inputs": ["ingestion_coverage"],
            },
            {
                "metric": "Sprint 1: Embedding pipeline stores ≥1 sample project in Qdrant with <10ms p99 query latency (local).",
                "func": evaluate_qdrant_metric,
                "inputs": ["qdrant_performance"],
            },
            {
                "metric": "Sprint 1: Sprint evaluation script executes and produces retrospective report in `cmos/reports/`.",
                "func": evaluate_script_metric,
                "inputs": [],
            },
        ],
    },
    "Sprint 02": {
        "reports_dir": REPO_ROOT / "cmos" / "reports" / "sprint-02",
        "missions_dir": REPO_ROOT / "cmos" / "missions" / "sprint-02",
        "telemetry_paths": {
            "rag_query_metrics": REPO_ROOT / "cmos" / "reports" / "sprint-02" / "rag_query_metrics.json",
            "context_compression_metrics": REPO_ROOT / "cmos" / "reports" / "sprint-02" / "context_compression_metrics.json",
            "semantic_cache_metrics": REPO_ROOT / "cmos" / "reports" / "sprint-02" / "semantic_cache_metrics.json",
            "tiered_routing_metrics": REPO_ROOT / "cmos" / "reports" / "sprint-02" / "tiered_routing_metrics.json",
            "cost_metrics": REPO_ROOT / "cmos" / "reports" / "sprint-02" / "cost_metrics.json",
            "query_latency_metrics": REPO_ROOT / "cmos" / "reports" / "sprint-02" / "query_latency_metrics.json",
        },
        "evaluations": [
            {
                "metric": "Sprint 2: RAG query API successfully retrieves relevant chunks and generates answers with citations.",
                "func": evaluate_rag_query_metric,
                "inputs": ["rag_query_metrics"],
            },
            {
                "metric": "Sprint 2: Context compression reduces input tokens by 60-70% (from ~3000 to ~1000 tokens).",
                "func": evaluate_context_compression_metric,
                "inputs": ["context_compression_metrics"],
            },
            {
                "metric": "Sprint 2: Semantic cache achieves hit rate ≥ 15% (target 15-20%).",
                "func": evaluate_semantic_cache_metric,
                "inputs": ["semantic_cache_metrics"],
            },
            {
                "metric": "Sprint 2: Tiered routing escalation rate < 10% (90%+ queries handled by GPT-4o-mini).",
                "func": evaluate_tiered_routing_metric,
                "inputs": ["tiered_routing_metrics"],
            },
            {
                "metric": "Sprint 2: Average cost per query < $0.0003 (with all optimizations applied).",
                "func": evaluate_cost_metric,
                "inputs": ["cost_metrics"],
            },
            {
                "metric": "Sprint 2: Query latency < 5 seconds end-to-end for RAG queries.",
                "func": evaluate_latency_metric,
                "inputs": ["query_latency_metrics"],
            },
            {
                "metric": "Sprint 2: Sprint evaluation script executes and produces retrospective report in `cmos/reports/sprint-02/`.",
                "func": evaluate_script_metric,
                "inputs": [],
            },
        ],
    },
}


def main() -> None:
    """Main evaluation workflow."""
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate sprint missions against success criteria")
    parser.add_argument("--sprint", type=int, default=1, help="Sprint number to evaluate (default: 1)")
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    args = parser.parse_args()
    sprint_id = f"Sprint {args.sprint:02d}"

    if sprint_id not in SPRINT_CONFIG:
        available = ", ".join(sorted(SPRINT_CONFIG))
        raise SystemExit(f"Unsupported sprint '{sprint_id}'. Supported sprints: {available}")

    config = SPRINT_CONFIG[sprint_id]

    print(f"Evaluating {sprint_id}...")

    backlog = load_yaml(BACKLOG_PATH)
    missions = extract_sprint_missions(backlog, sprint_id)
    print(f"Found {len(missions)} missions for {sprint_id}")

    telemetry_data: Dict[str, Optional[Dict[str, Any]]] = {}
    print("Loaded telemetry artifacts:")
    for key, path in config.get("telemetry_paths", {}).items():
        data = load_json(path)
        telemetry_data[key] = data
        status_icon = "✓" if data is not None else "✗"
        relative_path = path.relative_to(REPO_ROOT)
        print(f"  - {_format_artifact_key(key)}: {status_icon} ({relative_path})")

    evaluations: List[Tuple[str, bool, str, Dict[str, Any]]] = []
    for evaluation in config["evaluations"]:
        metric = evaluation["metric"]
        func = evaluation["func"]
        input_keys = evaluation.get("inputs", [])
        inputs = [telemetry_data.get(key) for key in input_keys]
        met, status, details = func(*inputs)
        evaluations.append((metric, met, status, details))

    reports_dir = config["reports_dir"]

    if args.format == "markdown":
        report_path = generate_report(sprint_id, missions, evaluations, reports_dir)
        print(f"\n✅ Report generated: {report_path}")
    else:
        report_data = {
            "sprint": sprint_id,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "evaluations": [
                {"metric": metric, "met": met, "status": status, "details": details}
                for metric, met, status, details in evaluations
            ],
            "mission_summary": {
                "total": len(missions),
                "completed": len([m for m in missions if m.get("status") == "Completed"]),
                "in_progress": len([m for m in missions if m.get("status") == "In Progress"]),
                "current": len([m for m in missions if m.get("status") == "Current"]),
                "queued": len([m for m in missions if m.get("status") == "Queued"]),
            },
        }
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"{sprint_id.lower().replace(' ', '-')}-summary.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        print(f"\n✅ Report generated: {report_path}")

    print("\n" + "=" * 60)
    print("Evaluation Summary")
    print("=" * 60)
    met_count = sum(1 for _, met, _, _ in evaluations if met)
    print(f"Metrics Met: {met_count}/{len(evaluations)}")
    for metric, met, status, _ in evaluations:
        icon = "✅" if met else "❌"
        print(f"  {icon} {metric}")
        print(f"     {status}")


if __name__ == "__main__":
    main()

