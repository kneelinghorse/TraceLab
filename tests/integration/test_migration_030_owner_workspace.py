"""Up/down test for migration 030_add_owner_workspace_columns (Sprint 43 T43.2).

Runs the FULL Alembic chain against a fresh, isolated PostgreSQL database
(prod-shaped — production is Railway Postgres) and asserts that migration 030
creates the workspaces table + seed row, the nullable owner_id/workspace_id FKs
(ON DELETE SET NULL) + composite indexes on all five owned tables; then downgrades
to 029 and asserts every 030 object is gone; then re-upgrades to prove the chain
is repeatable.

Marked @pytest.mark.integration so it runs in CI's test-integration lane against
postgres:15 and locally via testcontainers (needs Docker). SQLite cannot validate
this: the migration adds FK constraints + drops columns/constraints on downgrade,
which SQLite cannot do without batch mode. The migration_db_url + alembic_cfg
fixtures live in tests/integration/conftest.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic import command

REV_PREV = "029_device_authorization_grants"

# table -> timestamp column used as the trailing column of its composite index.
OWNED_TABLES = {
    "projects": "created_at",
    "collections": "created_at",
    "missions": "created_at",
    "reports": "created_at",
    "documents": "uploaded_at",  # documents has no created_at
}

pytestmark = pytest.mark.integration


def _columns(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


class TestOwnerWorkspaceMigration:
    def test_upgrade_then_downgrade_then_reupgrade(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            # --- upgrade the full chain to head (030) ---
            command.upgrade(alembic_cfg, "head")

            insp = inspect(engine)
            assert "workspaces" in set(insp.get_table_names())

            # exactly one seeded workspace row, with the well-known default id + name
            # (T43.3 backfill / owner-bootstrap reference this fixed UUID).
            with engine.connect() as conn:
                rows = conn.execute(text("SELECT id, name FROM workspaces")).all()
            assert len(rows) == 1, "migration 030 must seed exactly one workspace row"
            assert str(rows[0].id) == "00000000-0000-0000-0000-000000000001"
            assert rows[0].name == "Default Workspace"

            # columns + FKs + composite index on every owned table
            for table, ts_col in OWNED_TABLES.items():
                cols = _columns(insp, table)
                assert {"owner_id", "workspace_id"} <= cols, f"{table} missing owner_id/workspace_id after upgrade"
                # both new columns must be nullable (no NOT NULL that could break rows)
                by_name = {c["name"]: c for c in insp.get_columns(table)}
                assert by_name["owner_id"]["nullable"] is True
                assert by_name["workspace_id"]["nullable"] is True

                # include ondelete: SET NULL is a hard constraint — a CASCADE regression
                # would silently delete resources when a user/workspace is removed.
                fk_targets = {
                    (
                        tuple(fk["constrained_columns"]),
                        fk["referred_table"],
                        (fk.get("options") or {}).get("ondelete"),
                    )
                    for fk in insp.get_foreign_keys(table)
                }
                assert (("owner_id",), "users", "SET NULL") in fk_targets, f"{table} owner_id FK"
                assert (("workspace_id",), "workspaces", "SET NULL") in fk_targets, f"{table} workspace_id FK"

                idx_names = {ix["name"] for ix in insp.get_indexes(table)}
                assert f"ix_{table}_workspace_owner_{ts_col}" in idx_names, f"{table} missing composite index"

            # --- downgrade to 029 must remove every 030 object cleanly ---
            command.downgrade(alembic_cfg, REV_PREV)
            insp = inspect(engine)
            assert "workspaces" not in set(insp.get_table_names()), "downgrade must drop the workspaces table"
            for table, ts_col in OWNED_TABLES.items():
                cols = _columns(insp, table)
                assert "owner_id" not in cols and "workspace_id" not in cols, (
                    f"{table} still has owner/workspace columns after downgrade"
                )
                idx_names = {ix["name"] for ix in insp.get_indexes(table)}
                assert f"ix_{table}_workspace_owner_{ts_col}" not in idx_names, (
                    f"{table} composite index survived downgrade"
                )
                fk_cols = {tuple(fk["constrained_columns"]) for fk in insp.get_foreign_keys(table)}
                assert ("owner_id",) not in fk_cols and ("workspace_id",) not in fk_cols, (
                    f"{table} owner/workspace FK survived downgrade"
                )

            # --- re-upgrade proves the chain is repeatable ---
            command.upgrade(alembic_cfg, "head")
            assert "workspaces" in set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
