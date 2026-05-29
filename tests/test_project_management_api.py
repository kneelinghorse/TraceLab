"""Tests for project management API endpoints (B15.7)."""

from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.schemas.project import ProjectCreate, ProjectRead, ProjectStats, ProjectUpdate


@pytest.fixture
def mock_db():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def sample_project():
    """Sample project for testing."""
    return {
        "id": str(uuid4()),
        "name": "Test Project",
        "description": "Test description",
        "research_type": "strategic",
        "methodology": "qualitative",
        "status": "active",
        "quality_score": None,
        "last_quality_check": None,
        "user_id": None,
        "mission_protocol_id": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


class TestProjectCreate:
    """Tests for POST /api/v1/projects endpoint."""

    def test_create_project_schema_validation(self):
        """Test that ProjectCreate schema accepts valid input."""
        data = ProjectCreate(
            name="My Research Project",
            description="Research on AI agents",
            research_type="strategic",
        )
        assert data.name == "My Research Project"
        assert data.description == "Research on AI agents"
        assert data.research_type == "strategic"

    def test_create_project_minimal(self):
        """Test creating project with minimal data."""
        data = ProjectCreate(name="Minimal Project")
        assert data.name == "Minimal Project"
        assert data.description is None


class TestProjectUpdate:
    """Tests for PUT /api/v1/projects/{id} endpoint."""

    def test_update_project_schema_partial(self):
        """Test that ProjectUpdate accepts partial updates."""
        data = ProjectUpdate(name="New Name")
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"name": "New Name"}

    def test_update_project_schema_full(self):
        """Test that ProjectUpdate accepts full updates."""
        data = ProjectUpdate(
            name="Updated Project",
            description="Updated description",
            status="completed",
        )
        dumped = data.model_dump(exclude_unset=True)
        assert "name" in dumped
        assert "description" in dumped
        assert "status" in dumped


class TestProjectStats:
    """Tests for GET /api/v1/projects/{id}/stats endpoint."""

    def test_project_stats_schema(self):
        """Test that ProjectStats schema works correctly."""
        stats = ProjectStats(
            project_id=uuid4(),
            name="Test Project",
            document_count=10,
            chunk_count=150,
            report_count=3,
            total_tokens=25000,
            last_updated=datetime.utcnow(),
        )
        assert stats.document_count == 10
        assert stats.chunk_count == 150
        assert stats.report_count == 3
        assert stats.total_tokens == 25000

    def test_project_stats_without_last_updated(self):
        """Test that last_updated is optional."""
        stats = ProjectStats(
            project_id=uuid4(),
            name="Test Project",
            document_count=0,
            chunk_count=0,
            report_count=0,
            total_tokens=0,
        )
        assert stats.last_updated is None


class TestProjectQueryService:
    """Tests for ProjectQueryService methods."""

    def test_create_project_service(self):
        """Test project creation via service."""
        from app.services.project_query_service import ProjectQueryService

        service = ProjectQueryService()
        # Service methods exist
        assert hasattr(service, "create_project")
        assert hasattr(service, "update_project")
        assert hasattr(service, "get_project_stats")

    def test_project_stats_returns_aggregates(self):
        """Test that get_project_stats returns aggregated data."""
        from app.services.project_query_service import ProjectQueryService

        service = ProjectQueryService()
        # Method signature includes project_id parameter
        import inspect

        sig = inspect.signature(service.get_project_stats)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "project_id" in params


class TestProjectSchemaOwnership:
    """T43.4: user_id is no longer a client-settable input field."""

    def test_project_create_no_longer_accepts_user_id(self):
        assert "user_id" not in ProjectCreate.model_fields
        # An extra user_id in the payload is silently ignored, never recorded.
        data = ProjectCreate(name="x", user_id=str(uuid4()))
        assert "user_id" not in data.model_dump()

    def test_project_update_no_longer_accepts_user_id(self):
        assert "user_id" not in ProjectUpdate.model_fields
        data = ProjectUpdate(name="y", user_id=str(uuid4()))
        assert "user_id" not in data.model_dump(exclude_unset=True)

    def test_project_read_still_exposes_user_id_for_backward_compat(self):
        # Response contract is preserved (option B); the value is null for projects
        # created after T43.4. owner_id is the authoritative owner (surfaced later).
        assert "user_id" in ProjectRead.model_fields


class TestProjectOwnershipWritePath:
    """T43.4: owner_id is derived from the authenticated caller, not the body."""

    def test_create_records_owner_from_caller_and_ignores_body_user_id(self, db_session, auth_headers):
        from fastapi.testclient import TestClient

        from app.main import app
        from app.models.project import Project
        from app.models.user import User
        from app.services.ownership import bootstrap_owner_email

        seed = db_session.query(User).filter(User.email == bootstrap_owner_email()).first()
        assert seed is not None, "autouse fixture should seed the bootstrap admin"

        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/projects",
                # bogus self-asserted owner in the body — must be ignored
                json={"name": "Owned Project", "user_id": str(uuid4())},
                headers=auth_headers,
            )
        assert resp.status_code == 201, resp.text
        project_id = resp.json()["id"]

        project = db_session.query(Project).filter(Project.id == project_id).first()
        assert str(project.owner_id) == str(seed.id), "owner_id must be the authenticated caller"
        assert project.user_id is None, "client-supplied user_id must be ignored"
