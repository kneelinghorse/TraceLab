"""Integration tests for Mission Protocol API endpoints."""
from __future__ import annotations

from textwrap import dedent

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(auth_headers):
    with TestClient(app) as test_client:
        test_client.headers.update(auth_headers)
        yield test_client


def _api_payload(project_id):
    return {
        "project_id": str(project_id),
        "mission_data": {
            "mission_id": "B3.2-api",
            "title": "Protocol Engine",
            "research_statement": {
                "topic": "Protocol Engine",
                "objective": "Test API",
                "scope": "Backend",
            },
            "key_questions": [
                {"question": "How do we test?", "status": "answered", "answer": "with pytest"}
            ],
            "synthesis": {
                "key_insights": [
                    "API works end-to-end and persists telemetry-friendly quality gate outcomes."
                ],
                "recommendations": ["Monitor quality gate endpoint from UI"],
                "next_steps": ["Publish integration test coverage"],
            },
            "evidence": [
                {
                    "evidence_id": "EV-api",
                    "source": "docs/mission_protocol_validation.md",
                    "summary": "Spec",
                    "chunk_id": "00000000-0000-0000-0000-000000000002",
                }
            ],
            "quality_checkpoints": [
                {"gate": "research_statement", "status": "pass"},
                {"gate": "evidence_links", "status": "pass"},
                {"gate": "synthesis_quality", "status": "pass"},
                {"gate": "traceability", "status": "pass"},
                {"gate": "contradictions_resolved", "status": "pass"},
            ],
        },
    }


def test_create_and_export_mission(client: TestClient, project):
    response = client.post("/api/v1/missions/", json=_api_payload(project.id))
    assert response.status_code == 201
    created = response.json()
    mission_id = created["id"]
    assert created["status"] == "complete"

    fetched = client.get(f"/api/v1/missions/{mission_id}")
    assert fetched.status_code == 200
    assert fetched.json()["mission_data"]["mission_id"] == "B3.2-api"

    export_resp = client.get(f"/api/v1/missions/{mission_id}/export")
    assert export_resp.status_code == 200
    assert "mission_id: B3.2-api" in export_resp.json()["yaml_text"]


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
    assert mission["mission_data"]["mission_id"] == "B3.2-import"

    list_resp = client.get(f"/api/v1/missions/?project_id={project.id}")
    assert list_resp.status_code == 200
    missions = list_resp.json()
    assert any(item["mission_data"]["mission_id"] == "B3.2-import" for item in missions)


def test_quality_endpoint_reports_gate_status(client: TestClient, project):
    create_resp = client.post("/api/v1/missions/", json=_api_payload(project.id))
    assert create_resp.status_code == 201
    mission_id = create_resp.json()["id"]

    quality_resp = client.get(f"/api/v1/missions/{mission_id}/quality")
    assert quality_resp.status_code == 200
    payload = quality_resp.json()
    assert payload["all_passed"] is True
    assert "research_statement" in payload["gates"]
