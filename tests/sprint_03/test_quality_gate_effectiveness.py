from scripts.evaluate_sprint_03 import (
    TELEMETRY_FILES,
    compute_quality_gate_effectiveness,
    load_jsonl,
)


def test_quality_gate_failures_blocked_with_actionable_feedback() -> None:
    events = load_jsonl(TELEMETRY_FILES["quality_gates"])
    result = compute_quality_gate_effectiveness(events)

    assert result.met is True
    assert result.details["failure_count"] > 0
    assert result.details["actionable_ratio"] == 1.0
