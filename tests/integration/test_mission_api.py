"""Integration tests for Mission Protocol API endpoints."""
from __future__ import annotations

from textwrap import dedent

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
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
            "synthesis": {"key_insights": ["API works"]},
            "evidence": [
                {
                    "evidence_id": "EV-api",
                    "source": "docs/mission_protocol_validation.md",
                    "summary": "Spec",
                }
            ],
            "quality_checkpoints": [
                {"gate": "research_alignment", "status": "pass"},
                {"gate": "evidence_traceability", "status": "pass"},
                {"gate": "synthesis_depth", "status": "pass"},
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
            - import works
        evidence:
          - evidence_id: EV-API
            source: docs
            summary: Example
        quality_checkpoints:
          - gate: research_alignment
            status: pass
          - gate: evidence_traceability
            status: pass
          - gate: synthesis_depth
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
