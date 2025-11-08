from scripts.evaluate_sprint_03 import (
    TELEMETRY_FILES,
    compute_progress_accuracy,
    load_jsonl,
)


def test_progress_tracking_within_tolerance() -> None:
    events = load_jsonl(TELEMETRY_FILES["progress_tracking"])
    result = compute_progress_accuracy(events)

    assert result.met is True
    assert result.details["out_of_tolerance"] == 0
