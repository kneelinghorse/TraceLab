from __future__ import annotations

from app.services.pedr.manifest_transformer import ManifestTransformer


def _edges_by_type(relationships: dict) -> dict[str, list[dict]]:
    edges = relationships.get("edges", [])
    grouped: dict[str, list[dict]] = {}
    for edge in edges:
        grouped.setdefault(edge.get("type"), []).append(edge)
    return grouped


def test_transform_mission_emits_edges() -> None:
    transformer = ManifestTransformer()
    mission_data = {
        "missionId": "M100",
        "name": "Edge Mission",
        "evidence": [
            {"chunk_id": "chunk-1", "via": "api"},
            {"chunk_id": "chunk-2"},
        ],
    }

    result = transformer.transform_mission(
        mission_id="uuid-100",
        mission_data=mission_data,
        project_id="project-100",
    )

    assert result.success
    relationships = result.manifest.manifest["relationships"]
    grouped = _edges_by_type(relationships)

    belongs_edges = grouped.get("belongs_to", [])
    assert len(belongs_edges) == 1
    assert belongs_edges[0]["to"] == "urn:research:project:project-100"

    evidence_edges = grouped.get("evidence", [])
    evidence_targets = {edge["to"] for edge in evidence_edges}
    assert evidence_targets == {
        "urn:research:chunk:chunk-1",
        "urn:research:chunk:chunk-2",
    }
    assert any(edge.get("via") == "api" for edge in evidence_edges)


def test_transform_document_emits_edges() -> None:
    transformer = ManifestTransformer()
    result = transformer.transform_document(
        document_id="doc-200",
        name="Edge Document",
        content="Content",
        file_type="md",
        source_type="data",
        project_id="project-200",
        chunk_count=2,
    )

    assert result.success
    relationships = result.manifest.manifest["relationships"]
    grouped = _edges_by_type(relationships)

    belongs_edges = grouped.get("belongs_to", [])
    assert len(belongs_edges) == 1
    assert belongs_edges[0]["to"] == "urn:research:project:project-200"
    assert belongs_edges[0].get("via") == "data"

    contains_edges = grouped.get("contains", [])
    contains_targets = {edge["to"] for edge in contains_edges}
    assert contains_targets == {
        "urn:research:chunk:doc-200-chunk-0",
        "urn:research:chunk:doc-200-chunk-1",
    }


def test_transform_insight_emits_edges() -> None:
    transformer = ManifestTransformer()
    result = transformer.transform_insight(
        insight_id="insight-300",
        title="Edge Insight",
        content="Insight content",
        project_id="project-300",
        source_chunk_ids=["chunk-3", "urn:research:chunk:chunk-4"],
    )

    assert result.success
    relationships = result.manifest.manifest["relationships"]
    grouped = _edges_by_type(relationships)

    belongs_edges = grouped.get("belongs_to", [])
    assert len(belongs_edges) == 1
    assert belongs_edges[0]["to"] == "urn:research:project:project-300"

    derived_edges = grouped.get("derived_from", [])
    derived_targets = {edge["to"] for edge in derived_edges}
    assert derived_targets == {
        "urn:research:chunk:chunk-3",
        "urn:research:chunk:chunk-4",
    }


def test_transform_report_emits_edges() -> None:
    transformer = ManifestTransformer()
    result = transformer.transform_report(
        report_id="report-400",
        title="Edge Report",
        content="Report content",
        project_id="project-400",
        source_chunk_ids=["chunk-5"],
    )

    assert result.success
    relationships = result.manifest.manifest["relationships"]
    grouped = _edges_by_type(relationships)

    belongs_edges = grouped.get("belongs_to", [])
    assert len(belongs_edges) == 1
    assert belongs_edges[0]["to"] == "urn:research:project:project-400"

    reference_edges = grouped.get("references", [])
    assert len(reference_edges) == 1
    assert reference_edges[0]["to"] == "urn:research:chunk:chunk-5"
