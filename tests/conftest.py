"""Shared pytest fixtures for ingestion pipeline tests."""
from __future__ import annotations

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

_COVERAGE_PATH = Path("cmos/reports/sprint-01/ingestion_format_coverage.json")


@pytest.fixture(autouse=True)
def reset_database_and_reports():
    """Reset the SQLite database and coverage artifact before each test."""
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
