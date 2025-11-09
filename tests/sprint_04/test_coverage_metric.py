from scripts.evaluate_sprint_04 import (
    TELEMETRY_FILES,
    compute_test_coverage,
    load_jsonl,
)


def test_coverage_threshold_exceeded() -> None:
    events = load_jsonl(TELEMETRY_FILES["coverage"])
    result = compute_test_coverage(events)

    assert result.met is True
    assert result.actual["coverage"] >= 0.8
    assert result.details["report_path"].endswith("test-coverage-report.html")
