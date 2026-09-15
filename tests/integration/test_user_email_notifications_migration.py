"""NOTIFY-1: the email opt-out column is additive, defaults every user to enabled, and reverses cleanly."""

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command

pytestmark = pytest.mark.integration


def test_email_notifications_column_is_additive_and_reversible(alembic_cfg, migration_db_url):
    engine = create_engine(migration_db_url)
    try:
        command.upgrade(alembic_cfg, "head")
        columns = {column["name"]: column for column in inspect(engine).get_columns("users")}
        opt_in = columns["email_notifications_enabled"]
        # Existing users keep receiving mail until they opt out, so the column must default to true.
        assert opt_in["nullable"] is False
        assert str(opt_in["default"]).lower() == "true"
        command.downgrade(alembic_cfg, "049_recent_activity")
        assert "email_notifications_enabled" not in {column["name"] for column in inspect(engine).get_columns("users")}
        command.upgrade(alembic_cfg, "head")
    finally:
        engine.dispose()
