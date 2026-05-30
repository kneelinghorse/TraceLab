"""Up/down + idempotency test for migration 035_add_sync_states_table (T45.1).

Two properties matter for this migration, each tied to a concrete failure mode:

1. Round-trip on a fresh alembic-only DB — proves sync_states is reproducible
   from migrations alone (the gap that made it the one uncovered ORM table), with
   the exact column/constraint shape the SyncState model declares. Without this,
   a fresh CI/test/prod DB has no sync_states and PEDR delta sync breaks.

2. Idempotency when the table already exists — proves the has_table guard makes
   the upgrade a no-op (not a DuplicateTable error) on a database where the
   dev-gated create_all already provisioned sync_states. This is the workspaces
   crash-loop class (learning #90); the test would fail loudly if the guard were
   ever dropped.

Shared fixtures: conftest.py (alembic_cfg resets the schema per test).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic import command

pytestmark = pytest.mark.integration

REV_034 = "034_add_project_tags"
REV_035 = "035_add_sync_states_table"

EXPECTED_COLUMNS = {
    "id",
    "entity_type",
    "last_sync_at",
    "sync_count",
    "last_entity_id",
    "sync_metadata",
    "created_at",
    "updated_at",
}


class TestSyncStatesMigration:
    def test_upgrade_then_downgrade_then_reupgrade(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            # --- upgrade the full chain to head (035) ---
            command.upgrade(alembic_cfg, "head")

            insp = inspect(engine)
            assert "sync_states" in set(insp.get_table_names())

            # exact column set — parity with the SyncState model.
            cols = {c["name"] for c in insp.get_columns("sync_states")}
            assert cols == EXPECTED_COLUMNS

            # single-column PK on id.
            pk = insp.get_pk_constraint("sync_states")
            assert pk["constrained_columns"] == ["id"]

            # the one-cursor-per-entity-type unique constraint, by exact name.
            uniques = {
                uc["name"]: tuple(uc["column_names"])
                for uc in insp.get_unique_constraints("sync_states")
            }
            assert uniques.get("uq_sync_state_entity_type") == ("entity_type",)

            # entity_type is a NOT NULL business column (model parity).
            not_null = {
                c["name"] for c in insp.get_columns("sync_states") if not c["nullable"]
            }
            assert "entity_type" in not_null

            # --- downgrade to 034 must drop the table cleanly ---
            command.downgrade(alembic_cfg, REV_034)
            assert "sync_states" not in set(inspect(engine).get_table_names()), (
                "downgrade must drop the sync_states table"
            )

            # --- re-upgrade proves the chain is repeatable ---
            command.upgrade(alembic_cfg, "head")
            assert "sync_states" in set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

    def test_idempotent_when_table_preexists(self, alembic_cfg, migration_db_url):
        """Simulate the dev-gated create_all having already made sync_states.

        Upgrade to 034 (chain just below 035), create sync_states out of band the
        way create_all would (from the model's own metadata), then upgrade to head.
        035 must NOT raise DuplicateTable — it must detect the table and no-op while
        still advancing the alembic version to 035.
        """
        from app.models.sync_state import SyncState

        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_034)

            # Out-of-band create, exactly as Base.metadata.create_all would do it.
            SyncState.__table__.create(bind=engine)
            assert "sync_states" in set(inspect(engine).get_table_names())

            # The guarded upgrade must be a clean no-op, not DuplicateTable.
            command.upgrade(alembic_cfg, "head")

            assert "sync_states" in set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                version = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
            assert version == REV_035, (
                "035 must stamp the version even when it no-ops on a pre-existing table"
            )
        finally:
            engine.dispose()

    def test_pedr_delta_sync_runs_on_alembic_only_db(self, alembic_cfg, migration_db_url):
        """The point of the migration: PEDR delta sync works on an alembic-only DB.

        Before 035, sync_states existed only via create_all, so on a migrations-only
        DB the very first thing DeltaSyncService does — _get_sync_state querying
        sync_states — raised "relation sync_states does not exist". This drives the
        real sync_missions()/sync_documents() DELTA path (which calls _get_sync_state)
        against a DB provisioned by `alembic upgrade head` alone and asserts no error.
        dry_run + no ingest_callback keeps it fully offline (no Qdrant/OpenAI/PEDR).
        """
        from sqlalchemy.orm import sessionmaker

        from app.services.pedr.delta_sync import DeltaSyncService, SyncMode

        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, "head")  # migrations only — no create_all

            session_factory = sessionmaker(bind=engine)
            service = DeltaSyncService(session_factory=session_factory)

            # DELTA mode hits _get_sync_state -> SELECT on sync_states first. If 035
            # didn't create the table this raises and success would be False.
            missions = service.sync_missions(mode=SyncMode.DELTA, dry_run=True)
            documents = service.sync_documents(mode=SyncMode.DELTA, dry_run=True)

            assert missions.success, f"sync_missions errored: {missions.errors}"
            assert documents.success, f"sync_documents errored: {documents.errors}"
        finally:
            engine.dispose()
