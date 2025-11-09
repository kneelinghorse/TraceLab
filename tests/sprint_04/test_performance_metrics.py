from scripts.evaluate_sprint_04 import (
    TELEMETRY_FILES,
    compute_cost_compliance,
    compute_query_latency,
    load_jsonl,
)


def test_latency_stays_under_two_seconds() -> None:
    events = load_jsonl(TELEMETRY_FILES["performance"])
    result = compute_query_latency(events)

    assert result.met is True
    assert result.actual["p95_latency_ms"] < 2000


def test_cost_profile_within_budget() -> None:
    events = load_jsonl(TELEMETRY_FILES["performance"])
    result = compute_cost_compliance(events)

    assert result.met is True
    assert 80.0 <= result.actual["monthly_cost"] <= 105.0
    assert result.actual["cost_per_query"] <= 0.00023
