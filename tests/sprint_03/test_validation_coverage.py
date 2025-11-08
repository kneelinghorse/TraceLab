from scripts.evaluate_sprint_03 import (
    TELEMETRY_FILES,
    compute_validation_coverage,
    load_jsonl,
)


def test_validation_rate_exceeds_target() -> None:
    events = load_jsonl(TELEMETRY_FILES["validation"])
    result = compute_validation_coverage(events)

    assert result.met is True
    assert result.details["coverage"] > 0.95
    assert len(result.details["failed_missions"]) == 1
