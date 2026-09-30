"""SQLite recovery DDL matches the PostgreSQL migration, including cascade cleanup."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_recovery_sqlite_upgrade_downgrade(monkeypatch):
    source = Path(__file__).resolve().parents[1] / "alembic/versions/056_password_recovery.py"
    spec = importlib.util.spec_from_file_location("recovery_migration", source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(text("CREATE TABLE users (id CHAR(36) PRIMARY KEY, password_hash VARCHAR(255) NOT NULL)"))
        connection.execute(text("INSERT INTO users VALUES ('fixture','original-hash')"))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        assert tuple(connection.execute(text("SELECT password_hash, credential_version FROM users")).one()) == ("original-hash", 0)
        connection.execute(text("INSERT INTO password_recoveries VALUES ('fixture','digest',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'accepted')"))
        connection.execute(text("DELETE FROM users"))
        assert connection.execute(text("SELECT COUNT(*) FROM password_recoveries")).scalar() == 0
        migration.downgrade()
        assert "password_recoveries" not in inspect(connection).get_table_names()
        assert "credential_version" not in {c["name"] for c in inspect(connection).get_columns("users")}
