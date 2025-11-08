from scripts.evaluate_sprint_03 import (
    TELEMETRY_FILES,
    compute_api_stability,
    load_jsonl,
)


def test_api_uptime_and_latency_meet_targets() -> None:
    events = load_jsonl(TELEMETRY_FILES["api_performance"])
    result = compute_api_stability(events)

    assert result.met is True
    assert result.details["min_uptime"] >= 0.99
    assert result.details["aggregated_p95_latency_ms"] < 500
