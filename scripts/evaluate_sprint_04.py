#!/usr/bin/env python3
"""
Sprint 04 Mission Protocol Efficacy Evaluator (B4.5)
----------------------------------------------------

Aggregates Sprint 04 telemetry (tech debt, quality automation, performance, load,
and coverage) to confirm that success criteria were met. Produces Markdown +
JSON reports under ``cmos/reports/sprint-04`` so planning artifacts stay aligned
with the SQLite backlog.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
TELEMETRY_DIR = REPO_ROOT / "cmos" / "telemetry" / "events"
REPORTS_DIR = REPO_ROOT / "cmos" / "reports" / "sprint-04"
SUMMARY_PATH = REPORTS_DIR / "sprint-04-summary.md"
METRICS_PATH = REPORTS_DIR / "metrics.json"

TELEMETRY_FILES: Dict[str, Path] = {
    "playwright": TELEMETRY_DIR / "sprint-04-playwright-migration.jsonl",
    "quality": TELEMETRY_DIR / "sprint-04-quality-automation.jsonl",
    "performance": TELEMETRY_DIR / "sprint-04-performance.jsonl",
    "coverage": TELEMETRY_DIR / "sprint-04-test-coverage.jsonl",
}


@dataclass
class MetricResult:
    """Structured metric output to simplify report generation."""

    name: str
    met: bool
    actual: Any
    target: Any
    details: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load newline-delimited JSON telemetry."""

    if not path.exists():
        raise FileNotFoundError(f"Telemetry file missing: {path}")
    events: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    return events


def _first(items: Iterable[Dict[str, Any]], predicate) -> Dict[str, Any]:
    for item in items:
        if predicate(item):
            return item
    raise ValueError("Expected telemetry event not found.")


def compute_tech_debt_resolution(events: Sequence[Dict[str, Any]]) -> MetricResult:
    """Verify Cypress was removed and Playwright runs at $0/month."""

    primary = _first(events, lambda event: "cypress_cost_monthly" in event)
    tests_migrated = primary.get("tests_migrated", 0)
    tests_passing = primary.get("tests_passing", 0)
    removed = bool(primary.get("cypress_removed"))
    monthly_cost = float(primary.get("playwright_cost_monthly", 1.0))
    cost_savings = float(primary.get("cypress_cost_monthly", 0.0)) - monthly_cost

    met = removed and monthly_cost == 0.0 and tests_passing >= tests_migrated
    details = {
        "tests_migrated": tests_migrated,
        "tests_passing": tests_passing,
        "trace_viewer_verified": bool(primary.get("trace_viewer_verified")),
        "ci_duration_minutes": primary.get("ci_duration_minutes"),
        "cost_savings_monthly": cost_savings,
        "github_actions_job": primary.get("github_actions_job"),
    }
    return MetricResult(
        name="Tech debt resolved: Cypress removed, Playwright cost $0/month",
        met=met,
        actual={
            "playwright_cost_monthly": monthly_cost,
            "tests_passing": tests_passing,
        },
        target={"playwright_cost_monthly": 0.0, "tests_passing": tests_migrated},
        details=details,
    )


def compute_quality_automation(events: Sequence[Dict[str, Any]]) -> MetricResult:
    """Bias detection and traceability automation must pass with actionable blocking."""

    required_checks = ("bias_detection", "traceability")
    check_summary: Dict[str, Dict[str, Any]] = {}
    failing: List[str] = []

    for check in required_checks:
        record = _first(events, lambda event, chk=check: event.get("check") == chk)
        runs = record.get("runs", 0)
        issues_detected = (
            record.get("issues_detected")
            if "issues_detected" in record
            else record.get("broken_links", 0) + record.get("low_relevance", 0)
        )
        issues_blocked = record.get("issues_blocked", issues_detected)
        pass_rate = 1.0 if runs == 0 else (runs - issues_detected) / runs
        healthy = record.get("status") == "pass" and issues_blocked >= issues_detected
        if not healthy:
            failing.append(check)
        check_summary[check] = {
            "runs": runs,
            "issues_detected": issues_detected,
            "issues_blocked": issues_blocked,
            "pass_rate": pass_rate,
            "status": record.get("status"),
        }

    met = not failing
    details = {"checks": check_summary, "failing": failing}
    return MetricResult(
        name="Quality automation operational (bias + traceability)",
        met=met,
        actual={
            check: summary["pass_rate"] for check, summary in check_summary.items()
        },
        target={"bias_detection": 1.0, "traceability": 1.0},
        details=details,
    )


def compute_query_latency(
    events: Sequence[Dict[str, Any]], target_ms: int = 2000
) -> MetricResult:
    """Ensure P95 latency remains under the 2s target."""

    latency_events = [
        event for event in events if event.get("type") == "latency_sample"
    ]
    if not latency_events:
        raise ValueError("Latency telemetry missing.")

    worst_p95 = max(event.get("p95_latency_ms", 0) for event in latency_events)
    avg_cache_hit = sum(
        event.get("cache_hit_rate", 0.0) for event in latency_events
    ) / len(latency_events)
    met = worst_p95 < target_ms
    details = {
        "samples": len(latency_events),
        "worst_p95_latency_ms": worst_p95,
        "p99_latency_ms": max(
            event.get("p99_latency_ms", 0) for event in latency_events
        ),
        "pre_optimization_p95_ms": min(
            event.get("pre_optimization_p95_ms", worst_p95) for event in latency_events
        ),
        "average_cache_hit_rate": avg_cache_hit,
    }
    return MetricResult(
        name="Performance optimized: RAG query latency <2s P95",
        met=met,
        actual={"p95_latency_ms": worst_p95},
        target={"p95_latency_ms": target_ms},
        details=details,
    )


def compute_cost_compliance(
    events: Sequence[Dict[str, Any]],
    budget_min: float = 80.0,
    budget_max: float = 105.0,
    cost_per_query_target: float = 0.00023,
) -> MetricResult:
    """Validate monthly API spend and per-query cost stay within roadmap targets."""

    cost_events = [event for event in events if event.get("type") == "cost_report"]
    if not cost_events:
        raise ValueError("Cost telemetry missing.")

    latest = cost_events[-1]
    monthly_cost = float(latest.get("monthly_cost", 0.0))
    cost_per_query = float(latest.get("cost_per_query", 1.0))

    within_budget = budget_min <= monthly_cost <= budget_max
    within_per_query = cost_per_query <= cost_per_query_target
    met = within_budget and within_per_query
    details = {
        "monthly_cost": monthly_cost,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "cost_per_query": cost_per_query,
        "cost_per_query_target": cost_per_query_target,
        "queries": latest.get("queries"),
        "openai_usage": latest.get("openai_usage"),
    }
    return MetricResult(
        name="API cost within $80-105/month and ≤$0.00023 per query",
        met=met,
        actual={"monthly_cost": monthly_cost, "cost_per_query": cost_per_query},
        target={
            "monthly_cost_range": [budget_min, budget_max],
            "cost_per_query": cost_per_query_target,
        },
        details=details,
    )


def compute_load_test(
    events: Sequence[Dict[str, Any]], target_users: int = 100
) -> MetricResult:
    """Confirm system sustains 100 concurrent queries without errors."""

    load_events = [event for event in events if event.get("type") == "load_test"]
    if not load_events:
        raise ValueError("Load test telemetry missing.")

    qualifying = [
        event
        for event in load_events
        if event.get("concurrent_users", 0) >= target_users
        and event.get("error_rate", 1.0) <= 0.01
        and event.get("max_latency_ms", target_users) <= 2000
    ]
    met = bool(qualifying)
    details = {
        "runs": load_events,
        "qualifying_runs": qualifying,
        "target_concurrent_users": target_users,
    }
    return MetricResult(
        name="Load testing: 100 concurrent queries sustained",
        met=met,
        actual={"qualifying_runs": len(qualifying)},
        target={"required_runs": 1},
        details=details,
    )


def compute_test_coverage(
    events: Sequence[Dict[str, Any]], minimum: float = 0.8
) -> MetricResult:
    """Ensure Python coverage stays above 80%."""

    if not events:
        raise ValueError("Coverage telemetry missing.")
    latest = events[-1]
    coverage = float(latest.get("coverage", 0.0))
    met = coverage >= minimum
    details = {
        "lines_covered": latest.get("lines_covered"),
        "lines_total": latest.get("lines_total"),
        "report_path": latest.get("report_path"),
        "command": latest.get("command"),
        "modules_reported": latest.get("modules_reported"),
    }
    return MetricResult(
        name="Test coverage ≥80% across Python codebase",
        met=met,
        actual={"coverage": coverage},
        target={"coverage": minimum},
        details=details,
    )


def compute_report_generation_metric() -> MetricResult:
    """Validate summary + metrics artifacts exist for sprint handoff."""

    summary_exists = SUMMARY_PATH.exists() and SUMMARY_PATH.stat().st_size > 0
    metrics_exists = METRICS_PATH.exists() and METRICS_PATH.stat().st_size > 0
    met = summary_exists and metrics_exists
    details = {
        "summary_path": str(SUMMARY_PATH),
        "summary_bytes": SUMMARY_PATH.stat().st_size if summary_exists else 0,
        "metrics_path": str(METRICS_PATH),
        "metrics_bytes": METRICS_PATH.stat().st_size if metrics_exists else 0,
    }
    return MetricResult(
        name="Sprint evaluation report + metrics generated",
        met=met,
        actual={
            "summary_exists": summary_exists,
            "metrics_exists": metrics_exists,
        },
        target={
            "artifacts": [
                "cmos/reports/sprint-04/sprint-04-summary.md",
                "cmos/reports/sprint-04/metrics.json",
            ]
        },
        details=details,
    )


def build_summary(results: Sequence[MetricResult]) -> str:
    """Render Markdown summary for documentation handoff."""

    timestamp = datetime.now(timezone.utc).isoformat()
    met_count = sum(1 for result in results if result.met)
    lines = [
        "# Sprint 04 Mission Protocol Evaluation",
        "",
        f"**Generated:** {timestamp}",
        "",
        "## Executive Summary",
        "",
        f"- **Metrics Met:** {met_count}/{len(results)}",
        f"- **Metrics Unmet:** {len(results) - met_count}/{len(results)}",
        "- References: cmos/reports/sprint-04/SPRINT-04-PLANNING.md, docs/mission-protocol-tutorial.md",
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
    """Persist Markdown and JSON artifacts for Sprint 04."""

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_payload = {
        "sprint": "Sprint 04",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": [result.as_dict() for result in results],
    }
    SUMMARY_PATH.write_text(build_summary(results) + "\n", encoding="utf-8")
    METRICS_PATH.write_text(
        json.dumps(metrics_payload, indent=2) + "\n", encoding="utf-8"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sprint 04 Mission Protocol evaluation runner."
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

    playwright_events = load_jsonl(TELEMETRY_FILES["playwright"])
    quality_events = load_jsonl(TELEMETRY_FILES["quality"])
    performance_events = load_jsonl(TELEMETRY_FILES["performance"])
    coverage_events = load_jsonl(TELEMETRY_FILES["coverage"])

    core_results = [
        compute_tech_debt_resolution(playwright_events),
        compute_quality_automation(quality_events),
        compute_query_latency(performance_events),
        compute_cost_compliance(performance_events),
        compute_test_coverage(coverage_events),
        compute_load_test(performance_events),
    ]

    # Generate artifacts before validating their presence for the report metric.
    write_reports(core_results)
    report_metric = compute_report_generation_metric()
    results = core_results + [report_metric]
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
