"""PostgreSQL catalog contract for the DeepSearch ledger batch migration.

The runtime depends on a mission/job uniqueness boundary and a nullable
batch-to-entry ownership link.  A table that merely has the right name is not
good enough: accepting
that drift would make replay look successful while leaving duplicate evidence
possible.  These tests therefore inspect the real PostgreSQL catalog and prove
upgrade, rollback, re-upgrade, and fail-loud handling of a lookalike table.
"""

from __future__ import annotations

import hashlib
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.models.evidence_ledger import DeepSearchEvidenceOutbox

pytestmark = pytest.mark.integration

REV_042 = "042_ledger_retrieval_v1"
REV_043 = "043_deepsearch_evidence"
BATCH_TABLE = "deepsearch_ledger_batches"
BATCH_COLUMNS = {
    "id",
    "mission_id",
    "deepsearch_job_id",
    "session_key",
    "payload_hash",
    "entry_count",
    "created_at",
    "updated_at",
}
BATCH_CHECKS = {
    "ck_deepsearch_ledger_batches_nonempty_job",
    "ck_deepsearch_ledger_batches_nonempty_session",
    "ck_deepsearch_ledger_batches_hash_length",
    "ck_deepsearch_ledger_batches_entry_count",
}
OUTBOX_TABLE = "deepsearch_evidence_outbox"
OUTBOX_COLUMNS = {
    "mission_id",
    "deepsearch_job_id",
    "deepsearch_result_key",
    "mission_attempt_count",
    "terminal_status",
    "schema_version",
    "state",
    "delivery_attempt_count",
    "next_attempt_at",
    "lease_token",
    "lease_expires_at",
    "acked_at",
    "last_http_status",
    "last_error_code",
    "created_at",
    "updated_at",
}
OUTBOX_CHECKS = {
    "ck_deepsearch_evidence_outbox_nonempty_job",
    "ck_deepsearch_evidence_outbox_nonempty_result_key",
    "ck_deepsearch_evidence_outbox_positive_attempt",
    "ck_deepsearch_evidence_outbox_terminal_status",
    "ck_deepsearch_evidence_outbox_schema_version",
    "ck_deepsearch_evidence_outbox_state",
    "ck_deepsearch_evidence_outbox_delivery_attempts",
    "ck_deepsearch_evidence_outbox_http_status",
    "ck_deepsearch_evidence_outbox_state_coherence",
}
MIGRATION_043_PATH = Path(__file__).parents[2] / "alembic" / "versions" / "043_deepsearch_evidence_batches.py"


def _foreign_key(inspector, table: str, constrained_column: str) -> dict:
    matches = [
        foreign_key
        for foreign_key in inspector.get_foreign_keys(table)
        if foreign_key["constrained_columns"] == [constrained_column]
    ]
    assert len(matches) == 1
    return matches[0]


def _seed_human_ledger_entry(conn) -> dict[str, object]:
    ids: dict[str, object] = {
        "project_id": uuid4(),
        "mission_id": uuid4(),
        "source_id": uuid4(),
        "entry_id": uuid4(),
        "deepsearch_job_id": f"pre-043-job-{uuid4().hex}",
    }
    source_url = "https://example.test/pre-043-human-evidence"
    conn.execute(
        text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
        {"id": ids["project_id"], "name": "Pre-043 human evidence"},
    )
    conn.execute(
        text(
            """
            INSERT INTO missions (
                id, project_id, mission_id, title, objective, success_criteria,
                status, completed_at, deepsearch_job_id,
                deepsearch_attempt_count, deepsearch_result_key
            ) VALUES (
                :id, :project_id, :protocol_id, 'Pre-043 terminal mission',
                'Prove migration 043 never invents historical outbox work.',
                '["Migration 043 creates no historical delivery work."]'::jsonb,
                'completed', now(), :deepsearch_job_id, 1,
                'pre-043-result-key'
            )
            """
        ),
        {
            "id": ids["mission_id"],
            "project_id": ids["project_id"],
            "protocol_id": f"PRE-043-{uuid4().hex[:12]}",
            "deepsearch_job_id": ids["deepsearch_job_id"],
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO ledger_sources (
                id, project_id, source_url, source_url_hash, sighting_count,
                first_seen_at, last_seen_at
            ) VALUES (
                :id, :project_id, :source_url, :source_hash, 1, now(), now()
            )
            """
        ),
        {
            "id": ids["source_id"],
            "project_id": ids["project_id"],
            "source_url": source_url,
            "source_hash": hashlib.sha256(source_url.encode()).hexdigest(),
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO ledger_entries (
                id, project_id, session_key, origin, claim, source_url,
                source_id, disposition, tags, created_at, updated_at
            ) VALUES (
                :id, :project_id, 'human-before-043', 'mcp-agent',
                'Human evidence survives batch migration rollback.',
                :source_url, :source_id, 'supporting', '[]'::jsonb,
                now(), now()
            )
            """
        ),
        {
            "id": ids["entry_id"],
            "project_id": ids["project_id"],
            "source_url": source_url,
            "source_id": ids["source_id"],
        },
    )
    return ids


def _assert_outbox_catalog(inspector) -> None:
    assert inspector.has_table(OUTBOX_TABLE)
    columns = {column["name"]: column for column in inspector.get_columns(OUTBOX_TABLE)}
    assert set(columns) == OUTBOX_COLUMNS
    assert isinstance(columns["mission_id"]["type"], UUID)
    assert isinstance(columns["lease_token"]["type"], UUID)
    assert isinstance(columns["deepsearch_job_id"]["type"], String)
    assert columns["deepsearch_job_id"]["type"].length == 100
    assert isinstance(columns["deepsearch_result_key"]["type"], Text)
    assert isinstance(columns["mission_attempt_count"]["type"], Integer)
    assert isinstance(columns["terminal_status"]["type"], String)
    assert columns["terminal_status"]["type"].length == 32
    assert isinstance(columns["schema_version"]["type"], SmallInteger)
    assert isinstance(columns["state"]["type"], String)
    assert columns["state"]["type"].length == 16
    assert isinstance(columns["delivery_attempt_count"]["type"], Integer)
    assert isinstance(columns["last_http_status"]["type"], SmallInteger)
    assert isinstance(columns["last_error_code"]["type"], String)
    assert columns["last_error_code"]["type"].length == 100
    for name in (
        "next_attempt_at",
        "lease_expires_at",
        "acked_at",
        "created_at",
        "updated_at",
    ):
        assert isinstance(columns[name]["type"], DateTime)
        assert columns[name]["type"].timezone is True

    nullable = {name for name, column in columns.items() if column["nullable"]}
    assert nullable == {
        "lease_token",
        "lease_expires_at",
        "acked_at",
        "last_http_status",
        "last_error_code",
    }
    assert "1" in str(columns["schema_version"]["default"])
    assert "pending" in str(columns["state"]["default"])
    assert "0" in str(columns["delivery_attempt_count"]["default"])
    for name in ("next_attempt_at", "created_at", "updated_at"):
        assert "now" in str(columns[name]["default"]).lower()

    primary_key = inspector.get_pk_constraint(OUTBOX_TABLE)
    assert primary_key["name"] == "pk_deepsearch_evidence_outbox"
    assert tuple(primary_key["constrained_columns"]) == (
        "mission_id",
        "deepsearch_job_id",
    )
    assert inspector.get_unique_constraints(OUTBOX_TABLE) == []

    checks = {check["name"]: check["sqltext"] for check in inspector.get_check_constraints(OUTBOX_TABLE)}
    assert set(checks) == OUTBOX_CHECKS
    assert "validation_failed" in checks["ck_deepsearch_evidence_outbox_terminal_status"]
    assert "dead_letter" in checks["ck_deepsearch_evidence_outbox_state"]
    coherence = checks["ck_deepsearch_evidence_outbox_state_coherence"].lower()
    for required_term in (
        "leased",
        "acked",
        "pending",
        "dead_letter",
        "lease_token",
        "lease_expires_at",
        "next_attempt_at",
        "acked_at",
    ):
        assert required_term in coherence
    http_check = checks["ck_deepsearch_evidence_outbox_http_status"]
    assert "100" in http_check
    assert "599" in http_check

    mission_fk = _foreign_key(inspector, OUTBOX_TABLE, "mission_id")
    assert mission_fk["name"] == "fk_deepsearch_evidence_outbox_mission"
    assert mission_fk["referred_table"] == "missions"
    assert mission_fk["referred_columns"] == ["id"]
    assert mission_fk.get("options", {}).get("ondelete") == "CASCADE"

    indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes(OUTBOX_TABLE)
        if not index.get("duplicates_constraint")
    }
    assert indexes == {
        "ix_deepsearch_evidence_outbox_delivery": (
            "state",
            "next_attempt_at",
            "created_at",
        )
    }


def _seed_deepsearch_batch_and_entry(conn, ids: dict[str, object]) -> None:
    ids["batch_id"] = uuid4()
    ids["deepsearch_entry_id"] = uuid4()
    conn.execute(
        text(
            """
            INSERT INTO deepsearch_ledger_batches (
                id, mission_id, deepsearch_job_id, session_key, payload_hash,
                entry_count, created_at, updated_at
            ) VALUES (
                :id, :mission_id, :job_id, :session_key, :payload_hash,
                1, now(), now()
            )
            """
        ),
        {
            "id": ids["batch_id"],
            "mission_id": ids["mission_id"],
            "job_id": ids["deepsearch_job_id"],
            "session_key": f"deepsearch:{ids['deepsearch_job_id']}",
            "payload_hash": "a" * 64,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO ledger_entries (
                id, project_id, mission_id, deepsearch_batch_id, session_key,
                origin, claim, source_url, source_id, disposition, tags,
                created_at, updated_at
            ) VALUES (
                :id, :project_id, :mission_id, :batch_id, :session_key,
                'deepsearch-worker', 'Durable projected claim',
                'https://example.test/pre-043-human-evidence', :source_id,
                'supporting', '[]'::jsonb, now(), now()
            )
            """
        ),
        {
            "id": ids["deepsearch_entry_id"],
            "project_id": ids["project_id"],
            "mission_id": ids["mission_id"],
            "batch_id": ids["batch_id"],
            "session_key": f"deepsearch:{ids['deepsearch_job_id']}",
            "source_id": ids["source_id"],
        },
    )


def _seed_outbox_row(conn, ids: dict[str, object]) -> None:
    conn.execute(
        text(
            """
            INSERT INTO deepsearch_evidence_outbox (
                mission_id, deepsearch_job_id, deepsearch_result_key,
                mission_attempt_count, terminal_status
            ) VALUES (
                :mission_id, :job_id, 'durable-result-key', 1, 'completed'
            )
            """
        ),
        {
            "mission_id": ids["mission_id"],
            "job_id": ids["deepsearch_job_id"],
        },
    )


def _run_sqlite_043(conn, direction: str) -> None:
    spec = importlib.util.spec_from_file_location(
        f"sqlite_043_{direction}_{uuid4().hex}",
        MIGRATION_043_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = Operations(MigrationContext.configure(conn))
    getattr(migration, direction)()


def test_sqlite_043_upgrade_delete_downgrade_reupgrade_path(tmp_path):
    """SQLite gets the same ownership, retention, and reversible empty DDL."""
    engine = create_engine(f"sqlite:///{tmp_path / 'migration-043.sqlite'}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    metadata = MetaData()
    missions = Table(
        "missions",
        metadata,
        Column("id", String(36), primary_key=True),
    )
    ledger_entries = Table(
        "ledger_entries",
        metadata,
        Column("id", String(36), primary_key=True),
        Column(
            "mission_id",
            String(36),
            ForeignKey("missions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        Column("session_key", String(255), nullable=False),
        Column("origin", String(32), nullable=False),
        Column("claim", Text, nullable=False),
        Column("source_url", Text, nullable=False),
        Column("created_at", DateTime, nullable=False),
    )
    metadata.create_all(engine)
    mission_id = str(uuid4())
    entry_id = str(uuid4())
    batch_id = str(uuid4())
    job_id = "sqlite-durable-job"
    provenance = {
        "session_key": f"deepsearch:{job_id}",
        "origin": "deepsearch-worker",
        "claim": "SQLite keeps this projected claim.",
        "source_url": "https://example.test/sqlite-retained-evidence",
    }

    try:
        with engine.begin() as conn:
            conn.execute(missions.insert().values(id=mission_id))
            conn.execute(
                ledger_entries.insert().values(
                    id=entry_id,
                    mission_id=mission_id,
                    created_at=datetime.now(UTC),
                    **provenance,
                )
            )

            _run_sqlite_043(conn, "upgrade")
            inspector = inspect(conn)
            assert inspector.has_table(BATCH_TABLE)
            assert inspector.has_table(OUTBOX_TABLE)
            assert {column["name"] for column in inspector.get_columns(OUTBOX_TABLE)} == OUTBOX_COLUMNS
            assert {check["name"] for check in inspector.get_check_constraints(OUTBOX_TABLE)} == OUTBOX_CHECKS
            outbox_pk = inspector.get_pk_constraint(OUTBOX_TABLE)
            assert outbox_pk["name"] == "pk_deepsearch_evidence_outbox"
            assert tuple(outbox_pk["constrained_columns"]) == (
                "mission_id",
                "deepsearch_job_id",
            )
            assert {
                index["name"]: tuple(index["column_names"])
                for index in inspector.get_indexes(OUTBOX_TABLE)
                if not index.get("duplicates_constraint")
            } == {
                "ix_deepsearch_evidence_outbox_delivery": (
                    "state",
                    "next_attempt_at",
                    "created_at",
                )
            }
            entry_batch_fk = _foreign_key(
                inspector,
                "ledger_entries",
                "deepsearch_batch_id",
            )
            assert entry_batch_fk.get("options", {}).get("ondelete") == "SET NULL"
            outbox_mission_fk = _foreign_key(
                inspector,
                OUTBOX_TABLE,
                "mission_id",
            )
            assert outbox_mission_fk.get("options", {}).get("ondelete") == "CASCADE"

            conn.execute(
                text(
                    """
                    INSERT INTO deepsearch_ledger_batches (
                        id, mission_id, deepsearch_job_id, session_key,
                        payload_hash, entry_count, created_at, updated_at
                    ) VALUES (
                        :id, :mission_id, :job_id, :session_key,
                        :payload_hash, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": batch_id,
                    "mission_id": mission_id,
                    "job_id": job_id,
                    "session_key": provenance["session_key"],
                    "payload_hash": "b" * 64,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO deepsearch_evidence_outbox (
                        mission_id, deepsearch_job_id, deepsearch_result_key,
                        mission_attempt_count, terminal_status
                    ) VALUES (
                        :mission_id, :job_id, 'sqlite-result-key', 1, 'completed'
                    )
                    """
                ),
                {"mission_id": mission_id, "job_id": job_id},
            )
            conn.execute(
                text("UPDATE ledger_entries SET deepsearch_batch_id = :batch_id WHERE id = :entry_id"),
                {"batch_id": batch_id, "entry_id": entry_id},
            )

            conn.execute(missions.delete().where(missions.c.id == mission_id))

            assert conn.execute(text("SELECT count(*) FROM deepsearch_ledger_batches")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM deepsearch_evidence_outbox")).scalar_one() == 0
            retained = (
                conn.execute(
                    text(
                        "SELECT mission_id, deepsearch_batch_id, session_key, origin, "
                        "claim, source_url FROM ledger_entries WHERE id = :entry_id"
                    ),
                    {"entry_id": entry_id},
                )
                .mappings()
                .one()
            )
            assert retained["mission_id"] is None
            assert retained["deepsearch_batch_id"] is None
            assert {key: retained[key] for key in provenance} == provenance

            _run_sqlite_043(conn, "downgrade")
            inspector = inspect(conn)
            assert not inspector.has_table(BATCH_TABLE)
            assert not inspector.has_table(OUTBOX_TABLE)
            assert "deepsearch_batch_id" not in {column["name"] for column in inspector.get_columns("ledger_entries")}

            _run_sqlite_043(conn, "upgrade")
            inspector = inspect(conn)
            assert inspector.has_table(BATCH_TABLE)
            assert inspector.has_table(OUTBOX_TABLE)
            assert "deepsearch_batch_id" in {column["name"] for column in inspector.get_columns("ledger_entries")}
            reupgraded = (
                conn.execute(
                    text(
                        "SELECT mission_id, deepsearch_batch_id, session_key, origin, "
                        "claim, source_url FROM ledger_entries WHERE id = :entry_id"
                    ),
                    {"entry_id": entry_id},
                )
                .mappings()
                .one()
            )
            assert reupgraded["mission_id"] is None
            assert reupgraded["deepsearch_batch_id"] is None
            assert {key: reupgraded[key] for key in provenance} == provenance
            assert conn.execute(text("SELECT count(*) FROM deepsearch_evidence_outbox")).scalar_one() == 0
    finally:
        engine.dispose()


def test_sqlite_043_rejects_preexisting_outbox_before_partial_ddl(tmp_path):
    """A failed preflight is retryable because it mutates none of revision 042."""
    engine = create_engine(f"sqlite:///{tmp_path / 'migration-043-lookalike.sqlite'}")
    metadata = MetaData()
    Table(
        "missions",
        metadata,
        Column("id", String(36), primary_key=True),
    )
    Table(
        "ledger_entries",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("created_at", DateTime, nullable=False),
    )
    metadata.create_all(engine)

    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE deepsearch_evidence_outbox (mission_id VARCHAR(36) NOT NULL)"))

            for _retry in range(2):
                with pytest.raises(RuntimeError, match="deepsearch_evidence_outbox"):
                    _run_sqlite_043(conn, "upgrade")

                inspector = inspect(conn)
                assert inspector.has_table(OUTBOX_TABLE)
                assert not inspector.has_table(BATCH_TABLE)
                assert "deepsearch_batch_id" not in {
                    column["name"] for column in inspector.get_columns("ledger_entries")
                }
    finally:
        engine.dispose()


class TestDeepSearchEvidenceBatchMigration:
    def test_upgrade_downgrade_reupgrade_preserves_human_entries_and_exact_catalog(
        self,
        alembic_cfg,
        migration_db_url,
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_042)
            with engine.begin() as conn:
                ids = _seed_human_ledger_entry(conn)

            command.upgrade(alembic_cfg, REV_043)
            inspector = inspect(engine)
            assert inspector.has_table(BATCH_TABLE)
            _assert_outbox_catalog(inspector)

            batch_columns = {column["name"]: column for column in inspector.get_columns(BATCH_TABLE)}
            assert set(batch_columns) == BATCH_COLUMNS
            assert isinstance(batch_columns["deepsearch_job_id"]["type"], String)
            assert batch_columns["deepsearch_job_id"]["type"].length == 100
            assert isinstance(batch_columns["session_key"]["type"], String)
            assert batch_columns["session_key"]["type"].length == 255
            assert isinstance(batch_columns["payload_hash"]["type"], String)
            assert batch_columns["payload_hash"]["type"].length == 64
            assert isinstance(batch_columns["entry_count"]["type"], Integer)
            assert isinstance(batch_columns["created_at"]["type"], DateTime)
            assert isinstance(batch_columns["updated_at"]["type"], DateTime)
            for name in BATCH_COLUMNS:
                assert batch_columns[name]["nullable"] is False

            checks = {check["name"]: check["sqltext"] for check in inspector.get_check_constraints(BATCH_TABLE)}
            assert set(checks) == BATCH_CHECKS
            assert "1000" in checks["ck_deepsearch_ledger_batches_entry_count"]
            assert "> 0" in checks["ck_deepsearch_ledger_batches_entry_count"]

            uniques = {
                unique["name"]: tuple(unique["column_names"])
                for unique in inspector.get_unique_constraints(BATCH_TABLE)
            }
            assert uniques["uq_deepsearch_ledger_batches_mission_job"] == (
                "mission_id",
                "deepsearch_job_id",
            )

            batch_indexes = {
                index["name"]: tuple(index["column_names"])
                for index in inspector.get_indexes(BATCH_TABLE)
                if not index.get("duplicates_constraint")
            }
            assert batch_indexes["ix_deepsearch_ledger_batches_mission_created"] == ("mission_id", "created_at")

            mission_fk = _foreign_key(inspector, BATCH_TABLE, "mission_id")
            assert mission_fk["referred_table"] == "missions"
            assert mission_fk["referred_columns"] == ["id"]
            assert mission_fk.get("options", {}).get("ondelete") == "CASCADE"

            entry_columns = {column["name"]: column for column in inspector.get_columns("ledger_entries")}
            assert entry_columns["deepsearch_batch_id"]["nullable"] is True
            entry_batch_fk = _foreign_key(
                inspector,
                "ledger_entries",
                "deepsearch_batch_id",
            )
            assert entry_batch_fk["referred_table"] == BATCH_TABLE
            assert entry_batch_fk["referred_columns"] == ["id"]
            assert entry_batch_fk.get("options", {}).get("ondelete") == "SET NULL"
            entry_indexes = {
                index["name"]: tuple(index["column_names"])
                for index in inspector.get_indexes("ledger_entries")
                if not index.get("duplicates_constraint")
            }
            assert entry_indexes["ix_ledger_entries_deepsearch_batch_created"] == ("deepsearch_batch_id", "created_at")

            with engine.connect() as conn:
                assert (
                    conn.execute(text("SELECT count(*) FROM deepsearch_evidence_outbox")).scalar_one() == 0
                ), "043 must not backfill historical terminal missions into new delivery work"
                assert (
                    conn.execute(
                        text("SELECT deepsearch_batch_id FROM ledger_entries WHERE id = :entry_id"),
                        {"entry_id": ids["entry_id"]},
                    ).scalar_one()
                    is None
                )
                assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REV_043

            command.downgrade(alembic_cfg, REV_042)
            inspector = inspect(engine)
            assert not inspector.has_table(BATCH_TABLE)
            assert not inspector.has_table(OUTBOX_TABLE)
            assert "deepsearch_batch_id" not in {column["name"] for column in inspector.get_columns("ledger_entries")}
            with engine.connect() as conn:
                assert (
                    conn.execute(
                        text("SELECT session_key FROM ledger_entries WHERE id = :entry_id"),
                        {"entry_id": ids["entry_id"]},
                    ).scalar_one()
                    == "human-before-043"
                )

            command.upgrade(alembic_cfg, REV_043)
            inspector = inspect(engine)
            assert inspector.has_table(BATCH_TABLE)
            _assert_outbox_catalog(inspector)
            assert inspector.get_columns("ledger_entries")[-1]["name"] == ("deepsearch_batch_id")
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT session_key, deepsearch_batch_id FROM ledger_entries WHERE id = :entry_id"),
                    {"entry_id": ids["entry_id"]},
                ).one()
                assert conn.execute(text("SELECT count(*) FROM deepsearch_evidence_outbox")).scalar_one() == 0
            assert row.session_key == "human-before-043"
            assert row.deepsearch_batch_id is None
        finally:
            engine.dispose()

    @pytest.mark.parametrize("payload_kind", ("batch", "outbox"))
    def test_downgrade_refuses_to_destroy_durable_delivery_or_projection_state(
        self,
        alembic_cfg,
        migration_db_url,
        payload_kind,
    ):
        """A redelivery retry cannot follow a partially destructive rollback."""
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_042)
            with engine.begin() as conn:
                ids = _seed_human_ledger_entry(conn)
            command.upgrade(alembic_cfg, REV_043)
            with engine.begin() as conn:
                if payload_kind == "batch":
                    _seed_deepsearch_batch_and_entry(conn, ids)
                else:
                    _seed_outbox_row(conn, ids)

            for _retry in range(2):
                with pytest.raises(RuntimeError):
                    command.downgrade(alembic_cfg, REV_042)

                inspector = inspect(engine)
                assert inspector.has_table(BATCH_TABLE)
                assert inspector.has_table(OUTBOX_TABLE)
                assert "deepsearch_batch_id" in {column["name"] for column in inspector.get_columns("ledger_entries")}
                with engine.connect() as conn:
                    assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REV_043
                    if payload_kind == "batch":
                        assert (
                            conn.execute(
                                text("SELECT count(*) FROM deepsearch_ledger_batches WHERE id = :batch_id"),
                                {"batch_id": ids["batch_id"]},
                            ).scalar_one()
                            == 1
                        )
                        assert (
                            conn.execute(
                                text("SELECT count(*) FROM ledger_entries WHERE deepsearch_batch_id = :batch_id"),
                                {"batch_id": ids["batch_id"]},
                            ).scalar_one()
                            == 1
                        )
                    else:
                        assert (
                            conn.execute(
                                text(
                                    "SELECT count(*) FROM deepsearch_evidence_outbox "
                                    "WHERE mission_id = :mission_id "
                                    "AND deepsearch_job_id = :job_id"
                                ),
                                {
                                    "mission_id": ids["mission_id"],
                                    "job_id": ids["deepsearch_job_id"],
                                },
                            ).scalar_one()
                            == 1
                        )
        finally:
            engine.dispose()

    def test_precreated_lookalike_batch_table_is_rejected(
        self,
        alembic_cfg,
        migration_db_url,
    ):
        """Same-name shadow DDL cannot be mistaken for the replay boundary."""
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_042)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE deepsearch_ledger_batches (
                            id uuid PRIMARY KEY,
                            mission_id uuid NOT NULL REFERENCES missions(id),
                            deepsearch_job_id varchar(100) NOT NULL
                        )
                        """
                    )
                )

            with pytest.raises(
                RuntimeError,
                match=r"deepsearch_ledger_batches.*incompatible",
            ):
                command.upgrade(alembic_cfg, REV_043)

            with engine.connect() as conn:
                assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REV_042
        finally:
            engine.dispose()

    def test_precreated_exact_looking_outbox_table_is_rejected(
        self,
        alembic_cfg,
        migration_db_url,
    ):
        """Even exact-looking shadow DDL cannot impersonate migration ownership."""
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_042)
            with engine.begin() as conn:
                DeepSearchEvidenceOutbox.__table__.create(bind=conn)

            with pytest.raises(
                RuntimeError,
                match=r"deepsearch_evidence_outbox.*already exists",
            ):
                command.upgrade(alembic_cfg, REV_043)

            with engine.connect() as conn:
                assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REV_042
            assert not inspect(engine).has_table(BATCH_TABLE), "failed 043 DDL must roll back as one transaction"
        finally:
            engine.dispose()
