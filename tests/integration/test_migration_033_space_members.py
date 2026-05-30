"""Up/down test for migration 033_add_space_members (Sprint 44 T44.1).

Against a fresh isolated Postgres DB: run the chain to head and assert a
space_members table exists with NOT NULL workspace_id/user_id FKs that CASCADE on
parent deletion, a UNIQUE(workspace_id, user_id) grant constraint, and the
user_id reverse-lookup index. Then downgrade and assert the table is gone, and
re-upgrade to prove the chain is repeatable. Shared fixtures: conftest.py.

CASCADE (not SET NULL) is a hard contract here: a space_members row is the grant
itself, so when the user or workspace is deleted the grant must vanish, not
linger as an orphan pointing at a dead parent.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command

pytestmark = pytest.mark.integration

REV_032 = "032_add_user_is_active"


class TestSpaceMembersMigration:
    def test_upgrade_then_downgrade_then_reupgrade(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            # --- upgrade the full chain to head (033) ---
            command.upgrade(alembic_cfg, "head")

            insp = inspect(engine)
            assert "space_members" in set(insp.get_table_names())

            # columns present with the right nullability
            by_name = {c["name"]: c for c in insp.get_columns("space_members")}
            assert {"id", "workspace_id", "user_id", "role", "created_at"} <= set(by_name)
            assert by_name["workspace_id"]["nullable"] is False
            assert by_name["user_id"]["nullable"] is False
            assert by_name["role"]["nullable"] is False

            # FKs must CASCADE: deleting a user/workspace removes the grant, never
            # leaves an orphan grant row pointing at a dead parent.
            fk_targets = {
                (
                    tuple(fk["constrained_columns"]),
                    fk["referred_table"],
                    (fk.get("options") or {}).get("ondelete"),
                )
                for fk in insp.get_foreign_keys("space_members")
            }
            assert (("workspace_id",), "workspaces", "CASCADE") in fk_targets
            assert (("user_id",), "users", "CASCADE") in fk_targets

            # UNIQUE(workspace_id, user_id): one membership row per (Space, user).
            uniques = {
                tuple(uc["column_names"])
                for uc in insp.get_unique_constraints("space_members")
            }
            assert ("workspace_id", "user_id") in uniques

            # reverse-lookup index on user_id ("which Spaces is this user in").
            idx_names = {ix["name"] for ix in insp.get_indexes("space_members")}
            assert "ix_space_members_user_id" in idx_names

            # --- downgrade to 032 must drop the table cleanly ---
            command.downgrade(alembic_cfg, REV_032)
            assert "space_members" not in set(inspect(engine).get_table_names()), (
                "downgrade must drop the space_members table"
            )

            # --- re-upgrade proves the chain is repeatable ---
            command.upgrade(alembic_cfg, "head")
            assert "space_members" in set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
