"""Unit tests for mission ID resolution and create-and-submit workflow."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.unit


def _mission_stub(
    *, mission_id: str = "B16.1", status: str = "draft", project_set: bool = True
):
    project_id = uuid4() if project_set else None
    return SimpleNamespace(
        id=uuid4(),
        project_id=project_id,
        project=SimpleNamespace(name="Project X") if project_set else None,
        mission_id=mission_id,
        title="Mission title",
        objective="Mission objective long enough",
        success_criteria=["Criterion"],
        context={},
        deliverables=[],
        research_phases={},
        tags=[],
        mission_metadata={},
        # Mission-authoring fields (T40.1/T40.2) the GET serializer reads directly;
        # the stub predated them, so reading them 500'd (first miss: constraints). All
        # are Optional on MissionResponse, so None is a faithful "unset" for a draft.
        constraints=None,
        background=None,
        focus=None,
        references=None,
        required_entities=None,
        excluded_entities=None,
        expected_output_schema=None,
        coverage_thresholds=None,
        validation_thresholds=None,
        deliverable_format=None,
        max_loops=None,
        min_loops=None,
        status=status,
        queued_at=None,
        started_at=None,
        completed_at=None,
        deepsearch_job_id=None,
        deepsearch_lease_owner=None,
        deepsearch_lease_token=None,
        deepsearch_leased_at=None,
        deepsearch_heartbeat_at=None,
        deepsearch_lease_expires_at=None,
        deepsearch_attempt_count=0,
        deepsearch_result_key=None,
        execution_metadata={},
        result_document_ids=[],
        result_report_id=None,
        result_markdown=None,
        result_protocol=None,
        error_message=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        created_by="tester",
    )


class _MissionServiceStub:
    def __init__(self, mission):
        self.mission = mission
        self.calls = []

    def get_mission(self, _db, mission_uuid):
        self.calls.append(("get_mission", str(mission_uuid)))
        return self.mission

    def get_mission_by_mission_id(self, _db, mission_id):
        self.calls.append(("get_mission_by_mission_id", mission_id))
        return self.mission

    def update_mission(self, _db, mission_uuid, update_data):
        self.calls.append(("update_mission", str(mission_uuid), update_data.status))
        self.mission.status = update_data.status
        return self.mission

    def create_mission(self, _db, data):
        self.calls.append(("create_mission", data.mission_id))
        self.mission.mission_id = data.mission_id
        return self.mission


@pytest.fixture
def mission_client(monkeypatch):
    import app.api.v1.missions as missions_api

    mission = _mission_stub()
    service = _MissionServiceStub(mission)

    monkeypatch.setattr(missions_api, "_service", service)
    monkeypatch.setattr(
        missions_api.settings, "deepsearch_mode", "worker", raising=False
    )

    def _fake_db():
        yield object()

    app.dependency_overrides[missions_api.get_db] = _fake_db
    with TestClient(app) as client:
        yield client, service, mission
    app.dependency_overrides.clear()


def test_get_mission_allows_human_readable_id(mission_client, auth_headers):
    client, service, mission = mission_client

    response = client.get(
        f"/api/v1/missions/{mission.mission_id}", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["mission_id"] == mission.mission_id
    assert any(call[0] == "get_mission_by_mission_id" for call in service.calls)


def test_submit_mission_allows_human_readable_id(mission_client, auth_headers):
    client, service, mission = mission_client

    response = client.post(
        f"/api/v1/missions/{mission.mission_id}/submit", headers=auth_headers
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mission_id"] == mission.mission_id
    assert payload["status"] == "queued"
    assert any(call[0] == "update_mission" for call in service.calls)


def test_create_and_submit_endpoint_queues_immediately(mission_client, auth_headers):
    client, service, mission = mission_client

    response = client.post(
        "/api/v1/missions/create-and-submit",
        json={
            "mission_id": "B22.4",
            "title": "Create and submit",
            "objective": "Create and queue this mission in a single call.",
            "success_criteria": ["Queued"],
            "project_id": str(uuid4()),
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mission_id"] == "B22.4"
    assert body["status"] == "queued"
    assert "created and" in body["message"].lower()
    assert ("create_mission", "B22.4") in service.calls


def test_submit_without_project_returns_actionable_error(monkeypatch, auth_headers):
    import app.api.v1.missions as missions_api

    mission = _mission_stub(mission_id="NOPROJ-1", project_set=False)
    service = _MissionServiceStub(mission)
    monkeypatch.setattr(missions_api, "_service", service)

    def _fake_db():
        yield object()

    app.dependency_overrides[missions_api.get_db] = _fake_db
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/missions/{mission.mission_id}/submit", headers=auth_headers
        )
    app.dependency_overrides.clear()

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "project_id" in detail["message"]
    assert detail["mission_id"] == mission.mission_id
    assert "suggestion" in detail
