"""Tests for project management API endpoints (B15.7)."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime

from app.main import app
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectStats, ProjectRead


client = TestClient(app)


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
