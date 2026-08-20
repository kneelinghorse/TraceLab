"""Real-Postgres contract tests for the DeepSearch lease-v2 runtime boundary.

The production failure this guards is repository/schema drift: the worker can
only claim safely when Alembic reproduces the exact fencing boundary, while a
manually-ahead database must converge without losing an active lease or result
idempotency key.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import DateTime, Integer, Text, create_engine, inspect, text

from alembic import command

pytestmark = pytest.mark.integration

REV_038 = "038_backfill_mission_report"
REV_039 = "039_deepsearch_lease_v1"

LEASE_COLUMNS = {
    "deepsearch_lease_owner",
    "deepsearch_lease_token",
    "deepsearch_leased_at",
    "deepsearch_heartbeat_at",
    "deepsearch_lease_expires_at",
    "deepsearch_attempt_count",
    "deepsearch_result_key",
}


def _seed_project_and_mission(conn, *, status: str = "in_progress") -> tuple[str, str]:
    project_id = str(uuid4())
    mission_id = str(uuid4())
    human_id = f"LEASE-{mission_id[:8]}"
    conn.execute(
        text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
        {"id": project_id, "name": f"Project {project_id[:8]}"},
    )
    conn.execute(
        text(
            """
            INSERT INTO missions (
                id, project_id, mission_id, title, objective,
                success_criteria, status, created_at, updated_at
            ) VALUES (
                :id, :project_id, :mission_id, :title, :objective,
                CAST(:criteria AS jsonb), :status, now(), now()
            )
            """
        ),
        {
            "id": mission_id,
            "project_id": project_id,
            "mission_id": human_id,
            "title": "Lease boundary mission",
            "objective": "Prove the fenced worker lease survives migration",
            "criteria": json.dumps(["The active lease is preserved"]),
            "status": status,
        },
    )
    return project_id, mission_id


class TestDeepSearchLeaseV1Migration:
    def test_clean_upgrade_creates_exact_columns_defaults_and_indexes(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_039)

            inspector = inspect(engine)
            columns = {
                column["name"]: column
                for column in inspector.get_columns("missions")
            }
            assert LEASE_COLUMNS.issubset(columns)

            for name in (
                "deepsearch_lease_owner",
                "deepsearch_lease_token",
                "deepsearch_result_key",
            ):
                assert isinstance(columns[name]["type"], Text)
                assert columns[name]["nullable"] is True

            for name in (
                "deepsearch_leased_at",
                "deepsearch_heartbeat_at",
                "deepsearch_lease_expires_at",
            ):
                assert isinstance(columns[name]["type"], DateTime)
                assert columns[name]["type"].timezone is True
                assert columns[name]["nullable"] is True

            attempts = columns["deepsearch_attempt_count"]
            assert isinstance(attempts["type"], Integer)
            assert attempts["nullable"] is False
            assert attempts["default"] is not None
            assert "0" in str(attempts["default"])

            indexes = {
                index["name"]: index for index in inspector.get_indexes("missions")
            }
            assert indexes["missions_deepsearch_lease_token_active_uq"][
                "column_names"
            ] == ["deepsearch_lease_token"]
            assert indexes["missions_deepsearch_lease_token_active_uq"][
                "unique"
            ] is True
            assert indexes["missions_deepsearch_result_key_uq"]["column_names"] == [
                "deepsearch_result_key"
            ]
            assert indexes["missions_deepsearch_result_key_uq"]["unique"] is True
            assert indexes["missions_deepsearch_claim_scan_idx"]["column_names"] == [
                "status",
                "deepsearch_lease_expires_at",
                "queued_at",
            ]

            with engine.connect() as conn:
                version = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
            assert version == REV_039
        finally:
            engine.dispose()

    def test_manually_ahead_shape_converges_without_overwriting_active_state(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_038)
            active_token = uuid4().hex
            active_result_key = uuid4().hex
            with engine.begin() as conn:
                # Simulate compatible out-of-band production DDL, including the
                # two repairable drifts: VARCHAR instead of TEXT, naive timestamps,
                # and a nullable/default-less attempt count.
                conn.execute(
                    text(
                        """
                        ALTER TABLE missions
                            ADD COLUMN deepsearch_lease_owner varchar(255) NOT NULL DEFAULT 'legacy-worker',
                            ADD COLUMN deepsearch_lease_token varchar(255) NOT NULL DEFAULT 'legacy-token',
                            ADD COLUMN deepsearch_leased_at timestamp NOT NULL DEFAULT '2026-08-14 01:00:00',
                            ADD COLUMN deepsearch_heartbeat_at timestamp NOT NULL DEFAULT '2026-08-14 01:01:00',
                            ADD COLUMN deepsearch_lease_expires_at timestamp NOT NULL DEFAULT '2099-08-14 01:03:00',
                            ADD COLUMN deepsearch_attempt_count integer,
                            ADD COLUMN deepsearch_result_key varchar(255) NOT NULL DEFAULT 'legacy-result'
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        CREATE UNIQUE INDEX missions_deepsearch_lease_token_active_uq
                        ON missions (deepsearch_lease_token)
                        WHERE deepsearch_lease_token IS NOT NULL
                        """
                    )
                )

                _, active_id = _seed_project_and_mission(conn)
                conn.execute(
                    text(
                        """
                        UPDATE missions
                        SET deepsearch_lease_owner = 'worker-a',
                            deepsearch_lease_token = :lease_token,
                            deepsearch_leased_at = '2026-08-14 01:00:00',
                            deepsearch_heartbeat_at = '2026-08-14 01:01:00',
                            deepsearch_lease_expires_at = '2099-08-14 01:03:00',
                            deepsearch_attempt_count = 2,
                            deepsearch_result_key = :result_key
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": active_id,
                        "lease_token": active_token,
                        "result_key": active_result_key,
                    },
                )

            command.upgrade(alembic_cfg, REV_039)

            columns = {
                column["name"]: column
                for column in inspect(engine).get_columns("missions")
            }
            assert isinstance(columns["deepsearch_lease_owner"]["type"], Text)
            assert columns["deepsearch_lease_expires_at"]["type"].timezone is True
            assert columns["deepsearch_attempt_count"]["nullable"] is False
            assert "0" in str(columns["deepsearch_attempt_count"]["default"])
            for name in (
                "deepsearch_lease_owner",
                "deepsearch_lease_token",
                "deepsearch_result_key",
                "deepsearch_leased_at",
                "deepsearch_heartbeat_at",
                "deepsearch_lease_expires_at",
            ):
                assert columns[name]["nullable"] is True

            with engine.connect() as conn:
                active = conn.execute(
                    text(
                        """
                        SELECT deepsearch_lease_owner, deepsearch_lease_token,
                               deepsearch_attempt_count, deepsearch_result_key,
                               deepsearch_lease_expires_at
                        FROM missions WHERE id = :id
                        """
                    ),
                    {"id": active_id},
                ).one()
            assert active.deepsearch_lease_owner == "worker-a"
            assert active.deepsearch_lease_token == active_token
            assert active.deepsearch_attempt_count == 2
            assert active.deepsearch_result_key == active_result_key
            assert active.deepsearch_lease_expires_at.year == 2099

        finally:
            engine.dispose()

    def test_prelease_in_progress_row_becomes_immediately_reclaimable(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_038)
            with engine.begin() as conn:
                _, mission_id = _seed_project_and_mission(conn)

            command.upgrade(alembic_cfg, REV_039)

            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT deepsearch_attempt_count,
                               deepsearch_lease_token,
                               deepsearch_heartbeat_at,
                               deepsearch_lease_expires_at
                        FROM missions WHERE id = :id
                        """
                    ),
                    {"id": mission_id},
                ).one()
            assert row.deepsearch_attempt_count == 0
            assert row.deepsearch_lease_token is None
            assert row.deepsearch_heartbeat_at is not None
            assert row.deepsearch_lease_expires_at is not None
        finally:
            engine.dispose()

    @pytest.mark.parametrize(
        "attempt_column_ddl",
        [
            "ALTER TABLE missions ADD COLUMN deepsearch_attempt_count smallint",
            "ALTER TABLE missions ADD COLUMN deepsearch_attempt_count bigint",
        ],
        ids=["smallint", "bigint"],
    )
    def test_integer_affinity_drift_converges_to_exact_postgres_integer(
        self,
        alembic_cfg,
        migration_db_url,
        attempt_column_ddl,
    ):
        """SQLAlchemy type affinity cannot hide a worker-incompatible width."""
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_038)
            with engine.begin() as conn:
                conn.execute(text(attempt_column_ddl))
                _, mission_id = _seed_project_and_mission(conn, status="queued")
                conn.execute(
                    text(
                        "UPDATE missions SET deepsearch_attempt_count = 2 "
                        "WHERE id = :id"
                    ),
                    {"id": mission_id},
                )

            command.upgrade(alembic_cfg, REV_039)

            with engine.connect() as conn:
                postgres_type = conn.execute(
                    text(
                        """
                        SELECT format_type(attribute.atttypid, attribute.atttypmod)
                        FROM pg_attribute AS attribute
                        JOIN pg_class AS relation
                          ON relation.oid = attribute.attrelid
                        WHERE relation.relname = 'missions'
                          AND attribute.attname = 'deepsearch_attempt_count'
                          AND NOT attribute.attisdropped
                        """
                    )
                ).scalar_one()
                attempts = conn.execute(
                    text(
                        "SELECT deepsearch_attempt_count FROM missions WHERE id = :id"
                    ),
                    {"id": mission_id},
                ).scalar_one()
            assert postgres_type == "integer"
            assert attempts == 2
        finally:
            engine.dispose()

    def test_wrong_claim_index_predicate_is_replaced(
        self, alembic_cfg, migration_db_url
    ):
        """A same-named partial index cannot silently change global claim scope."""
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_038)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        ALTER TABLE missions
                        ADD COLUMN deepsearch_lease_expires_at timestamptz
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        CREATE INDEX missions_deepsearch_claim_scan_idx
                        ON missions (
                            status, deepsearch_lease_expires_at, queued_at
                        )
                        WHERE status = 'queued'
                        """
                    )
                )

            command.upgrade(alembic_cfg, REV_039)

            claim_index = {
                index["name"]: index
                for index in inspect(engine).get_indexes("missions")
            }["missions_deepsearch_claim_scan_idx"]
            predicate = claim_index.get("dialect_options", {}).get(
                "postgresql_where"
            )
            assert predicate is None
        finally:
            engine.dispose()

    def test_legacy_project_scoped_claim_index_is_replaced(
        self, alembic_cfg, migration_db_url
    ):
        """The deployed project-leading index converges to the global scan."""
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_038)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        ALTER TABLE missions
                        ADD COLUMN deepsearch_lease_expires_at timestamptz
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        CREATE INDEX missions_deepsearch_claim_scan_idx
                        ON missions (
                            project_id, status,
                            deepsearch_lease_expires_at, queued_at
                        )
                        """
                    )
                )

            command.upgrade(alembic_cfg, REV_039)

            claim_index = {
                index["name"]: index
                for index in inspect(engine).get_indexes("missions")
            }["missions_deepsearch_claim_scan_idx"]
            assert claim_index["column_names"] == [
                "status",
                "deepsearch_lease_expires_at",
                "queued_at",
            ]
            assert claim_index["unique"] is False
            assert (
                claim_index.get("dialect_options", {}).get("postgresql_where")
                is None
            )
        finally:
            engine.dispose()
