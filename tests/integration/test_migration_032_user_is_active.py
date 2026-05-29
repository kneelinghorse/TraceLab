"""Up/down test for migration 032_add_user_is_active (Sprint 43 T43.5).

Against a fresh isolated Postgres DB: run the chain to head and assert users gains
a NOT NULL is_active column with every existing row defaulted to active (server
default), then downgrade and assert the column is gone. Shared fixtures: conftest.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic import command

pytestmark = pytest.mark.integration

REV_031 = "031_backfill_ownership"


class TestUserIsActiveMigration:
    def test_upgrade_adds_active_then_downgrade_removes(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, "head")
            cols = {c["name"]: c for c in inspect(engine).get_columns("users")}
            assert "is_active" in cols, "migration 032 must add users.is_active"
            assert cols["is_active"]["nullable"] is False

            # The seed admin (migration 023) must be backfilled to active via the
            # server_default — no NOT NULL violation, no NULL/false rows.
            with engine.connect() as conn:
                inactive = conn.execute(text("SELECT count(*) FROM users WHERE is_active = false")).scalar()
            assert inactive == 0

            command.downgrade(alembic_cfg, REV_031)
            cols_after = {c["name"] for c in inspect(engine).get_columns("users")}
            assert "is_active" not in cols_after, "downgrade must drop users.is_active"
        finally:
            engine.dispose()
