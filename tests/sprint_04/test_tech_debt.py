from scripts.evaluate_sprint_04 import (
    TELEMETRY_FILES,
    compute_tech_debt_resolution,
    load_jsonl,
)


def test_playwright_migration_eliminates_cypress_cost() -> None:
    events = load_jsonl(TELEMETRY_FILES["playwright"])
    result = compute_tech_debt_resolution(events)

    assert result.met is True
    assert result.actual["playwright_cost_monthly"] == 0.0
    assert result.details["cost_savings_monthly"] >= 70.0
    assert result.details["tests_migrated"] == result.details["tests_passing"]
