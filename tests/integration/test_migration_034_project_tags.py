"""Up/down test for migration 034_add_project_tags (Sprint 44 T44.2).

Against a fresh isolated Postgres DB: run the chain to head and assert a
project_tags junction exists with a composite (project_id, tag_id) primary key,
both FKs CASCADE on parent deletion (the link is dropped when the project or tag
is removed, never left dangling), and the tag_id reverse-lookup index. Then
downgrade and assert the table is gone, and re-upgrade to prove repeatability.
Shared fixtures: conftest.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command

pytestmark = pytest.mark.integration

REV_033 = "033_add_space_members"


class TestProjectTagsMigration:
    def test_upgrade_then_downgrade_then_reupgrade(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            # --- upgrade the full chain to head (034) ---
            command.upgrade(alembic_cfg, "head")

            insp = inspect(engine)
            assert "project_tags" in set(insp.get_table_names())

            cols = {c["name"] for c in insp.get_columns("project_tags")}
            assert cols == {"project_id", "tag_id"}

            # composite PK on both columns.
            pk = insp.get_pk_constraint("project_tags")
            assert set(pk["constrained_columns"]) == {"project_id", "tag_id"}

            # both FKs CASCADE: removing a project or tag drops the link row, never
            # leaves a junction row pointing at a dead parent.
            fk_targets = {
                (
                    tuple(fk["constrained_columns"]),
                    fk["referred_table"],
                    (fk.get("options") or {}).get("ondelete"),
                )
                for fk in insp.get_foreign_keys("project_tags")
            }
            assert (("project_id",), "projects", "CASCADE") in fk_targets
            assert (("tag_id",), "tags", "CASCADE") in fk_targets

            # reverse-lookup index on tag_id ("projects carrying this theme").
            idx_names = {ix["name"] for ix in insp.get_indexes("project_tags")}
            assert "ix_project_tags_tag_id" in idx_names

            # --- downgrade to 033 must drop the table cleanly ---
            command.downgrade(alembic_cfg, REV_033)
            assert "project_tags" not in set(inspect(engine).get_table_names()), (
                "downgrade must drop the project_tags table"
            )

            # --- re-upgrade proves the chain is repeatable ---
            command.upgrade(alembic_cfg, "head")
            assert "project_tags" in set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
