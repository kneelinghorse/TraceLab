from scripts.evaluate_sprint_03 import (
    TELEMETRY_FILES,
    compute_evidence_integrity,
    load_jsonl,
)


def test_evidence_integrity_checks_detect_missing_chunks() -> None:
    events = load_jsonl(TELEMETRY_FILES["evidence_integrity"])
    result = compute_evidence_integrity(events)

    assert result.met is True
    assert result.details["missing_chunk_events"] == 0
    assert result.details["average_relevance"] >= 0.8
