"""Integration tests for Mission Protocol API endpoints."""

from __future__ import annotations

from textwrap import dedent

from fastapi.testclient import TestClient


def _api_payload(project_id, mission_id="B3.2-api"):
    return {
        "project_id": str(project_id),
        "mission_id": mission_id,
        "title": "Protocol Engine",
        "objective": "Test API endpoint for mission creation and export workflow",
        "success_criteria": [
            "API creates mission successfully",
            "Export returns YAML",
        ],
        "context": {
            "mission_id": mission_id,
            "project_id": str(project_id),
            "title": "Protocol Engine",
        },
    }


def test_create_and_export_mission(client: TestClient, project):
    response = client.post("/api/v1/missions", json=_api_payload(project.id))
    assert response.status_code == 201
    created = response.json()
    mission_id = created["id"]
    assert created["mission_id"] == "B3.2-api"
    assert created["status"] == "draft"

    fetched = client.get(f"/api/v1/missions/{mission_id}")
    assert fetched.status_code == 200
    assert fetched.json()["mission_id"] == "B3.2-api"

    export_resp = client.get(f"/api/v1/missions/{mission_id}/export")
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"].startswith("text/yaml")
    assert "mission_id: B3.2-api" in export_resp.text


def test_export_mission_as_markdown(client: TestClient, project):
    payload = _api_payload(project.id, "B3.2-md-export")
    response = client.post("/api/v1/missions", json=payload)
    assert response.status_code == 201
    mission_id = response.json()["id"]

    export_resp = client.get(f"/api/v1/missions/{mission_id}/export?format=md")
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"].startswith("text/markdown")
    assert "Mission ID" in export_resp.text


def test_import_yaml_endpoint(client: TestClient, project):
    yaml_body = dedent(
        """
        mission_id: B3.2-import
        title: Imported via API
        research_statement:
          topic: YAML
          objective: Exercise import endpoint
          scope: Backend
        key_questions:
          - question: How to import?
            status: answered
            answer: Submit YAML payload
        synthesis:
          key_insights:
            - import works and emits telemetry.
          recommendations:
            - Watch the new quality gate endpoint.
          next_steps:
            - Hook UI widgets to the endpoint.
        evidence:
          - evidence_id: EV-API
            source: docs
            summary: Example
            chunk_id: 00000000-0000-0000-0000-000000000003
        quality_checkpoints:
          - gate: research_statement
            status: pass
          - gate: evidence_links
            status: pass
          - gate: synthesis_quality
            status: pass
          - gate: traceability
            status: pass
          - gate: contradictions_resolved
            status: pass
        """
    ).strip()

    import_resp = client.post(
        "/api/v1/missions/import",
        json={
            "project_id": str(project.id),
            "yaml_text": yaml_body,
            "promote_to_complete": False,
        },
    )
    assert import_resp.status_code == 201
    mission = import_resp.json()["mission"]
    assert mission["mission_id"] == "B3.2-import"

    list_resp = client.get(f"/api/v1/missions?project_id={project.id}")
    assert list_resp.status_code == 200
    response_data = list_resp.json()
    assert "data" in response_data, "Response should have 'data' key for consistency"
    missions = response_data["data"]
    assert any(item["mission_id"] == "B3.2-import" for item in missions)


def test_quality_endpoint_reports_gate_status(client: TestClient, project):
    payload = _api_payload(project.id, "B3.2-quality")
    create_resp = client.post("/api/v1/missions", json=payload)
    assert create_resp.status_code == 201
    mission_id = create_resp.json()["id"]

    quality_resp = client.get(f"/api/v1/missions/{mission_id}/quality")
    assert quality_resp.status_code == 200
    report = quality_resp.json()
    assert report["mission_id"] == mission_id
    assert report["protocol_mission_id"] == "B3.2-quality"
    assert set(report["gates"]) == {
        "research_statement",
        "evidence_links",
        "contradictions_resolved",
        "synthesis_quality",
        "traceability",
    }
    assert {name: gate["status"] for name, gate in report["gates"].items()} == {
        "research_statement": "fail",
        "evidence_links": "fail",
        "contradictions_resolved": "pass",
        "synthesis_quality": "fail",
        "traceability": "fail",
    }
    assert report["failing_gates"] == [
        "research_statement",
        "evidence_links",
        "synthesis_quality",
        "traceability",
    ]
    assert report["all_passed"] is False
