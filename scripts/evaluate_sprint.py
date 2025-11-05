#!/usr/bin/env python3
"""
Sprint Efficacy Evaluator (B1.6)

Evaluates sprint missions against their success criteria and produces planning feedback.
Consumes mission metadata (backlog.yaml, mission YAMLs) and telemetry artifacts.
Generates Markdown/JSON report highlighting met vs unmet targets and recommended follow-ups.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import yaml


# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKLOG_PATH = REPO_ROOT / "cmos" / "missions" / "backlog.yaml"
REPORTS_DIR = REPO_ROOT / "cmos" / "reports" / "sprint-01"
SPRINT_MISSIONS_DIR = REPO_ROOT / "cmos" / "missions" / "sprint-01"

# Artifact paths
PRESIDIO_BASELINE = REPO_ROOT / "cmos" / "reports" / "sprint-01" / "presidio_corpus_baseline.json"
PRESIDIO_TUNED = REPO_ROOT / "cmos" / "reports" / "sprint-01" / "presidio_tuned_results.json"
INGESTION_COVERAGE = REPO_ROOT / "cmos" / "reports" / "sprint-01" / "ingestion_format_coverage.json"
QDRANT_PERFORMANCE = REPO_ROOT / "cmos" / "reports" / "sprint-01" / "qdrant_performance.json"

# Success criteria from backlog.yaml
SUCCESS_METRICS = {
    "Sprint 1": [
        "Presidio recall ≥ 0.95 on synthetic corpus priority entities.",
        "Five priority formats ingested end-to-end with sanitized chunks in PostgreSQL.",
        "Embedding pipeline stores ≥1 sample project in Qdrant with <10ms p99 query latency (local).",
        "Sprint evaluation script executes and produces retrospective report in `cmos/reports/`."
    ]
}


def load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML file. Handles multi-document YAML by taking the mission document."""
    with open(path, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
        # Find the mission document (the one with missionId or domainFields)
        for doc in docs:
            if doc and (isinstance(doc, dict) and ("missionId" in doc or "domainFields" in doc)):
                return doc
        # Fallback to last document if no mission found
        return docs[-1] if docs else {}


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON file, return None if missing."""
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_sprint_missions(backlog: Dict[str, Any], sprint_id: str) -> List[Dict[str, Any]]:
    """Extract missions for a specific sprint."""
    missions = []
    for sprint in backlog.get("domainFields", {}).get("sprints", []):
        if sprint.get("sprintId") == sprint_id:
            missions = sprint.get("missions", [])
            break
    return missions


def extract_success_metrics(backlog: Dict[str, Any], sprint_id: str) -> List[str]:
    """Extract success metrics for a sprint from backlog."""
    metrics = []
    for sprint in backlog.get("domainFields", {}).get("sprints", []):
        if sprint.get("sprintId") == sprint_id:
            # Try to find metrics in successMetrics
            break
    
    # Fallback to predefined metrics
    if sprint_id == "Sprint 01":
        return SUCCESS_METRICS.get("Sprint 1", [])
    return metrics


def evaluate_presidio_metric(
    baseline: Optional[Dict[str, Any]], 
    tuned: Optional[Dict[str, Any]]
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
            results[entity] = {
                "recall": recall,
                "met": recall >= 0.95
            }
            min_recall = min(min_recall, recall)
        else:
            results[entity] = {
                "recall": None,
                "met": False,
                "note": "Entity not found in metrics"
            }
            min_recall = 0.0
    
    met = min_recall >= 0.95
    details = {
        "min_recall": min_recall,
        "target": 0.95,
        "per_entity": results,
        "overall_recall": tuned.get("tuned_metrics", {}).get("overall", {}).get("recall", 0.0)
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
            results[fmt] = {
                "total_uploaded": total,
                "chunked": chunked,
                "met": success
            }
            if success:
                success_count += 1
        else:
            results[fmt] = {
                "total_uploaded": 0,
                "chunked": 0,
                "met": False,
                "note": "Format not found in coverage report"
            }
    
    met = success_count >= 5
    details = {
        "formats_met": success_count,
        "target": 5,
        "per_format": results
    }
    
    return met, f"{success_count}/5 priority formats successfully ingested and chunked", details


def evaluate_qdrant_metric(performance: Optional[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Evaluate: Embedding pipeline stores ≥1 sample project in Qdrant with <10ms p99 query latency (local).
    """
    if not performance:
        return False, "qdrant_performance.json missing", {}
    
    collection_info = performance.get("collection_info", {})
    points_count = collection_info.get("points_count", 0)
    
    query_latency = performance.get("query_latency", [])
    p99_latency = None
    
    if query_latency:
        # Use the highest top_k latency as proxy for p99 (since we don't have exact p99)
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
        "latency_met": latency_met
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
    """
    Evaluate: Sprint evaluation script executes and produces retrospective report.
    This metric is met if this script runs successfully.
    """
    return True, "Script executed successfully", {}


def generate_report(
    sprint_id: str,
    missions: List[Dict[str, Any]],
    evaluations: List[Tuple[str, bool, str, Dict[str, Any]]],
    output_dir: Path
) -> Path:
    """Generate Markdown report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{sprint_id.lower().replace(' ', '-')}-summary.md"
    
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    lines = [
        f"# {sprint_id} Efficacy Report",
        "",
        f"**Generated:** {timestamp}",
        "",
        "## Executive Summary",
        ""
    ]
    
    # Count met/unmet
    met_count = sum(1 for _, met, _, _ in evaluations if met)
    total_count = len(evaluations)
    
    lines.append(f"- **Metrics Met:** {met_count}/{total_count}")
    lines.append(f"- **Metrics Unmet:** {total_count - met_count}/{total_count}")
    lines.append("")
    
    # Mission status summary
    completed = [m for m in missions if m.get("status") == "Completed"]
    in_progress = [m for m in missions if m.get("status") == "In Progress"]
    current = [m for m in missions if m.get("status") == "Current"]
    queued = [m for m in missions if m.get("status") == "Queued"]
    
    lines.extend([
        "## Mission Status",
        "",
        f"- **Completed:** {len(completed)}",
        f"- **In Progress:** {len(in_progress)}",
        f"- **Current:** {len(current)}",
        f"- **Queued:** {len(queued)}",
        ""
    ])
    
    # Success criteria evaluation
    lines.extend([
        "## Success Criteria Evaluation",
        ""
    ])
    
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
    
    # Recommendations
    lines.extend([
        "## Recommendations",
        ""
    ])
    
    unmet = [(metric, status, details) for metric, met, status, details in evaluations if not met]
    
    if not unmet:
        lines.append("- ✅ All success criteria met. Sprint 1 objectives achieved.")
    else:
        lines.append("### Unmet Criteria:")
        for metric, status, details in unmet:
            lines.append(f"- **{metric}**")
            lines.append(f"  - Status: {status}")
            if details:
                # Add specific recommendations based on details
                if "recall" in str(details):
                    lines.append("  - Consider tuning Presidio recognizers or adjusting threshold")
                if "formats" in str(details):
                    lines.append("  - Ensure all priority formats have test documents uploaded")
                if "latency" in str(details):
                    lines.append("  - Review Qdrant HNSW parameters or local performance constraints")
    
    lines.append("")
    
    # Mission completion summary
    lines.extend([
        "## Mission Completion Summary",
        ""
    ])
    
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
    
    # Write report
    report_content = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    return report_path


def main():
    """Main evaluation workflow."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Evaluate sprint missions against success criteria")
    parser.add_argument(
        "--sprint",
        type=int,
        default=1,
        help="Sprint number to evaluate (default: 1)"
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)"
    )
    
    args = parser.parse_args()
    sprint_id = f"Sprint {args.sprint:02d}"
    
    print(f"Evaluating {sprint_id}...")
    
    # Load backlog
    backlog = load_yaml(BACKLOG_PATH)
    
    # Extract sprint missions
    missions = extract_sprint_missions(backlog, sprint_id)
    print(f"Found {len(missions)} missions for {sprint_id}")
    
    # Load telemetry artifacts
    baseline = load_json(PRESIDIO_BASELINE)
    tuned = load_json(PRESIDIO_TUNED)
    coverage = load_json(INGESTION_COVERAGE)
    performance = load_json(QDRANT_PERFORMANCE)
    
    print("Loaded telemetry artifacts:")
    print(f"  - Presidio baseline: {'✓' if baseline else '✗'}")
    print(f"  - Presidio tuned: {'✓' if tuned else '✗'}")
    print(f"  - Ingestion coverage: {'✓' if coverage else '✗'}")
    print(f"  - Qdrant performance: {'✓' if performance else '✗'}")
    
    # Extract success metrics
    metrics = extract_success_metrics(backlog, sprint_id)
    if not metrics:
        # Use default Sprint 1 metrics
        metrics = SUCCESS_METRICS.get("Sprint 1", [])
    
    # Evaluate each metric
    evaluations = []
    
    # 1. Presidio recall
    met, status, details = evaluate_presidio_metric(baseline, tuned)
    evaluations.append((metrics[0] if len(metrics) > 0 else "Presidio recall ≥ 0.95", met, status, details))
    
    # 2. Ingestion formats
    met, status, details = evaluate_ingestion_metric(coverage)
    evaluations.append((metrics[1] if len(metrics) > 1 else "Five priority formats ingested", met, status, details))
    
    # 3. Qdrant performance
    met, status, details = evaluate_qdrant_metric(performance)
    evaluations.append((metrics[2] if len(metrics) > 2 else "Qdrant storage and latency", met, status, details))
    
    # 4. Script execution (met by definition)
    met, status, details = evaluate_script_metric()
    evaluations.append((metrics[3] if len(metrics) > 3 else "Evaluation script execution", met, status, details))
    
    # Generate report
    if args.format == "markdown":
        report_path = generate_report(sprint_id, missions, evaluations, REPORTS_DIR)
        print(f"\n✅ Report generated: {report_path}")
    else:
        # JSON output
        report_data = {
            "sprint": sprint_id,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "evaluations": [
                {
                    "metric": metric,
                    "met": met,
                    "status": status,
                    "details": details
                }
                for metric, met, status, details in evaluations
            ],
            "mission_summary": {
                "total": len(missions),
                "completed": len([m for m in missions if m.get("status") == "Completed"]),
                "in_progress": len([m for m in missions if m.get("status") == "In Progress"]),
                "current": len([m for m in missions if m.get("status") == "Current"]),
                "queued": len([m for m in missions if m.get("status") == "Queued"])
            }
        }
        report_path = REPORTS_DIR / f"{sprint_id.lower().replace(' ', '-')}-summary.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        print(f"\n✅ Report generated: {report_path}")
    
    # Print summary
    print("\n" + "="*60)
    print("Evaluation Summary")
    print("="*60)
    met_count = sum(1 for _, met, _, _ in evaluations if met)
    print(f"Metrics Met: {met_count}/{len(evaluations)}")
    for metric, met, status, _ in evaluations:
        icon = "✅" if met else "❌"
        print(f"  {icon} {metric}")
        print(f"     {status}")


if __name__ == "__main__":
    main()

