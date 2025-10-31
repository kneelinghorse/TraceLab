"""Basic health check tests."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./tests/test.db")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from httpx import AsyncClient
from app.main import app
from app.core.database import get_db


@pytest.fixture
def override_db_dependency():
    """Provide a fake database session for health checks."""

    class FakeResult:
        def fetchone(self):
            return (1,)

    class FakeSession:
        def execute(self, _query):
            return FakeResult()

        def close(self):
            pass

    def _get_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test root endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "status" in data


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_db_health_endpoint(override_db_dependency):
    """Test database health endpoint with dependency override."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/health/db")
        assert response.status_code == 200
        data = response.json()
        assert data["database"] == "connected"
