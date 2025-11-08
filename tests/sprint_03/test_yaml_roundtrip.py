from scripts.evaluate_sprint_03 import (
    TELEMETRY_FILES,
    compute_yaml_roundtrip,
    load_jsonl,
)


def test_yaml_roundtrip_is_lossless() -> None:
    events = load_jsonl(TELEMETRY_FILES["yaml_roundtrip"])
    result = compute_yaml_roundtrip(events)

    assert result.met is True
    assert result.details["round_trip_failures"] == 0
