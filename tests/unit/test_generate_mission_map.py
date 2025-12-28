from scripts.generate_mission_map import MissionRecord, assign_missions


def test_assign_missions_prefers_unique_ids() -> None:
    docs = [
        {"doc_id": "doc-1", "title": "PEDR Search", "source_path": "docs/pedr-search.md"},
        {"doc_id": "doc-2", "title": "Qdrant Optimization", "source_path": "docs/qdrant-optimization.md"},
    ]
    missions = [
        MissionRecord(
            mission_uuid="uuid-1",
            mission_id="B1.1",
            title="PEDR Search Improvements",
            status="completed",
        ),
        MissionRecord(
            mission_uuid="uuid-2",
            mission_id="B1.2",
            title="Qdrant Optimization Review",
            status="completed",
        ),
    ]

    mapping, low_confidence = assign_missions(docs, missions, min_score=0.1)

    assert mapping["doc-1"]["mission_id"] == "B1.1"
    assert mapping["doc-2"]["mission_id"] == "B1.2"
    assert low_confidence == []


def test_assign_missions_flags_low_confidence() -> None:
    docs = [
        {"doc_id": "doc-1", "title": "Unrelated Topic", "source_path": "docs/other.md"},
    ]
    missions = [
        MissionRecord(
            mission_uuid="uuid-1",
            mission_id="B1.1",
            title="PEDR Search Improvements",
            status="completed",
        ),
    ]

    mapping, low_confidence = assign_missions(docs, missions, min_score=0.9)

    assert mapping["doc-1"]["mission_id"] == "B1.1"
    assert low_confidence
