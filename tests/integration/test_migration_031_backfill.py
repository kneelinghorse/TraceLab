"""Backfill test for migration 031_backfill_ownership (Sprint 43 T43.3).

Against a fresh isolated Postgres DB: build the schema to 030 (migration 023 has
already seeded the bootstrap admin), insert sample rows with NULL ownership, run
031, and assert the rows are backfilled (owner_id = the seeded bootstrap admin,
workspace_id = the seed workspace), that admin is promoted to 'owner', and 0 NULL
ownership remains; then downgrade and assert the backfill + promotion are reversed.
Also covers the empty-users edge (031 skips cleanly). Shared fixtures: conftest.py.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from alembic import command

pytestmark = pytest.mark.integration

REV_030 = "030_add_owner_workspace_columns"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
# The bootstrap admin migration 023 seeds (AUTH_USERNAME=tracelab-admin default).
BOOTSTRAP_EMAIL = "tracelab-admin@tracelab.local"


class TestBackfillOwnership:
    def test_backfill_promotes_owner_and_fills_rows(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            # Schema up to 030. Migration 023 already seeded the bootstrap admin.
            command.upgrade(alembic_cfg, REV_030)

            with engine.connect() as conn:
                admin_id = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": BOOTSTRAP_EMAIL}).scalar()
            assert admin_id is not None, "migration 023 should have seeded the bootstrap admin"

            # Legacy NULL-ownership rows across heterogeneous tables incl. the
            # FK-dependent documents. projects/collections/documents exercise the
            # backfill loop directly; reports/missions are column-validated by the
            # migration's UPDATEs running (they error on a missing column/table) but
            # carry NOT NULL/CHECK constraints that make a raw seed impractical here.
            project_ids = [uuid4(), uuid4()]
            coll_id, doc_id = uuid4(), uuid4()
            backfilled_tables = ("projects", "collections", "documents")
            with engine.begin() as conn:
                for pid in project_ids:
                    conn.execute(
                        text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
                        {"id": pid, "name": "legacy project"},
                    )
                conn.execute(
                    text("INSERT INTO collections (id, name, created_at) VALUES (:id, :name, now())"),
                    {"id": coll_id, "name": "legacy collection"},
                )
                conn.execute(
                    text("INSERT INTO documents (id, project_id, name) VALUES (:id, :pid, :name)"),
                    {"id": doc_id, "pid": project_ids[0], "name": "legacy doc"},
                )

            # Run the 031 backfill.
            command.upgrade(alembic_cfg, "head")

            with engine.connect() as conn:
                role = conn.execute(text("SELECT role FROM users WHERE id = :id"), {"id": admin_id}).scalar()
                assert role == "owner", "bootstrap user must be promoted to owner"

                for table in backfilled_tables:
                    rows = conn.execute(text(f"SELECT owner_id, workspace_id FROM {table}")).all()  # noqa: S608
                    assert rows, f"{table} should have a seeded row"
                    assert all(str(r.owner_id) == str(admin_id) for r in rows), f"{table} owner_id not backfilled"
                    assert all(str(r.workspace_id) == DEFAULT_WORKSPACE_ID for r in rows), (
                        f"{table} workspace_id not backfilled"
                    )
                    nulls = conn.execute(
                        text(f"SELECT count(*) FROM {table} WHERE owner_id IS NULL OR workspace_id IS NULL")  # noqa: S608
                    ).scalar()
                    assert nulls == 0, f"{table}: no NULL ownership may remain after backfill"

            # Downgrade reverses the backfill + promotion (back to post-030 state).
            command.downgrade(alembic_cfg, REV_030)
            with engine.connect() as conn:
                role = conn.execute(text("SELECT role FROM users WHERE id = :id"), {"id": admin_id}).scalar()
                assert role == "admin", "downgrade must demote the bootstrapped owner"
                for table in backfilled_tables:
                    remaining = conn.execute(
                        text(f"SELECT count(*) FROM {table} WHERE owner_id IS NOT NULL OR workspace_id IS NOT NULL")  # noqa: S608
                    ).scalar()
                    assert remaining == 0, f"downgrade must null out {table} ownership"
        finally:
            engine.dispose()

    def test_backfill_noop_on_empty_users(self, alembic_cfg, migration_db_url):
        # Simulate the no-users edge (e.g. seed skipped): 031 resolves no owner and
        # must skip cleanly without raising and without inventing an owner.
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_030)
            with engine.begin() as conn:
                # CASCADE also clears FK dependents (e.g. the seeded invite_code).
                conn.execute(text("TRUNCATE TABLE users CASCADE"))
            command.upgrade(alembic_cfg, "head")
            with engine.connect() as conn:
                owners = conn.execute(text("SELECT count(*) FROM users WHERE role = 'owner'")).scalar()
            assert owners == 0
        finally:
            engine.dispose()
