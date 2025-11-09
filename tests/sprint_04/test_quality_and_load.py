from scripts.evaluate_sprint_04 import (
    TELEMETRY_FILES,
    compute_load_test,
    compute_quality_automation,
    load_jsonl,
)


def test_quality_checks_block_and_pass() -> None:
    events = load_jsonl(TELEMETRY_FILES["quality"])
    result = compute_quality_automation(events)

    assert result.met is True
    assert not result.details["failing"]
    assert min(result.actual.values()) > 0.9


def test_load_test_supports_target_concurrency() -> None:
    events = load_jsonl(TELEMETRY_FILES["performance"])
    result = compute_load_test(events)

    assert result.met is True
    assert result.actual["qualifying_runs"] >= 1
