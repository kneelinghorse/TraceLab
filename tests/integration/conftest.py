# ABOUTME: Integration test fixtures using testcontainers for real PostgreSQL.
# ABOUTME: Replaces the SQLite hack for tests that need actual database behavior.

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

# Prevent root conftest from interfering with our PG session
os.environ["SKIP_DB_INIT"] = "1"
os.environ["ENVIRONMENT"] = "test"

from app.core.database import Base  # noqa: E402

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
