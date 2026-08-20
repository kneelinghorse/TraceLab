# ABOUTME: Integration test fixtures using testcontainers for real PostgreSQL.
# ABOUTME: Replaces the SQLite hack for tests that need actual database behavior.

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from alembic.config import Config

# Prevent root conftest from interfering with our PG session
os.environ["SKIP_DB_INIT"] = "1"
os.environ["ENVIRONMENT"] = "test"

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def pg_container():
    """Spin up a PostgreSQL container for the test session."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:15") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_engine(pg_container):
    """Create a SQLAlchemy engine connected to the testcontainer."""
    url = pg_container.get_connection_url()
    engine = create_engine(url, echo=False)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(pg_engine):
    """Provide a transactional database session that rolls back after each test."""
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(auth_headers, db_session):
    """Exercise API routes against the same PostgreSQL transaction as the test."""
    request_session_factory = sessionmaker(
        bind=db_session.get_bind(),
        join_transaction_mode="create_savepoint",
    )

    def _override_get_db():
        request_session = request_session_factory()
        try:
            yield request_session
        finally:
            request_session.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.headers.update(auth_headers)
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def migration_db_url(pg_container):
    """Isolated empty database inside the shared container for alembic chain runs.

    A dedicated DB (not the container default, which other integration tests
    populate via Base.metadata.create_all) guarantees alembic runs from an empty
    schema. render_as_string(hide_password=False): plain str(URL) masks the
    password as '***', which would make alembic/create_engine fail authentication.
    """
    base = make_url(pg_container.get_connection_url()).set(drivername="postgresql+psycopg2")
    test_db = "tl_migration_test"
    admin_engine = create_engine(base, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{test_db}"'))
        yield base.set(database=test_db).render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))
        admin_engine.dispose()


@pytest.fixture
def alembic_cfg(migration_db_url, monkeypatch):
    """Alembic Config pinned at the isolated migration DB.

    env.py overrides sqlalchemy.url from settings.database_url at runtime, so we
    patch that too (not just the Config) or the override would win.
    """
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "database_url", migration_db_url)
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", migration_db_url)
    return cfg
