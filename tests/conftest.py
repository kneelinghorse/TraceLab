"""Shared pytest fixtures for ingestion pipeline tests."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./tests/test_ingestion.db")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AUTH_USERNAME", "tracelab-admin")
os.environ.setdefault("AUTH_PASSWORD", "changeme")

from app.core.database import Base, engine, SessionLocal
from app.core.security import get_configured_credentials, issue_token_response
from app.models.project import Project

pytest_plugins: tuple[str, ...] = ()

_TELEMETRY_PLUGIN_NAME = "cmos_pytest_telemetry_plugin"
_TELEMETRY_PLUGIN_PATH = REPO_ROOT / "cmos" / "scripts" / "pytest_telemetry_plugin.py"

if _TELEMETRY_PLUGIN_PATH.exists():
    _spec = importlib.util.spec_from_file_location(_TELEMETRY_PLUGIN_NAME, _TELEMETRY_PLUGIN_PATH)
    if _spec and _spec.loader:
        _module = importlib.util.module_from_spec(_spec)
        sys.modules[_TELEMETRY_PLUGIN_NAME] = _module
        _spec.loader.exec_module(_module)
        pytest_plugins = (*pytest_plugins, _TELEMETRY_PLUGIN_NAME)

_COVERAGE_PATH = Path("cmos/reports/sprint-01/ingestion_format_coverage.json")


@pytest.fixture(autouse=True)
def reset_database_and_reports(request):
    """Reset the SQLite database and coverage artifact before each test.

    This fixture is skipped for tests in tests/mcp/ since those don't need DB.
    """
    # Skip for MCP tests that don't need database
    if 'mcp' in str(request.fspath):
        yield
        return

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    original_bytes = None
    if _COVERAGE_PATH.exists():
        original_bytes = _COVERAGE_PATH.read_bytes()
        _COVERAGE_PATH.unlink()
    yield
    if original_bytes is not None:
        _COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _COVERAGE_PATH.write_bytes(original_bytes)
    elif _COVERAGE_PATH.exists():
        _COVERAGE_PATH.unlink()


@pytest.fixture
def db_session():
    """Provide a transactional database session for tests."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def project(db_session):
    """Create a project record for ingestion scenarios."""
    instance = Project(name="TraceLab Test Project", description="Pipeline validation")
    db_session.add(instance)
    db_session.commit()
    db_session.refresh(instance)
    return instance


@pytest.fixture(scope="session")
def auth_headers():
    """Provide Authorization header for API tests."""
    credentials = get_configured_credentials()
    token = issue_token_response(credentials)["access_token"]
    return {"Authorization": f"Bearer {token}"}
