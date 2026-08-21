"""Tests for the missions CRUD API endpoints (B16.2)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
from app.schemas.mission import MissionCreate, MissionUpdate

# T41.6 (sprint-41): MissionCreate.project_id is required as of this sprint.
# Tests construct MissionCreate to test OTHER validators (mission_id format,
# title length, etc.) — they need a stable project_id supplied so the
# under-test field validation runs instead of failing on missing project_id.
_TEST_PROJECT_ID = uuid.uuid4()


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
            project_id=_TEST_PROJECT_ID,
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
                project_id=_TEST_PROJECT_ID,
                mission_id="B16.1",
                title="Test Mission",
                objective="Test objective for validation",
                success_criteria=[],
            )

    def test_mission_create_short_title_fails(self):
        """Test that short title fails validation."""
        with pytest.raises(ValueError):
            MissionCreate(
                project_id=_TEST_PROJECT_ID,
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
        """Create mission with minimal required fields.

        T41.6: project_id is required at create time. Pre-T41.6 missions
        could be created without it (saved as orphan drafts) — that path
        is now blocked.
        """
        client = TestClient(app)
        project = _create_test_project(db_session)

        response = client.post(
            "/api/v1/missions",
            json={
                "mission_id": "B16.TEST",
                "title": "Test Mission",
                "objective": "Test objective",
                "success_criteria": ["Criterion 1"],
                "project_id": str(project.id),
            },
            headers=auth_headers,
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["mission_id"] == "B16.TEST"
        assert data["title"] == "Test Mission"
        assert data["status"] == "draft"
        assert data["project_id"] == str(project.id)
        assert "id" in data
        assert "created_at" in data

    def test_create_mission_without_project_id_returns_422(
        self, auth_headers, db_session
    ):
        """T41.6: missing project_id at create returns 422 with actionable error.

        Origin: sprint-41 user feedback that orphan missions were hard to
        find. Validation now blocks the orphan-creation path before any
        DB write. Pre-T41.6 there were 5 such orphans across 375 missions
        (1.3%) — they remain readable via GET.
        """
        client = TestClient(app)
        response = client.post(
            "/api/v1/missions",
            json={
                "mission_id": "B16.NOPROJ",
                "title": "Orphan Mission",
                "objective": "Should fail without project_id",
                "success_criteria": ["any"],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422
        body = response.json()
        # Pydantic field-required error surfaces in detail[].loc
        detail = body.get("detail")
        assert isinstance(detail, list)
        assert any(
            err.get("loc") == ["body", "project_id"]
            and err.get("type") == "missing"
            for err in detail
        ), f"Expected missing-project_id field error, got {detail}"

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
        project = _create_test_project(db_session)

        # Create first mission
        _create_test_mission(
            db_session, mission_id="DUPLICATE-001", project_id=project.id
        )

        # Try to create duplicate
        response = client.post(
            "/api/v1/missions",
            json={
                "mission_id": "DUPLICATE-001",
                "title": "Duplicate Mission",
                "objective": "Test duplicate detection",
                "success_criteria": ["Test criterion"],
                "project_id": str(project.id),
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
        _create_test_mission(
            db_session, mission_id="COMBO-001", status="draft", project_id=project.id
        )
        _create_test_mission(
            db_session,
            mission_id="COMBO-002",
            status="in_progress",
            project_id=project.id,
        )
        _create_test_mission(
            db_session, mission_id="COMBO-003", status="draft", project_id=None
        )

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
    """Tests for PATCH /api/v1/missions/{id} endpoint."""

    def test_update_mission_title(self, auth_headers, db_session):
        """Update mission title."""
        client = TestClient(app)

        mission = _create_test_mission(db_session, mission_id="UPDATE-001")

        response = client.patch(
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

        mission = _create_test_mission(
            db_session, mission_id="STATUS-001", status="draft"
        )

        response = client.patch(
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

        mission = _create_test_mission(
            db_session, mission_id="COMPLETE-001", status="in_progress"
        )

        response = client.patch(
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

        response = client.patch(
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

        response = client.patch(
            f"/api/v1/missions/{mission.id}",
            json={"status": "not_a_status"},
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_update_mission_not_found(self, auth_headers):
        """Update non-existent mission returns 404."""
        client = TestClient(app)
        fake_id = str(uuid.uuid4())

        response = client.patch(
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

        response = client.patch(
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


class TestT41_5UpdateProjectId:
    """T41.5: project_id is mutable on existing missions via PATCH.

    Pre-T41.5 missions were stuck with their original project assignment
    forever. Re-parenting requires the target project to exist (404 if not)
    and otherwise behaves like any other field update — works on any
    status, doesn't touch other immutable fields (id, mission_id,
    created_at).
    """

    def test_reparent_mission_to_existing_project(self, auth_headers, db_session):
        client = TestClient(app)
        original_project = _create_test_project(db_session)
        new_project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session,
            mission_id="REPARENT-001",
            project_id=original_project.id,
        )

        response = client.patch(
            f"/api/v1/missions/{mission.id}",
            json={"project_id": str(new_project.id)},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["project_id"] == str(new_project.id)
        assert data["project_id"] != str(original_project.id)

    def test_reparent_to_nonexistent_project_returns_404(
        self, auth_headers, db_session
    ):
        client = TestClient(app)
        mission = _create_test_mission(db_session, mission_id="REPARENT-002")
        bogus_project_id = uuid.uuid4()

        response = client.patch(
            f"/api/v1/missions/{mission.id}",
            json={"project_id": str(bogus_project_id)},
            headers=auth_headers,
        )

        assert response.status_code == 404, response.text
        detail = response.json()["detail"]
        assert "does not exist" in detail["message"]
        assert "suggestion" in detail
        assert str(bogus_project_id) in detail["message"]

    def test_reparent_works_on_completed_mission(self, auth_headers, db_session):
        """Re-parent allowed regardless of mission status — useful for
        misfiled completed research."""
        client = TestClient(app)
        original = _create_test_project(db_session)
        new_project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session,
            mission_id="REPARENT-003",
            project_id=original.id,
            status="completed",
        )

        response = client.patch(
            f"/api/v1/missions/{mission.id}",
            json={"project_id": str(new_project.id)},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["project_id"] == str(new_project.id)

    def test_immutable_fields_remain_immutable(self, auth_headers, db_session):
        """Re-parent must not allow mission_id, id, or created_at to change."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        new_project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session, mission_id="REPARENT-004", project_id=project.id
        )
        original_uuid = str(mission.id)
        original_mission_id = mission.mission_id
        original_created_at = mission.created_at.isoformat()

        # Attempt to update project_id AND immutable fields in same call.
        # Pydantic rejects unknown fields silently; we just want to confirm
        # nothing here mutates them.
        response = client.patch(
            f"/api/v1/missions/{mission.id}",
            json={
                "project_id": str(new_project.id),
                "mission_id": "TRY-TO-CHANGE-ME",  # silently dropped
                "id": str(uuid.uuid4()),  # silently dropped
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == original_uuid
        assert data["mission_id"] == original_mission_id
        assert data["created_at"].startswith(original_created_at[:19])
        assert data["project_id"] == str(new_project.id)

    def test_update_without_project_id_leaves_existing_value(
        self, auth_headers, db_session
    ):
        """Updates that omit project_id must NOT clear the existing value."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session, mission_id="REPARENT-005", project_id=project.id
        )

        response = client.patch(
            f"/api/v1/missions/{mission.id}",
            json={"title": "Renamed"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["project_id"] == str(project.id)


class TestMissionAuthoringFieldsRoundTrip:
    """T40.2 smoke: POST /missions with all authoring fields then GET them back."""

    def _full_authoring_payload(self) -> dict:
        return {
            "background": "Teams keep conflating Contrast-Consistent Search with CCS-style probing.",
            "focus": "Only papers benchmarking CCS against supervised probing baselines.",
            "references": [
                {"title": "Contrast-Consistent Search (Burns et al. 2022)"},
                {"title": "Linear probing limitations (Alain & Bengio 2016)"},
            ],
            "required_entities": ["Contrast-Consistent Search", "CCS", "latent truth"],
            "excluded_entities": ["Amazon CloudFront", "CCS Insurance"],
            "expected_output_schema": {
                "type": "object",
                "properties": {
                    "executive_summary": {"type": "string"},
                    "comparison_table": {"type": "array"},
                },
            },
            "coverage_thresholds": {"min_sources": 12, "min_per_required_entity": 2},
            "validation_thresholds": {"structural": 0.85, "coverage": 0.70},
            "deliverable_format": "executive summary with comparison table",
            "max_loops": 6,
            "min_loops": 3,
            "constraints": ["no paywalled sources", "prefer peer-reviewed"],
        }

    def test_create_and_get_round_trips_every_authoring_field(
        self, auth_headers, db_session
    ):
        client = TestClient(app)
        project = _create_test_project(db_session)
        payload = {
            "mission_id": "AUTH-ROUND-1",
            "title": "Authoring round-trip",
            "objective": "Verify every authoring field survives POST then GET.",
            "success_criteria": ["Every field round-trips"],
            "project_id": str(project.id),
            **self._full_authoring_payload(),
        }

        create = client.post("/api/v1/missions", json=payload, headers=auth_headers)
        assert create.status_code == 201, create.text
        created_body = create.json()
        mission_uuid = created_body["id"]

        # First: the create response itself should already expose the fields.
        for field, value in self._full_authoring_payload().items():
            assert created_body.get(field) == value, (
                f"CREATE: field {field} not in response: got "
                f"{created_body.get(field)!r}, full body keys: {list(created_body.keys())}"
            )

        get = client.get(f"/api/v1/missions/{mission_uuid}", headers=auth_headers)
        assert get.status_code == 200, get.text
        body = get.json()

        for field, value in self._full_authoring_payload().items():
            assert body[field] == value, f"field {field} did not round-trip: {body.get(field)!r}"

    def test_patch_updates_authoring_fields(self, auth_headers, db_session):
        client = TestClient(app)
        project = _create_test_project(db_session)
        create = client.post(
            "/api/v1/missions",
            json={
                "mission_id": "AUTH-ROUND-2",
                "title": "PATCH round-trip",
                "objective": "Verify PATCH touches every authoring field.",
                "success_criteria": ["Every field round-trips"],
                "project_id": str(project.id),
            },
            headers=auth_headers,
        )
        assert create.status_code == 201, create.text
        mission_uuid = create.json()["id"]

        patch = client.patch(
            f"/api/v1/missions/{mission_uuid}",
            json=self._full_authoring_payload(),
            headers=auth_headers,
        )
        assert patch.status_code == 200, patch.text
        body = patch.json()
        for field, value in self._full_authoring_payload().items():
            assert body[field] == value, f"PATCH did not persist {field}"

    def test_constraints_fallback_via_context(self, auth_headers, db_session):
        """Legacy missions with constraints in context still surface them in the API response."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        create = client.post(
            "/api/v1/missions",
            json={
                "mission_id": "AUTH-FALLBACK-1",
                "title": "Legacy constraints",
                "objective": "Mission with constraints only in context.",
                "success_criteria": ["Fallback works"],
                "project_id": str(project.id),
                "context": {"constraints": ["legacy constraint"]},
            },
            headers=auth_headers,
        )
        assert create.status_code == 201, create.text
        body = create.json()
        assert body["constraints"] == ["legacy constraint"]


class TestMissionVerbContract:
    """Regression guards for the MCP↔API verb contract.

    Sprint 40 T40.0: MCP sent PATCH while the API handler was PUT, producing
    405s in every environment. These tests lock the contract so a future
    refactor cannot silently break `update_mission` or `submit_mission`.
    """

    def test_patch_update_mission_returns_200(self, auth_headers, db_session):
        """PATCH is the canonical verb for partial mission updates."""
        client = TestClient(app)
        mission = _create_test_mission(db_session, mission_id="VERB-PATCH-001")

        response = client.patch(
            f"/api/v1/missions/{mission.id}",
            json={"title": "PATCH works"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["title"] == "PATCH works"

    def test_put_update_mission_returns_405(self, auth_headers, db_session):
        """PUT must not be registered — the MCP client uses PATCH."""
        client = TestClient(app)
        mission = _create_test_mission(db_session, mission_id="VERB-PUT-001")

        response = client.put(
            f"/api/v1/missions/{mission.id}",
            json={"title": "PUT should fail"},
            headers=auth_headers,
        )

        assert response.status_code == 405

    def test_post_submit_mission_route_exists(self, auth_headers, db_session):
        """POST /{id}/submit must exist (not 405/404) — regression for main-branch staleness."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session,
            mission_id="VERB-SUBMIT-001",
            status="draft",
            project_id=project.id,
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )

        assert response.status_code not in (404, 405), (
            f"submit route missing in deployed code: got {response.status_code}"
        )

    def test_status_route_is_lightweight_and_hides_worker_proofs(
        self, auth_headers, db_session
    ):
        """Frequent MCP polls must not download results or leak lease tokens."""
        client = TestClient(app)
        mission = _create_test_mission(
            db_session,
            mission_id="STATUS-LIGHT-001",
            status="completed",
        )
        mission.result_markdown = "# Large result\n" + ("x" * 20_000)
        mission.result_protocol = {"large": "y" * 20_000}
        mission.deepsearch_attempt_count = 2
        mission.deepsearch_lease_token = uuid.uuid4().hex
        mission.deepsearch_result_key = uuid.uuid4().hex
        db_session.commit()

        response = client.get(
            f"/api/v1/missions/{mission.id}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["mission_id"] == "STATUS-LIGHT-001"
        assert body["status"] == "completed"
        assert body["deepsearch_attempt_count"] == 2
        assert body["materialization_pending"] is True
        assert body["search_ready"] is False
        assert "result_markdown" not in body
        assert "result_protocol" not in body
        assert "execution_metadata" not in body
        assert "deepsearch_lease_token" not in body
        assert "deepsearch_result_key" not in body

    def test_status_route_reports_search_ready_only_for_processed_linked_document(
        self, auth_headers, db_session
    ):
        """Terminal status is ready only after its linked result is searchable."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session,
            mission_id="STATUS-READY-001",
            status="completed",
            project_id=project.id,
        )
        mission.result_markdown = "# Searchable result"
        mission.execution_metadata = {
            "progress_percent": 100,
            "current_phase": "complete",
        }
        document = Document(
            project_id=project.id,
            name="Searchable result.md",
            content=mission.result_markdown,
            processed=True,
            chunked=True,
            embedded=True,
            source_mission_id=mission.id,
        )
        db_session.add(document)
        db_session.commit()
        mission.result_document_ids = [str(document.id)]
        db_session.commit()

        response = client.get(
            f"/api/v1/missions/{mission.id}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["progress_percent"] == 100
        assert body["current_phase"] == "complete"
        assert body["result_document_ids"] == [str(document.id)]
        assert body["search_ready"] is True
        assert body["materialization_pending"] is False

    def test_status_route_tolerates_malformed_legacy_document_id(
        self, auth_headers, db_session
    ):
        """Corrupt legacy linkage is visible as pending, not a polling 500."""
        client = TestClient(app)
        mission = _create_test_mission(
            db_session,
            mission_id="STATUS-LEGACY-001",
            status="completed",
        )
        mission.result_markdown = "# Result awaiting link repair"
        mission.result_document_ids = ["not-a-uuid"]
        db_session.commit()

        response = client.get(
            f"/api/v1/missions/{mission.id}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["result_document_ids"] == []
        assert response.json()["search_ready"] is False
        assert response.json()["materialization_pending"] is True

    def test_status_route_explains_tombstone_without_requesting_recreation(
        self, auth_headers, db_session
    ):
        """Polling honors owner deletion intent instead of advertising a retry."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session,
            mission_id="STATUS-TOMBSTONE-001",
            status="completed",
            project_id=project.id,
        )
        mission.result_markdown = "# Intentionally removed result"
        mission.execution_metadata = {
            "result_materialization": {
                "status": "failed",
                "attempt_count": 2,
                "attempted_at": "2026-01-01T00:00:00+00:00",
                "error_categories": [],
            }
        }
        document = Document(
            project_id=project.id,
            name=f"{mission.mission_id}_report.md",
            content=mission.result_markdown,
            source_type="deepsearch",
            source_mission_id=mission.id,
            processed=True,
            chunked=True,
            embedded=True,
        )
        document.soft_delete(deleted_by="owner@example.com")
        db_session.add(document)
        db_session.flush()
        mission.result_document_ids = [str(document.id)]
        db_session.commit()

        response = client.get(
            f"/api/v1/missions/{mission.id}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["materialization_pending"] is False
        assert body["materialization_status"] == "blocked_soft_deleted"
        assert body["materialization_attempt_count"] == 2
        assert body["materialization_error"] is None
        assert body["search_ready"] is False
        assert "owner@example.com" not in response.text

    def test_status_route_preserves_genuine_failure_when_document_is_tombstoned(
        self, auth_headers, db_session
    ):
        """Deletion disposition cannot erase a genuine report repair failure."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session,
            mission_id="STATUS-TOMBSTONE-FAILED-001",
            status="completed",
            project_id=project.id,
        )
        mission.result_markdown = "# Intentionally removed document"
        mission.result_protocol = {"synthesis": "Report still needs repair"}
        mission.execution_metadata = {
            "result_materialization": {
                "status": "failed",
                "attempt_count": 3,
                "attempted_at": "2026-01-01T00:00:00+00:00",
                "error_categories": ["unexpected_report_error"],
            }
        }
        document = Document(
            project_id=project.id,
            name=f"{mission.mission_id}_report.md",
            content=mission.result_markdown,
            source_type="deepsearch",
            source_mission_id=mission.id,
            processed=True,
            chunked=True,
            embedded=True,
        )
        document.soft_delete(deleted_by="owner@example.com")
        db_session.add(document)
        db_session.flush()
        mission.result_document_ids = [str(document.id)]
        db_session.commit()

        response = client.get(
            f"/api/v1/missions/{mission.id}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["materialization_status"] == "failed"
        assert body["materialization_error"] == "unexpected_report_error"
        assert body["materialization_pending"] is True
        assert body["materialization_attempt_count"] == 3
        assert body["search_ready"] is False
        assert "owner@example.com" not in response.text

    def test_status_route_exposes_bounded_error_category_only(
        self, auth_headers, db_session
    ):
        """Operators get an actionable code without private exception text."""
        client = TestClient(app)
        private_identifier = uuid.uuid4()
        private_error = f"Qdrant host failed for document {private_identifier}"
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session,
            mission_id="STATUS-CATEGORY-001",
            status="completed",
            project_id=project.id,
        )
        mission.execution_metadata = {
            "result_materialization": {
                "status": "failed",
                "attempt_count": 1,
                "attempted_at": "2026-01-01T00:00:00+00:00",
                "error_categories": [private_error],
            },
            "private_error": private_error,
        }
        db_session.commit()

        response = client.get(
            f"/api/v1/missions/{mission.id}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["materialization_error"] == (
            "unexpected_materialization_error"
        )
        assert "Qdrant host" not in response.text
        assert str(private_identifier) not in response.text

    def test_status_route_protocol_only_result_needs_no_document(
        self, auth_headers, db_session
    ):
        """A materialized structured-only result is complete without markdown."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session,
            mission_id="STATUS-PROTOCOL-001",
            status="completed",
            project_id=project.id,
        )
        report = Report(
            project_id=project.id,
            title="Structured result",
            report_type="markdown",
            content="Structured protocol rendering",
        )
        db_session.add(report)
        db_session.flush()
        mission.result_protocol = {"synthesis": "Structured only"}
        mission.result_report_id = report.id
        db_session.commit()

        response = client.get(
            f"/api/v1/missions/{mission.id}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["search_ready"] is False
        assert response.json()["materialization_pending"] is False


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
        response = client.patch(
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

        mission = _create_test_mission(
            db_session, mission_id="TRANS-001", status="draft"
        )
        assert mission.queued_at is None

        response = client.patch(
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

        mission = _create_test_mission(
            db_session, mission_id="TRANS-002", status="queued"
        )

        response = client.patch(
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

        mission = _create_test_mission(
            db_session, mission_id="TRANS-003", status="in_progress"
        )

        response = client.patch(
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
        project = _create_test_project(db_session)
        valid_statuses = [
            "draft",
            "queued",
            "in_progress",
            "completed",
            "blocked",
            "cancelled",
        ]

        for i, status in enumerate(valid_statuses):
            response = client.post(
                "/api/v1/missions",
                json={
                    "mission_id": f"STAT-{i:03d}",
                    "title": f"Status {status}",
                    "objective": "Test status transitions for validation",
                    "success_criteria": ["Test criterion"],
                    "status": status,
                    "project_id": str(project.id),
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
            db_session,
            mission_id="SUBMIT-HUMAN-001",
            status="draft",
            project_id=project.id,
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
            db_session,
            mission_id="SUBMIT-003",
            status="in_progress",
            project_id=project.id,
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "already in_progress" in detail["message"]

    def test_submit_completed_mission_requires_new_mission(
        self, auth_headers, db_session
    ):
        """A mission is one fenced run; terminal provenance is immutable."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session,
            mission_id="SUBMIT-004",
            status="completed",
            project_id=project.id,
        )

        response = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "cannot be resubmitted" in detail["message"]
        assert "new mission ID" in detail["suggestion"]

    def test_submit_rejects_draft_with_stale_lease_state(
        self, auth_headers, db_session
    ):
        """Changing status back to draft cannot bypass lease fencing."""
        client = TestClient(app)
        project = _create_test_project(db_session)
        mission = _create_test_mission(
            db_session,
            mission_id="SUBMIT-STALE-001",
            status="draft",
            project_id=project.id,
        )
        mission.deepsearch_attempt_count = 2
        mission.deepsearch_result_key = uuid.uuid4().hex
        db_session.commit()

        response = client.post(
            f"/api/v1/missions/{mission.id}/submit",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "prior execution state" in response.json()["detail"]["message"]

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

    def test_create_and_submit_without_project_returns_422(self, auth_headers):
        """T41.6: project_id is required at create — request never reaches the
        submit-side actionable-error branch (which used to live in
        `_submit_existing_mission`). The Pydantic-level rejection happens
        first and gives a structured field error instead of the prior
        prose suggestion."""
        client = TestClient(app)

        response = client.post(
            "/api/v1/missions/create-and-submit",
            json={
                "mission_id": "CREATE-SUBMIT-002",
                "title": "Create and submit without project",
                "objective": "This should fail at the create-time gate.",
                "success_criteria": ["Should fail"],
            },
            headers=auth_headers,
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, list)
        assert any(
            err.get("loc") == ["body", "project_id"]
            and err.get("type") == "missing"
            for err in detail
        ), f"Expected missing-project_id field error, got {detail}"
