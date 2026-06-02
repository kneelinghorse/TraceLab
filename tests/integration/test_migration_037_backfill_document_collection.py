"""Backfill test for migration 037_backfill_document_collection_ownership (S48 T48.4).

Migration 031 backfilled rows that existed at Sprint 43; but until T48.4 the document
and collection CREATE paths kept minting NULL owner_id/workspace_id, so rows created in
the gap (after 031, before T48.4) are still NULL and would go invisible to non-admins
the instant rbac_enabled flips. 037 idempotently mops those up to the bootstrap owner +
the seeded Default Workspace — for the documents + collections tables only.

Against a fresh isolated Postgres DB: bring the schema to 036 (037's down_revision; 023
has seeded the bootstrap admin and 031 has run), seed gap-era NULL rows, run 037, and
assert the fill + the 0-NULL guard. Also pins non-clobber (already-attributed rows are
left alone) and the no-users early-return branch. Shared fixtures: tests/integration/conftest.py.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from alembic import command

pytestmark = pytest.mark.integration

# 037's down_revision — the head before this migration.
REV_036 = "036_drop_metadata_table"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
# The bootstrap admin migration 023 seeds (AUTH_USERNAME=tracelab-admin default).
BOOTSTRAP_EMAIL = "tracelab-admin@tracelab.local"


class TestBackfillDocumentCollectionOwnership:
    def test_037_backfills_gap_era_nulls_and_enforces_zero_null_guard(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_036)
            with engine.connect() as conn:
                admin_id = conn.execute(
                    text("SELECT id FROM users WHERE email = :e"), {"e": BOOTSTRAP_EMAIL}
                ).scalar()
            assert admin_id is not None, "migration 023 should have seeded the bootstrap admin"

            # Gap-era rows: minted NULL-owner AFTER 031 ran (a document needs a parent
            # project for its FK; the project itself is irrelevant to 037's two tables).
            pid, coll_id, doc_id = uuid4(), uuid4(), uuid4()
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO projects (id, name) VALUES (:id, :n)"),
                    {"id": pid, "n": "gap project"},
                )
                conn.execute(
                    text("INSERT INTO collections (id, name, created_at) VALUES (:id, :n, now())"),
                    {"id": coll_id, "n": "gap collection"},
                )
                conn.execute(
                    text("INSERT INTO documents (id, project_id, name) VALUES (:id, :pid, :n)"),
                    {"id": doc_id, "pid": pid, "n": "gap doc"},
                )
                # Sanity: these are NULL-owner right now (the bug 037 closes).
                for table in ("collections", "documents"):
                    nulls = conn.execute(
                        text(f"SELECT count(*) FROM {table} WHERE owner_id IS NULL")  # noqa: S608
                    ).scalar()
                    assert nulls >= 1, f"{table} seed should start NULL-owner"

            # Run 037 (the only migration between 036 and head).
            command.upgrade(alembic_cfg, "head")

            with engine.connect() as conn:
                for table in ("documents", "collections"):
                    rows = conn.execute(
                        text(f"SELECT owner_id, workspace_id FROM {table}")  # noqa: S608
                    ).all()
                    assert rows, f"{table} should have a seeded row"
                    assert all(str(r.owner_id) == str(admin_id) for r in rows), (
                        f"{table} owner_id not backfilled to the bootstrap owner"
                    )
                    assert all(
                        str(r.workspace_id) == DEFAULT_WORKSPACE_ID for r in rows
                    ), f"{table} workspace_id not backfilled to the Default Workspace"
                    nulls = conn.execute(
                        text(
                            f"SELECT count(*) FROM {table} "  # noqa: S608
                            "WHERE owner_id IS NULL OR workspace_id IS NULL"
                        )
                    ).scalar()
                    assert nulls == 0, f"{table}: 0-NULL guard — no NULL ownership may remain"
        finally:
            engine.dispose()

    def test_037_is_idempotent_and_does_not_clobber_existing_ownership(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_036)
            with engine.connect() as conn:
                admin_id = conn.execute(
                    text("SELECT id FROM users WHERE email = :e"), {"e": BOOTSTRAP_EMAIL}
                ).scalar()

            other_id, owned_coll, null_coll = uuid4(), uuid4(), uuid4()
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, password_hash, "
                        "role, is_active, created_at, updated_at) "
                        "VALUES (:id, :e, :d, :p, 'member', true, now(), now())"
                    ),
                    {"id": other_id, "e": "other@example.com", "d": "Other", "p": "x"},
                )
                # A collection ALREADY attributed to the second user — 037 must leave it.
                conn.execute(
                    text(
                        "INSERT INTO collections (id, name, created_at, owner_id, workspace_id) "
                        "VALUES (:id, :n, now(), :o, :w)"
                    ),
                    {"id": owned_coll, "n": "owned", "o": other_id, "w": DEFAULT_WORKSPACE_ID},
                )
                # And a NULL-owner straggler — 037 must fill it with the bootstrap owner.
                conn.execute(
                    text("INSERT INTO collections (id, name, created_at) VALUES (:id, :n, now())"),
                    {"id": null_coll, "n": "orphan"},
                )

            command.upgrade(alembic_cfg, "head")

            with engine.connect() as conn:
                kept = conn.execute(
                    text("SELECT owner_id FROM collections WHERE id = :id"), {"id": owned_coll}
                ).scalar()
                filled = conn.execute(
                    text("SELECT owner_id FROM collections WHERE id = :id"), {"id": null_coll}
                ).scalar()
            assert str(kept) == str(other_id), "037 must NOT clobber an already-attributed owner"
            assert str(filled) == str(admin_id), "037 must fill the NULL straggler with bootstrap owner"
        finally:
            engine.dispose()

    def test_037_noop_on_empty_users(self, alembic_cfg, migration_db_url):
        # No-users edge (seed skipped / users purged): 037 resolves no owner and must
        # EARLY-RETURN before the backfill + 0-NULL guard, leaving NULL rows in place
        # rather than raising. Without the early return, the guard would fire spuriously.
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_036)
            pid, coll_id, doc_id = uuid4(), uuid4(), uuid4()
            with engine.begin() as conn:
                # CASCADE clears FK dependents (e.g. the seeded invite_code).
                conn.execute(text("TRUNCATE TABLE users CASCADE"))
                conn.execute(
                    text("INSERT INTO projects (id, name) VALUES (:id, :n)"),
                    {"id": pid, "n": "p"},
                )
                conn.execute(
                    text("INSERT INTO collections (id, name, created_at) VALUES (:id, :n, now())"),
                    {"id": coll_id, "n": "c"},
                )
                conn.execute(
                    text("INSERT INTO documents (id, project_id, name) VALUES (:id, :pid, :n)"),
                    {"id": doc_id, "pid": pid, "n": "d"},
                )

            # Must NOT raise (early return skips the 0-NULL guard when there is no owner).
            command.upgrade(alembic_cfg, "head")

            with engine.connect() as conn:
                # No owner was invented; the NULL rows are left untouched (schema-safe).
                for table in ("documents", "collections"):
                    non_null = conn.execute(
                        text(f"SELECT count(*) FROM {table} WHERE owner_id IS NOT NULL")  # noqa: S608
                    ).scalar()
                    assert non_null == 0, f"{table}: no owner should be invented with no users"
        finally:
            engine.dispose()
