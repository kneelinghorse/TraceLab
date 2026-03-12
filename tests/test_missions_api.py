"""Tests for the missions CRUD API endpoints (B16.2)."""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.mission import Mission
from app.models.project import Project
from app.schemas.mission import MissionCreate, MissionUpdate, MissionResponse


def _create_test_project(db_session) -> Project:
    """Create a test project."""
    project = Project(name="Test Project", description="For testing")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _create_test_mission(
    db_session,
    mission_id: str = "TEST-001",
    title: str = "Test Mission",
    status: str = "draft",
    project_id=None,
) -> Mission:
    """Create a test mission."""
    mission = Mission(
        mission_id=mission_id,
        title=title,
        objective="Test objective",
        success_criteria=["Criterion 1", "Criterion 2"],
        status=status,
        project_id=project_id,
        context={"key": "value"},
        deliverables=["Deliverable 1"],
        tags=["test", "api"],
    )
    db_session.add(mission)
    db_session.commit()
    db_session.refresh(mission)
    return mission


class TestMissionSchemas:
    """Tests for mission Pydantic schemas."""

    def test_mission_create_minimal(self):
        """Test MissionCreate with minimal required fields."""
        data = MissionCreate(
            mission_id="B16.1",
            title="Test Mission",
            objective="Test objective",
            success_criteria=["Criterion 1"],
        )
        assert data.mission_id == "B16.1"
        assert data.title == "Test Mission"
        assert data.status == "draft"

    def test_mission_create_full(self):
        """Test MissionCreate with all fields."""
        data = MissionCreate(
            mission_id="B16.2",
            title="Full Mission",
            objective="Complete objective",
            success_criteria=["Criterion 1", "Criterion 2"],
            project_id=uuid.uuid4(),
            context={"key": "value"},
            deliverables=["File 1", "File 2"],
            research_phases={"phase1": "research"},
            tags=["api", "test"],
            metadata={"custom": "data"},
            status="queued",
            created_by="test-agent",
        )
        assert data.mission_id == "B16.2"
        assert data.status == "queued"
        assert len(data.deliverables) == 2

    def test_mission_create_empty_criteria_fails(self):
        """Test that empty success_criteria fails validation."""
        with pytest.raises(ValueError, match="too_short|success_criteria must contain"):
            MissionCreate(
                mission_id="B16.1",
                title="Test Mission",
                objective="Test objective for validation",
                success_criteria=[],
            )

    def test_mission_create_short_title_fails(self):
        """Test that short title fails validation."""
        with pytest.raises(ValueError):
            MissionCreate(
                mission_id="B16.1",
                title="AB",  # Too short
                objective="Test",
                success_criteria=["Criterion"],
            )

    def test_mission_update_partial(self):
        """Test MissionUpdate accepts partial updates."""
        data = MissionUpdate(title="New Title")
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"title": "New Title"}

    def test_mission_update_status(self):
        """Test MissionUpdate with status change."""
        data = MissionUpdate(status="in_progress")
        assert data.status == "in_progress"


class TestMissionService:
    """Tests for MissionService methods."""

    def test_service_methods_exist(self):
        """Test that service has all required methods."""
        from app.services.mission_service import MissionService

        service = MissionService()
        assert hasattr(service, "list_missions")
        assert hasattr(service, "get_mission")
        assert hasattr(service, "create_mission")
        assert hasattr(service, "update_mission")
        assert hasattr(service, "delete_mission")

    def test_service_constants(self):
        """Test service pagination constants."""
        from app.services.mission_service import MissionService

        assert MissionService.DEFAULT_PAGE_SIZE == 20
        assert MissionService.MAX_PAGE_SIZE == 100


class TestMissionCreate:
    """Tests for POST /api/v1/missions endpoint."""

    def test_create_mission_minimal(self, auth_headers, db_session):
        """Create mission with minimal required fields."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/missions",
            json={
                "mission_id": "B16.TEST",
                "title": "Test Mission",
                "objective": "Test objective",
                "success_criteria": ["Criterion 1"],
            },
            headers=auth_headers,
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["mission_id"] == "B16.TEST"
        assert data["title"] == "Test Mission"
        assert data["status"] == "draft"
        assert "id" in data
        assert "created_at" in data

    def test_create_mission_full(self, auth_headers, db_session):
        """Create mission with all optional fields."""
        client = TestClient(app)
        project = _create_test_project(db_session)

        response = client.post(
            "/api/v1/missions",
            json={
                "mission_id": "B16.FULL",
                "title": "Full Mission",
                "objective": "Complete objective description",
                "success_criteria": ["Criterion 1", "Criterion 2", "Criterion 3"],
                "project_id": str(project.id),
                "context": {"background": "Some background info"},
                "deliverables": ["app/file1.py", "app/file2.py"],
                "research_phases": {"phase1": {"task": "research"}},
                "tags": ["api", "test", "crud"],
                "metadata": {"priority": "high"},
                "status": "queued",
                "created_by": "test-agent",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["mission_id"] == "B16.FULL"
        assert data["status"] == "queued"
        assert data["project_id"] == str(project.id)
        assert len(data["success_criteria"]) == 3
        assert data["queued_at"] is not None  # Should be set for queued status
        assert data["created_by"] == "test-agent"

    def test_create_mission_duplicate_fails(self, auth_headers, db_session):
        """Creating mission with duplicate mission_id fails."""
        client = TestClient(app)

        # Create first mission
        _create_test_mission(db_session, mission_id="DUPLICATE-001")

        # Try to create duplicate
        response = client.post(
            "/api/v1/missions",
            json={
                "mission_id": "DUPLICATE-001",
                "title": "Duplicate Mission",
                "objective": "Test duplicate detection",
                "success_criteria": ["Test criterion"],
            },
            headers=auth_headers,
        )

        assert response.status_code == 409

    def test_create_mission_validation_error(self, auth_headers):
        """Creating mission with invalid data fails."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/missions",
            json={
                "mission_id": "B16.TEST",
                "title": "AB",  # Too short
                "objective": "Test",
                "success_criteria": ["Test"],
            },
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_create_mission_empty_criteria_fails(self, auth_headers):
        """Creating mission with empty success_criteria fails."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/missions",
            json={
                "mission_id": "B16.TEST",
                "title": "Valid Title",
                "objective": "Test",
                "success_criteria": [],
            },
            headers=auth_headers,
        )

        assert response.status_code == 422


class TestMissionList:
    """Tests for GET /api/v1/missions endpoint."""

    def test_list_missions_empty(self, auth_headers, db_session):
        """List missions when none exist."""
        client = TestClient(app)

        response = client.get("/api/v1/missions", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["pagination"]["total"] == 0
        assert data["pagination"]["page"] == 1

    def test_list_missions_with_data(self, auth_headers, db_session):
        """List missions when they exist."""
        client = TestClient(app)

        _create_test_mission(db_session, mission_id="LIST-001")
        _create_test_mission(db_session, mission_id="LIST-002")

        response = client.get("/api/v1/missions", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total"] == 2
        assert len(data["data"]) == 2

    def test_list_missions_filter_by_status(self, auth_headers, db_session):
        """List missions filtered by status."""
        client = TestClient(app)

        _create_test_mission(db_session, mission_id="FILTER-001", status="draft")
        _create_test_mission(db_session, mission_id="FILTER-002", status="in_progress")
        _create_test_mission(db_session, mission_id="FILTER-003", status="completed")

        response = client.get(
            "/api/v1/missions?status=in_progress",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total"] == 1
        assert data["data"][0]["status"] == "in_progress"

    def test_list_missions_filter_by_project(self, auth_headers, db_session):
        """List missions filtered by project."""
        client = TestClient(app)

        project = _create_test_project(db_session)
        _create_test_mission(db_session, mission_id="PROJ-001", project_id=project.id)
        _create_test_mission(db_session, mission_id="PROJ-002", project_id=None)

        response = client.get(
            f"/api/v1/missions?project_id={project.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total"] == 1
        assert data["data"][0]["mission_id"] == "PROJ-001"

    def test_list_missions_combined_filters(self, auth_headers, db_session):
        """List missions with both status and project filters."""
        client = TestClient(app)

        project = _create_test_project(db_session)
        _create_test_mission(db_session, mission_id="COMBO-001", status="draft", project_id=project.id)
        _create_test_mission(db_session, mission_id="COMBO-002", status="in_progress", project_id=project.id)
        _create_test_mission(db_session, mission_id="COMBO-003", status="draft", project_id=None)

        response = client.get(
            f"/api/v1/missions?status=draft&project_id={project.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total"] == 1
        assert data["data"][0]["mission_id"] == "COMBO-001"

    def test_list_missions_invalid_status(self, auth_headers):
        """List missions with invalid status returns 400."""
        client = TestClient(app)

        response = client.get(
            "/api/v1/missions?status=invalid_status",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]

    def test_list_missions_pagination(self, auth_headers, db_session):
        """Test mission list pagination."""
        client = TestClient(app)

        # Create 5 missions
        for i in range(5):
            _create_test_mission(db_session, mission_id=f"PAGE-{i:03d}")

        # Get page 1 with 2 items
        response = client.get(
            "/api/v1/missions?page=1&page_size=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total"] == 5
        assert len(data["data"]) == 2
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 2
        assert data["pagination"]["pages"] == 3

    def test_list_missions_page_2(self, auth_headers, db_session):
        """Test getting second page of missions."""
        client = TestClient(app)

        for i in range(5):
            _create_test_mission(db_session, mission_id=f"PAGE2-{i:03d}")

        response = client.get(
            "/api/v1/missions?page=2&page_size=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["page"] == 2
        assert len(data["data"]) == 2


class TestMissionGet:
    """Tests for GET /api/v1/missions/{id} endpoint."""

    def test_get_mission(self, auth_headers, db_session):
        """Get a single mission by ID."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="GET-001")

        response = client.get(
            f"/api/v1/missions/{mission.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(mission.id)
        assert data["mission_id"] == "GET-001"
        assert data["title"] == "Test Mission"
        assert "created_at" in data
        assert "updated_at" in data

    def test_get_mission_by_human_readable_id(self, auth_headers, db_session):
        """Get mission by mission_id string."""
        client = TestClient(app)
        mission = _create_test_mission(db_session, mission_id="GET-HUMAN-001")

        response = client.get(
            f"/api/v1/missions/{mission.mission_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(mission.id)
        assert data["mission_id"] == "GET-HUMAN-001"

    def test_get_mission_not_found(self, auth_headers):
        """Get non-existent mission returns 404."""
        client = TestClient(app)
        fake_id = str(uuid.uuid4())

        response = client.get(
            f"/api/v1/missions/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_get_mission_invalid_identifier_returns_404(self, auth_headers):
        """Unknown non-UUID identifiers are treated as mission_id and return 404."""
        client = TestClient(app)

        response = client.get(
            "/api/v1/missions/not-a-uuid",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestMissionUpdate:
    """Tests for PUT /api/v1/missions/{id} endpoint."""

    def test_update_mission_title(self, auth_headers, db_session):
        """Update mission title."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="UPDATE-001")

        response = client.put(
            f"/api/v1/missions/{mission.id}",
            json={"title": "Updated Title"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    def test_update_mission_status(self, auth_headers, db_session):
        """Update mission status."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="STATUS-001", status="draft")

        response = client.put(
            f"/api/v1/missions/{mission.id}",
            json={"status": "in_progress"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
        assert data["started_at"] is not None

    def test_update_mission_complete(self, auth_headers, db_session):
        """Update mission to completed status."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="COMPLETE-001", status="in_progress")

        response = client.put(
            f"/api/v1/missions/{mission.id}",
            json={"status": "completed"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["completed_at"] is not None

    def test_update_mission_multiple_fields(self, auth_headers, db_session):
        """Update multiple mission fields."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="MULTI-001")

        response = client.put(
            f"/api/v1/missions/{mission.id}",
            json={
                "title": "New Title",
                "objective": "New objective",
                "tags": ["new", "tags"],
                "metadata": {"updated": True},
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Title"
        assert data["objective"] == "New objective"
        assert "new" in data["tags"]
        assert data["metadata"]["updated"] is True

    def test_update_mission_invalid_status(self, auth_headers, db_session):
        """Update mission with invalid status fails."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="INVALID-001")

        response = client.put(
            f"/api/v1/missions/{mission.id}",
            json={"status": "not_a_status"},
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_update_mission_not_found(self, auth_headers):
        """Update non-existent mission returns 404."""
        client = TestClient(app)
        fake_id = str(uuid.uuid4())

        response = client.put(
            f"/api/v1/missions/{fake_id}",
            json={"title": "New Title"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_update_mission_results(self, auth_headers, db_session):
        """Update mission with result fields."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="RESULTS-001")
        doc_id = str(uuid.uuid4())

        response = client.put(
            f"/api/v1/missions/{mission.id}",
            json={
                "result_markdown": "# Results\n\nMission completed successfully.",
                "result_document_ids": [doc_id],
                "execution_metadata": {"duration_ms": 5000},
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "# Results" in data["result_markdown"]
        assert doc_id in data["result_document_ids"]


class TestMissionDelete:
    """Tests for DELETE /api/v1/missions/{id} endpoint."""

    def test_delete_mission(self, auth_headers, db_session):
        """Delete a mission."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="DELETE-001")
        mission_id = str(mission.id)

        response = client.delete(
            f"/api/v1/missions/{mission_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deleted
        verify_resp = client.get(
            f"/api/v1/missions/{mission_id}",
            headers=auth_headers,
        )
        assert verify_resp.status_code == 404

    def test_delete_mission_not_found(self, auth_headers):
        """Delete non-existent mission returns 404."""
        client = TestClient(app)
        fake_id = str(uuid.uuid4())

        response = client.delete(
            f"/api/v1/missions/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestMissionAuthentication:
    """Tests for authentication requirements."""

    def test_list_missions_requires_auth(self):
        """List missions requires authentication."""
        client = TestClient(app)
        response = client.get("/api/v1/missions")
        assert response.status_code == 401

    def test_create_mission_requires_auth(self):
        """Create mission requires authentication."""
        client = TestClient(app)
        response = client.post(
            "/api/v1/missions",
            json={
                "mission_id": "AUTH-001",
                "title": "Test",
                "objective": "Test",
                "success_criteria": ["Test"],
            },
        )
        assert response.status_code == 401

    def test_get_mission_requires_auth(self):
        """Get mission requires authentication."""
        client = TestClient(app)
        response = client.get(f"/api/v1/missions/{uuid.uuid4()}")
        assert response.status_code == 401

    def test_update_mission_requires_auth(self):
        """Update mission requires authentication."""
        client = TestClient(app)
        response = client.put(
            f"/api/v1/missions/{uuid.uuid4()}",
            json={"title": "Test"},
        )
        assert response.status_code == 401

    def test_delete_mission_requires_auth(self):
        """Delete mission requires authentication."""
        client = TestClient(app)
        response = client.delete(f"/api/v1/missions/{uuid.uuid4()}")
        assert response.status_code == 401


class TestMissionStatusTransitions:
    """Tests for mission status transitions and timestamps."""

    def test_draft_to_queued_sets_queued_at(self, auth_headers, db_session):
        """Transitioning from draft to queued sets queued_at."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="TRANS-001", status="draft")
        assert mission.queued_at is None

        response = client.put(
            f"/api/v1/missions/{mission.id}",
            json={"status": "queued"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["queued_at"] is not None

    def test_queued_to_in_progress_sets_started_at(self, auth_headers, db_session):
        """Transitioning from queued to in_progress sets started_at."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="TRANS-002", status="queued")

        response = client.put(
            f"/api/v1/missions/{mission.id}",
            json={"status": "in_progress"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["started_at"] is not None

    def test_in_progress_to_completed_sets_completed_at(self, auth_headers, db_session):
        """Transitioning from in_progress to completed sets completed_at."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="TRANS-003", status="in_progress")

        response = client.put(
            f"/api/v1/missions/{mission.id}",
            json={"status": "completed"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["completed_at"] is not None

    def test_all_valid_statuses(self, auth_headers, db_session):
        """Test all valid status values."""
        client = TestClient(app)
        valid_statuses = ["draft", "queued", "in_progress", "completed", "blocked", "cancelled"]

        for i, status in enumerate(valid_statuses):
            response = client.post(
                "/api/v1/missions",
                json={
                    "mission_id": f"STAT-{i:03d}",
                    "title": f"Status {status}",
                    "objective": "Test status transitions for validation",
                    "success_criteria": ["Test criterion"],
                    "status": status,
                },
                headers=auth_headers,
            )
            assert response.status_code == 201, f"Failed for status: {status}"
            assert response.json()["status"] == status


class TestMissionSubmit:
    """Tests for the POST /missions/{id}/submit endpoint."""

    def test_submit_mission_success(self, auth_headers, db_session):
        """Successfully submit a draft mission with project."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session, mission_id="SUBMIT-001", status="draft", project_id=project.id
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "queued"
        assert data["mission_id"] == "SUBMIT-001"
        assert data["uuid"] == str(mission.id)
        assert "message" in data
        assert data["mode"] in ("worker", "http")

    def test_submit_mission_by_human_readable_id(self, auth_headers, db_session):
        """Submit accepts mission_id path parameter (not only UUID)."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session, mission_id="SUBMIT-HUMAN-001", status="draft", project_id=project.id
        )

        response = client.post(
            f"/api/v1/missions/{mission.mission_id}/submit",
            headers=auth_headers,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["mission_id"] == "SUBMIT-HUMAN-001"
        assert payload["uuid"] == str(mission.id)

    def test_submit_mission_without_project_fails(self, auth_headers, db_session):
        """Cannot submit a mission without a project."""
        client = TestClient(app)
        mission = _create_test_mission(
            db_session, mission_id="SUBMIT-NOPROJECT", status="draft", project_id=None
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert "project" in data["detail"]["message"].lower()
        assert data["detail"]["mission_id"] == mission.mission_id
        assert data["detail"]["uuid"] == str(mission.id)
        assert "suggestion" in data["detail"]

    def test_submit_mission_not_found(self, auth_headers):
        """Submit non-existent mission returns 404."""
        client = TestClient(app)
        fake_id = uuid.uuid4()

        response = client.post(
            f"/api/v1/missions/{fake_id}/submit",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_submit_mission_already_queued(self, auth_headers, db_session):
        """Cannot submit a mission that is already queued."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session, mission_id="SUBMIT-002", status="queued", project_id=project.id
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "already queued" in detail["message"]

    def test_submit_mission_in_progress(self, auth_headers, db_session):
        """Cannot submit a mission that is in progress."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session, mission_id="SUBMIT-003", status="in_progress", project_id=project.id
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "already in_progress" in detail["message"]

    def test_submit_completed_mission(self, auth_headers, db_session):
        """Can resubmit a completed mission."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session, mission_id="SUBMIT-004", status="completed", project_id=project.id
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )

        # Completed missions can be resubmitted
        assert response.status_code == 200
        assert response.json()["status"] == "queued"

    def test_submit_mission_updates_status_in_db(self, auth_headers, db_session):
        """Submit should update the mission status in the database."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session, mission_id="SUBMIT-005", status="draft", project_id=project.id
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Verify in database
        db_session.refresh(mission)
        assert mission.status == "queued"


class TestCreateAndSubmitMission:
    """Tests for POST /api/v1/missions/create-and-submit endpoint."""

    def test_create_and_submit_success(self, auth_headers, db_session):
        client = TestClient(app)
        project = _create_test_project(db_session)

        response = client.post(
            "/api/v1/missions/create-and-submit",
            json={
                "mission_id": "CREATE-SUBMIT-001",
                "title": "Create and submit",
                "objective": "Create and immediately queue this mission for execution.",
                "success_criteria": ["Queued for DeepSearch"],
                "project_id": str(project.id),
            },
            headers=auth_headers,
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["status"] == "queued"
        assert data["mission_id"] == "CREATE-SUBMIT-001"
        assert "created and" in data["message"].lower()

    def test_create_and_submit_without_project_returns_actionable_error(self, auth_headers):
        client = TestClient(app)

        response = client.post(
            "/api/v1/missions/create-and-submit",
            json={
                "mission_id": "CREATE-SUBMIT-002",
                "title": "Create and submit without project",
                "objective": "This should fail with an actionable project assignment suggestion.",
                "success_criteria": ["Should fail"],
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "project_id" in detail["message"]
        assert "suggestion" in detail
