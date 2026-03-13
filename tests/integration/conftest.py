# ABOUTME: Integration test fixtures using testcontainers for real PostgreSQL.
# ABOUTME: Replaces the SQLite hack for tests that need actual database behavior.

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Prevent root conftest from interfering with our PG session
os.environ["SKIP_DB_INIT"] = "1"
os.environ["ENVIRONMENT"] = "test"

from app.core.database import Base  # noqa: E402


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
