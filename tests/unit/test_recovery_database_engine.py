"""SQLite in-memory test requests must see the same schema across threads."""

import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy
from sqlalchemy.pool import StaticPool

from app.core.config import settings

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "environment,url,shared",
    [
        ("test", "sqlite+pysqlite:///:memory:", True),
        ("production", "sqlite:///:memory:", False),
        ("test", "postgresql://unused.invalid/tracelab", False),
    ],
)
def test_sqlite_pool_override_is_limited_to_test_sqlite(monkeypatch, environment, url, shared):
    captured = {}
    isolated_engine = sqlalchemy.create_engine("sqlite:///:memory:")

    def create_engine(actual_url, **kwargs):
        captured.update(url=actual_url, **kwargs)
        return isolated_engine

    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "database_url", url)
    monkeypatch.setattr(sqlalchemy, "create_engine", create_engine)
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "app/core/database.py"))
    assert captured["url"] == url
    assert captured["pool_pre_ping"] is True
    assert captured["echo"] == settings.debug
    if shared:
        assert captured["poolclass"] is StaticPool
        assert captured["connect_args"] == {"check_same_thread": False}
    else:
        assert "poolclass" not in captured
        assert "connect_args" not in captured
    isolated_engine.dispose()


def test_sqlite_test_engine_shares_committed_state_across_request_threads():
    result = subprocess.run(  # noqa: S603 - fixed Python program in a fresh interpreter
        [
            sys.executable,
            "-c",
            """
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from app.core.database import engine
with engine.begin() as connection:
    connection.execute(text('CREATE TABLE recovery_probe (value INTEGER)'))
    connection.execute(text('INSERT INTO recovery_probe VALUES (42)'))
def read_request():
    with engine.connect() as connection:
        return connection.scalar(text('SELECT value FROM recovery_probe'))
with ThreadPoolExecutor(max_workers=1) as executor:
    assert executor.submit(read_request).result() == 42
engine.dispose()
""",
        ],
        env={**os.environ, "DATABASE_URL": "sqlite:///:memory:", "ENVIRONMENT": "test"},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
