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

# CRITICAL: Force test database to prevent accidental production wipes
# setdefault doesn't override .env values, so we MUST force this
_TEST_DB_URL = "sqlite:///./tests/test_ingestion.db"
_current_db = os.environ.get("DATABASE_URL", "")

# Safety check: refuse to run tests against production databases
if "postgresql" in _current_db.lower() or "rlwy.net" in _current_db.lower():
    raise RuntimeError(
        f"REFUSING TO RUN TESTS: DATABASE_URL points to PostgreSQL ({_current_db[:50]}...).\n"
        "Tests would wipe the database! Unset DATABASE_URL or use SQLite for tests."
    )

os.environ["DATABASE_URL"] = _TEST_DB_URL  # Force, don't setdefault
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("AUTH_USERNAME", "tracelab-admin")
os.environ.setdefault("AUTH_PASSWORD", "changeme")

from sqlalchemy import event

from app.core.database import Base, engine, SessionLocal
from app.core.security import get_configured_credentials, issue_token_response
from app.models.project import Project

# Register PostgreSQL-only functions for SQLite test compatibility
def _sqlite_jsonb_array_length(v):
    import json
    return len(json.loads(v)) if v else 0

if "sqlite" in str(engine.url):
    @event.listens_for(engine, "connect")
    def _register_sqlite_functions(dbapi_conn, connection_record):
        dbapi_conn.create_function("jsonb_array_length", 1, _sqlite_jsonb_array_length)

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


def _create_all_sqlite_safe(eng):
    """Create all tables, neutralizing PostgreSQL-only computed columns for SQLite."""
    if "sqlite" not in str(eng.url):
        Base.metadata.create_all(bind=eng)
        return
    # Ensure jsonb_array_length is available on all pooled connections
    eng.dispose()
    # Temporarily neutralize Computed columns (SQLite can't handle Postgres syntax)
    _originals = {}
    for table in Base.metadata.sorted_tables:
        for col in list(table.columns):
            if hasattr(col, "computed") and col.computed is not None:
                _originals[(table.fullname, col.name)] = col.computed
                col.computed = None
    try:
        Base.metadata.create_all(bind=eng)
    finally:
        for (table_name, col_name), computed in _originals.items():
            table = Base.metadata.tables[table_name]
            table.columns[col_name].computed = computed


@pytest.fixture(autouse=True)
def reset_database_and_reports(request):
    """Reset the SQLite database and coverage artifact before each test.

    This fixture is skipped for tests in tests/mcp/ since those don't need DB.
    """
    # Skip for MCP tests and unit tests that don't need database reset
    # Also skip for tests that rely on existing schema (created via Alembic)
    test_path = str(request.fspath)
    skip_patterns = [
        'mcp',
        'tests/unit',
        'test_deepsearch_client',
        'test_auto_ingest',
        'test_auto_report',
        'test_reprocess_embeddings',
        'test_pedr_relational',
        'test_qdrant_prewarm',
        'test_pedr_enhancements',
        'test_pedr_unified_search',
        'test_rag_service',
        'test_pedr_semantic_protocol',
        'test_pedr_manifest_transformer',
        'test_pedr_search_api',
        'test_edge_materialization',
        'test_graph_layer',
        'test_graph_search',
        'test_graph_rag',
        'test_evidence_auto_linking',
    ]
    if any(pattern in test_path for pattern in skip_patterns):
        yield
        return

    Base.metadata.drop_all(bind=engine)
    _create_all_sqlite_safe(engine)
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
