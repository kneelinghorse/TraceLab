#!/usr/bin/env python3
"""
Sprint 03 Mission Protocol Efficacy Evaluator (B3.5)
---------------------------------------------------

Aggregates validation, quality gate, and API telemetry to determine whether
Sprint 03 success criteria were met. Generates both Markdown and JSON reports
under ``cmos/reports/sprint-03`` so planning artifacts stay synchronized with
the CMOS Mission Protocol workspace.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Dict, Iterable, List, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
TELEMETRY_DIR = REPO_ROOT / "cmos" / "telemetry" / "events"
REPORTS_DIR = REPO_ROOT / "cmos" / "reports" / "sprint-03"
SUMMARY_PATH = REPORTS_DIR / "sprint-03-summary.md"
METRICS_PATH = REPORTS_DIR / "metrics.json"

TELEMETRY_FILES: Dict[str, Path] = {
    "validation": TELEMETRY_DIR / "sprint-03-validation.jsonl",
    "quality_gates": TELEMETRY_DIR / "sprint-03-quality-gates.jsonl",
    "api_performance": TELEMETRY_DIR / "sprint-03-api-performance.jsonl",
    "yaml_roundtrip": TELEMETRY_DIR / "sprint-03-yaml-roundtrip.jsonl",
    "evidence_integrity": TELEMETRY_DIR / "sprint-03-evidence-integrity.jsonl",
    "progress_tracking": TELEMETRY_DIR / "sprint-03-progress-tracking.jsonl",
}


@dataclass
class MetricResult:
    """Structured metric output so JSON/Markdown writers remain simple."""

    name: str
    met: bool
    actual: Any
    target: Any
    details: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return payload


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load newline-delimited JSON telemetry."""

    if not path.exists():
        raise FileNotFoundError(f"Telemetry file missing: {path}")
    items: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(json.loads(line))
    return items


def _pct(part: int, whole: int) -> float:
    return 0.0 if whole == 0 else part / whole


def compute_validation_coverage(events: Sequence[Dict[str, Any]]) -> MetricResult:
    """Mission Protocol validation must exceed 95% success across all layers."""

    required_layers = ("api", "service", "database")
    total = len(events)
    passing = 0
    failures: List[Dict[str, Any]] = []

    for event in events:
        layers = event.get("layers", {})
        multi_layer_pass = event.get("status") == "pass" and all(
            layers.get(layer) for layer in required_layers
        )
        if multi_layer_pass:
            passing += 1
            continue
        missing = [layer for layer in required_layers if not layers.get(layer)]
        failures.append(
            {
                "mission_id": event.get("mission_id"),
                "missing_layers": missing,
                "detail": event.get("detail"),
            }
        )

    coverage = _pct(passing, total)
    target = 0.95
    met = coverage > target
    details = {
        "total_validations": total,
        "successful_validations": passing,
        "coverage": coverage,
        "failed_missions": failures,
        "reference": "docs/quality_gates.md",
    }
    return MetricResult(
        name="Mission Protocol validation coverage >95% across API/service/database layers",
        met=met,
        actual=coverage,
        target=target,
        details=details,
    )


def compute_quality_gate_effectiveness(
    events: Sequence[Dict[str, Any]],
) -> MetricResult:
    """Quality gate failures must block promotion and include actionable notes."""

    gate_totals: Dict[str, Dict[str, int]] = {}
    fail_records: List[Dict[str, Any]] = []

    for event in events:
        gate = event.get("gate")
        bucket = gate_totals.setdefault(gate, {"total": 0, "fails": 0})
        bucket["total"] += 1
        if event.get("status") == "pass":
            continue
        bucket["fails"] += 1
        fail_records.append(
            {
                "mission_id": event.get("mission_id"),
                "gate": gate,
                "blocked": bool(event.get("blocked")),
                "actionable_feedback": bool(event.get("actionable_feedback")),
                "resolution_logged": bool(event.get("resolution_logged")),
            }
        )

    fail_count = len(fail_records)
    actionable = sum(
        1
        for record in fail_records
        if record["blocked"]
        and record["actionable_feedback"]
        and record["resolution_logged"]
    )
    actionable_ratio = _pct(actionable, fail_count) if fail_count else 1.0
    met = actionable_ratio == 1.0
    details = {
        "gate_activity": gate_totals,
        "failure_count": fail_count,
        "actionable_failures": actionable,
        "actionable_ratio": actionable_ratio,
    }
    return MetricResult(
        name="Quality gates block invalid missions with actionable remediation guidance",
        met=met,
        actual=actionable_ratio,
        target=1.0,
        details=details,
    )


def compute_api_stability(events: Sequence[Dict[str, Any]]) -> MetricResult:
    """Mission Protocol CRUD endpoints must run >99% uptime with p95 latency <500ms."""

    if not events:
        raise ValueError("No API telemetry events recorded.")
    uptimes = [event["uptime"] for event in events if event.get("uptime") is not None]
    latencies = [
        event["p95_latency_ms"]
        for event in events
        if event.get("p95_latency_ms") is not None
    ]
    error_rates = [event.get("error_rate", 0.0) for event in events]

    avg_uptime = fmean(uptimes)
    min_uptime = min(uptimes)
    sorted_latencies = sorted(latencies)
    percentile_index = max(int(round(0.95 * len(sorted_latencies))) - 1, 0)
    aggregated_p95 = sorted_latencies[percentile_index]
    avg_error_rate = fmean(error_rates) if error_rates else 0.0

    met = min_uptime >= 0.99 and aggregated_p95 < 500
    details = {
        "avg_uptime": avg_uptime,
        "min_uptime": min_uptime,
        "aggregated_p95_latency_ms": aggregated_p95,
        "avg_error_rate": avg_error_rate,
        "samples": len(events),
    }
    return MetricResult(
        name="API stability (>99% uptime, <500ms p95 latency)",
        met=met,
        actual={"min_uptime": min_uptime, "p95_latency_ms": aggregated_p95},
        target={"uptime": 0.99, "p95_latency_ms": 500},
        details=details,
    )


def compute_yaml_roundtrip(events: Sequence[Dict[str, Any]]) -> MetricResult:
    """Import→export→import loop must retain 100% fidelity."""

    total = len(events)
    perfect_roundtrips = sum(
        1 for event in events if (event.get("round_trip_diff") or 0) == 0
    )
    met = perfect_roundtrips == total
    details = {
        "total_round_trips": total,
        "perfect_round_trips": perfect_roundtrips,
        "round_trip_failures": total - perfect_roundtrips,
        "total_fields_reviewed": sum(
            event.get("fields_checked", 0) for event in events
        ),
    }
    return MetricResult(
        name="YAML round-trip accuracy (import/export/import parity)",
        met=met,
        actual=perfect_roundtrips,
        target=total,
        details=details,
    )


def compute_evidence_integrity(events: Sequence[Dict[str, Any]]) -> MetricResult:
    """All linked evidence chunks must exist and meet relevance thresholds."""

    missing_events = [
        event
        for event in events
        if (event.get("missing_chunks", 0) > 0)
        or (event.get("invalid_relevance", 0) > 0)
    ]
    avg_relevance = (
        fmean(event.get("average_relevance", 0.0) for event in events)
        if events
        else 0.0
    )
    met = not missing_events and avg_relevance >= 0.8
    details = {
        "checked_missions": len(events),
        "missing_chunk_events": len(missing_events),
        "average_relevance": avg_relevance,
    }
    return MetricResult(
        name="Evidence linking integrity (chunk presence + relevance >= 0.8)",
        met=met,
        actual={
            "missing_chunk_events": len(missing_events),
            "average_relevance": avg_relevance,
        },
        target={"missing_chunk_events": 0, "average_relevance": 0.8},
        details=details,
    )


def compute_progress_accuracy(
    events: Sequence[Dict[str, Any]], tolerance: float = 0.05
) -> MetricResult:
    """Progress tracker must stay within ±5% of actual field coverage."""

    if not events:
        raise ValueError("Progress telemetry missing.")
    within_tolerance = [
        event
        for event in events
        if abs(
            event.get("declared_completion", 0.0)
            - event.get("observed_completion", 0.0)
        )
        <= tolerance
    ]
    out_of_tolerance = len(events) - len(within_tolerance)
    met = out_of_tolerance == 0
    details = {
        "samples": len(events),
        "within_tolerance": len(within_tolerance),
        "out_of_tolerance": out_of_tolerance,
        "tolerance": tolerance,
    }
    return MetricResult(
        name="Progress tracking accuracy within ±5% of field population",
        met=met,
        actual={"within_tolerance": len(within_tolerance), "samples": len(events)},
        target={"tolerance": tolerance},
        details=details,
    )


def build_summary(results: Sequence[MetricResult]) -> str:
    """Render Markdown report for planning handoff."""

    timestamp = datetime.now(timezone.utc).isoformat()
    met_count = sum(1 for result in results if result.met)
    lines = [
        "# Sprint 03 Mission Protocol Evaluation",
        "",
        f"**Generated:** {timestamp}",
        "",
        "## Executive Summary",
        "",
        f"- **Metrics Met:** {met_count}/{len(results)}",
        f"- **Metrics Unmet:** {len(results) - met_count}/{len(results)}",
        "- References: docs/quality_gates.md, docs/mission_protocol_validation.md",
        "",
        "## Metric Details",
        "",
    ]
    for result in results:
        icon = "✅" if result.met else "❌"
        lines.append(f"### {icon} {result.name}")
        lines.append("")
        lines.append(f"- **Actual:** {json.dumps(result.actual)}")
        lines.append(f"- **Target:** {json.dumps(result.target)}")
        lines.append("")
        lines.append("**Details:**")
        lines.append("```json")
        lines.append(json.dumps(result.details, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def write_reports(results: Sequence[MetricResult]) -> None:
    """Persist Markdown + JSON artifacts."""

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_payload = {
        "sprint": "Sprint 03",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": [result.as_dict() for result in results],
    }
    SUMMARY_PATH.write_text(build_summary(results) + "\n", encoding="utf-8")
    METRICS_PATH.write_text(
        json.dumps(metrics_payload, indent=2) + "\n", encoding="utf-8"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sprint 03 Mission Protocol evaluation runner."
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Console output preference (reports always generated).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    validation_events = load_jsonl(TELEMETRY_FILES["validation"])
    gate_events = load_jsonl(TELEMETRY_FILES["quality_gates"])
    api_events = load_jsonl(TELEMETRY_FILES["api_performance"])
    yaml_events = load_jsonl(TELEMETRY_FILES["yaml_roundtrip"])
    evidence_events = load_jsonl(TELEMETRY_FILES["evidence_integrity"])
    progress_events = load_jsonl(TELEMETRY_FILES["progress_tracking"])

    results = [
        compute_validation_coverage(validation_events),
        compute_quality_gate_effectiveness(gate_events),
        compute_api_stability(api_events),
        compute_yaml_roundtrip(yaml_events),
        compute_evidence_integrity(evidence_events),
        compute_progress_accuracy(progress_events),
    ]

    write_reports(results)

    if args.format == "json":
        print(json.dumps([result.as_dict() for result in results], indent=2))
    else:
        for result in results:
            icon = "✅" if result.met else "❌"
            print(f"{icon} {result.name}")
            print(f"    Actual: {result.actual}")
            print(f"    Target: {result.target}")

        print(f"\nReports written to {SUMMARY_PATH} and {METRICS_PATH}")


if __name__ == "__main__":
    main()
