"""Real-PostgreSQL contract tests for the Evidence Ledger migration.

SQLite cannot prove native UUID/JSONB types, constraint enforcement, FK delete
behavior, or Alembic convergence.  This suite exercises revision 040 against the
same PostgreSQL 15 testcontainer used by production-shaped migration tests.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import DateTime, String, Text, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.exc import IntegrityError

from alembic import command

pytestmark = pytest.mark.integration

REV_039 = "039_deepsearch_lease_v1"
REV_040 = "040_evidence_ledger_v1"

ENTRY_COLUMNS = {
    "id",
    "project_id",
    "mission_id",
    "session_key",
    "origin",
    "claim",
    "summary",
    "source_url",
    "snippet",
    "query",
    "disposition",
    "tags",
    "owner_id",
    "workspace_id",
    "created_at",
    "updated_at",
}
NOTE_COLUMNS = {
    "id",
    "project_id",
    "mission_id",
    "session_key",
    "origin",
    "note_key",
    "content",
    "tags",
    "owner_id",
    "workspace_id",
    "created_at",
    "updated_at",
}
ENTRY_CHECKS = {
    "ck_ledger_entries_origin",
    "ck_ledger_entries_disposition",
    "ck_ledger_entries_nonempty_session",
    "ck_ledger_entries_nonempty_claim",
    "ck_ledger_entries_nonempty_source_url",
}
NOTE_CHECKS = {
    "ck_ledger_notes_origin",
    "ck_ledger_notes_nonempty_session",
    "ck_ledger_notes_nonempty_key",
    "ck_ledger_notes_nonempty_content",
}
ENTRY_INDEXES = {
    "ix_ledger_entries_project_created": ("project_id", "created_at"),
    "ix_ledger_entries_project_session_created": (
        "project_id",
        "session_key",
        "created_at",
    ),
    "ix_ledger_entries_project_mission_created": (
        "project_id",
        "mission_id",
        "created_at",
    ),
    "ix_ledger_entries_workspace_owner_created": (
        "workspace_id",
        "owner_id",
        "created_at",
    ),
}
NOTE_INDEXES = {
    "ix_ledger_notes_project_session_updated": (
        "project_id",
        "session_key",
        "updated_at",
    ),
    "ix_ledger_notes_project_mission_updated": (
        "project_id",
        "mission_id",
        "updated_at",
    ),
    "ix_ledger_notes_workspace_owner_updated": (
        "workspace_id",
        "owner_id",
        "updated_at",
    ),
}


def _columns(inspector, table: str) -> dict[str, dict]:
    return {column["name"]: column for column in inspector.get_columns(table)}


def _foreign_keys(inspector, table: str) -> dict[str, dict]:
    return {foreign_key["constrained_columns"][0]: foreign_key for foreign_key in inspector.get_foreign_keys(table)}


def _create_model_ledger_tables(engine) -> None:
    from app.models.evidence_ledger import LedgerEntry, LedgerNote

    LedgerEntry.__table__.create(bind=engine)
    LedgerNote.__table__.create(bind=engine)


def _assert_upgrade_refused_at_039(
    alembic_cfg,
    engine,
    *,
    match: str,
) -> None:
    with pytest.raises(RuntimeError, match=match):
        command.upgrade(alembic_cfg, REV_040)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == REV_039


def _seed_parents(conn) -> dict[str, UUID]:
    ids = {
        "user_id": uuid4(),
        "workspace_id": uuid4(),
        "project_id": uuid4(),
        "mission_id": uuid4(),
    }
    conn.execute(
        text(
            """
            INSERT INTO users (
                id, email, display_name, password_hash, role, created_at, updated_at
            ) VALUES (
                :id, :email, 'Ledger Tester', 'not-a-real-hash', 'member', now(), now()
            )
            """
        ),
        {"id": ids["user_id"], "email": f"ledger-{ids['user_id']}@example.test"},
    )
    conn.execute(
        text("INSERT INTO workspaces (id, name, created_at) VALUES (:id, 'Ledger Workspace', now())"),
        {"id": ids["workspace_id"]},
    )
    conn.execute(
        text(
            """
            INSERT INTO projects (
                id, name, owner_id, workspace_id, created_at, updated_at
            ) VALUES (
                :id, 'Ledger Project', :owner_id, :workspace_id, now(), now()
            )
            """
        ),
        {
            "id": ids["project_id"],
            "owner_id": ids["user_id"],
            "workspace_id": ids["workspace_id"],
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO missions (
                id, project_id, mission_id, title, objective, success_criteria,
                status, owner_id, workspace_id, created_at, updated_at
            ) VALUES (
                :id, :project_id, :human_id, 'Ledger migration mission',
                'Prove every ledger field survives PostgreSQL',
                CAST(:criteria AS jsonb), 'draft', :owner_id, :workspace_id,
                now(), now()
            )
            """
        ),
        {
            "id": ids["mission_id"],
            "project_id": ids["project_id"],
            "human_id": f"LEDGER-{str(ids['mission_id'])[:8]}",
            "criteria": json.dumps(["All fields round-trip"]),
            "owner_id": ids["user_id"],
            "workspace_id": ids["workspace_id"],
        },
    )
    return ids


def _insert_full_entry(conn, ids: dict[str, UUID], *, entry_id: UUID | None = None):
    entry_id = entry_id or uuid4()
    conn.execute(
        text(
            """
            INSERT INTO ledger_entries (
                id, project_id, mission_id, session_key, origin, claim, summary,
                source_url, snippet, query, disposition, tags, owner_id,
                workspace_id, created_at, updated_at
            ) VALUES (
                :id, :project_id, :mission_id, 'migration-session', 'mcp-agent',
                'Passkeys reduce phishing exposure', 'Primary-source summary',
                'https://example.test/passkeys', 'Origin-bound credential',
                'passkey phishing resistance', 'contradicting',
                CAST(:tags AS jsonb), :owner_id, :workspace_id, now(), now()
            )
            """
        ),
        {
            "id": entry_id,
            "project_id": ids["project_id"],
            "mission_id": ids["mission_id"],
            "tags": json.dumps(["authentication", "primary-source"]),
            "owner_id": ids["user_id"],
            "workspace_id": ids["workspace_id"],
        },
    )
    return entry_id


def _insert_full_note(conn, ids: dict[str, UUID], *, note_id: UUID | None = None):
    note_id = note_id or uuid4()
    conn.execute(
        text(
            """
            INSERT INTO ledger_notes (
                id, project_id, mission_id, session_key, origin, note_key,
                content, tags, owner_id, workspace_id, created_at, updated_at
            ) VALUES (
                :id, :project_id, :mission_id, 'migration-session', 'mcp-agent',
                'next-query', 'Investigate recovery evidence',
                CAST(:tags AS jsonb), :owner_id, :workspace_id, now(), now()
            )
            """
        ),
        {
            "id": note_id,
            "project_id": ids["project_id"],
            "mission_id": ids["mission_id"],
            "tags": json.dumps(["todo"]),
            "owner_id": ids["user_id"],
            "workspace_id": ids["workspace_id"],
        },
    )
    return note_id


class TestEvidenceLedgerMigration:
    def test_039_to_040_creates_exact_postgres_contract(self, alembic_cfg, migration_db_url):
        assert len(REV_040) <= 32, "alembic_version.version_num is VARCHAR(32) in prod"
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_039)
            command.upgrade(alembic_cfg, REV_040)
            inspector = inspect(engine)
            assert {"ledger_entries", "ledger_notes"} <= set(inspector.get_table_names())

            entries = _columns(inspector, "ledger_entries")
            notes = _columns(inspector, "ledger_notes")
            assert set(entries) == ENTRY_COLUMNS
            assert set(notes) == NOTE_COLUMNS

            for columns, uuid_names in (
                (
                    entries,
                    ("id", "project_id", "mission_id", "owner_id", "workspace_id"),
                ),
                (
                    notes,
                    ("id", "project_id", "mission_id", "owner_id", "workspace_id"),
                ),
            ):
                for name in uuid_names:
                    assert isinstance(columns[name]["type"], PGUUID)
                assert isinstance(columns["tags"]["type"], JSONB)
                for name in ("created_at", "updated_at"):
                    assert isinstance(columns[name]["type"], DateTime)
                    assert columns[name]["type"].timezone is False

            assert isinstance(entries["session_key"]["type"], String)
            assert entries["session_key"]["type"].length == 255
            assert isinstance(entries["origin"]["type"], String)
            assert entries["origin"]["type"].length == 32
            assert isinstance(entries["disposition"]["type"], String)
            assert entries["disposition"]["type"].length == 32
            for name in ("claim", "summary", "source_url", "snippet", "query"):
                assert isinstance(entries[name]["type"], Text)

            assert isinstance(notes["session_key"]["type"], String)
            assert notes["session_key"]["type"].length == 255
            assert isinstance(notes["origin"]["type"], String)
            assert notes["origin"]["type"].length == 32
            assert isinstance(notes["note_key"]["type"], String)
            assert notes["note_key"]["type"].length == 100
            assert isinstance(notes["content"]["type"], Text)

            required_entry_columns = {
                "id",
                "project_id",
                "session_key",
                "origin",
                "claim",
                "source_url",
                "disposition",
                "tags",
                "created_at",
                "updated_at",
            }
            required_note_columns = {
                "id",
                "project_id",
                "session_key",
                "origin",
                "note_key",
                "content",
                "tags",
                "created_at",
                "updated_at",
            }
            assert {name for name, column in entries.items() if not column["nullable"]} == required_entry_columns
            assert {name for name, column in notes.items() if not column["nullable"]} == required_note_columns

            assert inspector.get_pk_constraint("ledger_entries")["constrained_columns"] == ["id"]
            assert inspector.get_pk_constraint("ledger_notes")["constrained_columns"] == ["id"]

            for table in ("ledger_entries", "ledger_notes"):
                foreign_keys = _foreign_keys(inspector, table)
                expected = {
                    "project_id": ("projects", "CASCADE"),
                    "mission_id": ("missions", "SET NULL"),
                    "owner_id": ("users", "SET NULL"),
                    "workspace_id": ("workspaces", "SET NULL"),
                }
                assert set(foreign_keys) == set(expected)
                for column, (referred_table, ondelete) in expected.items():
                    foreign_key = foreign_keys[column]
                    assert foreign_key["referred_table"] == referred_table
                    assert foreign_key["referred_columns"] == ["id"]
                    assert foreign_key["options"].get("ondelete") == ondelete

            entry_checks = {
                check["name"]: check["sqltext"] for check in inspector.get_check_constraints("ledger_entries")
            }
            note_checks = {check["name"]: check["sqltext"] for check in inspector.get_check_constraints("ledger_notes")}
            assert set(entry_checks) == ENTRY_CHECKS
            assert set(note_checks) == NOTE_CHECKS
            assert "mcp-agent" in entry_checks["ck_ledger_entries_origin"]
            assert "deepsearch-worker" in entry_checks["ck_ledger_entries_origin"]
            for disposition in (
                "supporting",
                "contradicting",
                "rejected",
                "background",
            ):
                assert disposition in entry_checks["ck_ledger_entries_disposition"]
            assert "mcp-agent" in note_checks["ck_ledger_notes_origin"]
            assert "deepsearch-worker" in note_checks["ck_ledger_notes_origin"]

            for table, expected_indexes in (
                ("ledger_entries", ENTRY_INDEXES),
                ("ledger_notes", NOTE_INDEXES),
            ):
                indexes = {index["name"]: tuple(index["column_names"]) for index in inspector.get_indexes(table)}
                for name, columns in expected_indexes.items():
                    assert indexes.get(name) == columns

            note_uniques = {
                unique["name"]: tuple(unique["column_names"])
                for unique in inspector.get_unique_constraints("ledger_notes")
            }
            assert note_uniques["uq_ledger_notes_project_session_key"] == (
                "project_id",
                "session_key",
                "note_key",
            )

            with engine.connect() as conn:
                version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == REV_040
        finally:
            engine.dispose()

    def test_every_field_round_trips_and_database_checks_reject_invalid_values(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_040)
            with engine.begin() as conn:
                ids = _seed_parents(conn)
                entry_id = _insert_full_entry(conn, ids)
                note_id = _insert_full_note(conn, ids)

            with engine.connect() as conn:
                entry = (
                    conn.execute(
                        text("SELECT * FROM ledger_entries WHERE id = :id"),
                        {"id": entry_id},
                    )
                    .mappings()
                    .one()
                )
                note = (
                    conn.execute(
                        text("SELECT * FROM ledger_notes WHERE id = :id"),
                        {"id": note_id},
                    )
                    .mappings()
                    .one()
                )

            assert entry["id"] == entry_id
            assert entry["project_id"] == ids["project_id"]
            assert entry["mission_id"] == ids["mission_id"]
            assert entry["session_key"] == "migration-session"
            assert entry["origin"] == "mcp-agent"
            assert entry["claim"] == "Passkeys reduce phishing exposure"
            assert entry["summary"] == "Primary-source summary"
            assert entry["source_url"] == "https://example.test/passkeys"
            assert entry["snippet"] == "Origin-bound credential"
            assert entry["query"] == "passkey phishing resistance"
            assert entry["disposition"] == "contradicting"
            assert entry["tags"] == ["authentication", "primary-source"]
            assert entry["owner_id"] == ids["user_id"]
            assert entry["workspace_id"] == ids["workspace_id"]
            assert entry["created_at"] is not None and entry["updated_at"] is not None

            assert note["id"] == note_id
            assert note["project_id"] == ids["project_id"]
            assert note["mission_id"] == ids["mission_id"]
            assert note["session_key"] == "migration-session"
            assert note["origin"] == "mcp-agent"
            assert note["note_key"] == "next-query"
            assert note["content"] == "Investigate recovery evidence"
            assert note["tags"] == ["todo"]
            assert note["owner_id"] == ids["user_id"]
            assert note["workspace_id"] == ids["workspace_id"]
            assert note["created_at"] is not None and note["updated_at"] is not None

            invalid_values = [
                ("third-party", "supporting"),
                ("mcp-agent", "unreviewed"),
            ]
            for origin, disposition in invalid_values:
                with pytest.raises(IntegrityError), engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO ledger_entries (
                                id, project_id, session_key, origin, claim,
                                source_url, disposition, tags, created_at, updated_at
                            ) VALUES (
                                :id, :project_id, 'invalid-value', :origin,
                                'Invalid constrained value', 'https://example.test/invalid',
                                :disposition, '[]'::jsonb, now(), now()
                            )
                            """
                        ),
                        {
                            "id": uuid4(),
                            "project_id": ids["project_id"],
                            "origin": origin,
                            "disposition": disposition,
                        },
                    )

            with pytest.raises(IntegrityError), engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO ledger_notes (
                            id, project_id, session_key, origin, note_key, content,
                            tags, created_at, updated_at
                        ) VALUES (
                            :id, :project_id, 'migration-session', 'mcp-agent',
                            'next-query', 'Duplicate logical note', '[]'::jsonb,
                            now(), now()
                        )
                        """
                    ),
                    {"id": uuid4(), "project_id": ids["project_id"]},
                )
        finally:
            engine.dispose()

    def test_model_created_tables_are_idempotent_and_preserve_existing_rows(self, alembic_cfg, migration_db_url):
        """Simulate tables provisioned out of band before Alembic reaches 040."""
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_039)
            _create_model_ledger_tables(engine)
            with engine.begin() as conn:
                ids = _seed_parents(conn)
                entry_id = _insert_full_entry(conn, ids)
                note_id = _insert_full_note(conn, ids)

            command.upgrade(alembic_cfg, REV_040)

            with engine.connect() as conn:
                version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                entry_claim = conn.execute(
                    text("SELECT claim FROM ledger_entries WHERE id = :id"),
                    {"id": entry_id},
                ).scalar_one()
                note_content = conn.execute(
                    text("SELECT content FROM ledger_notes WHERE id = :id"),
                    {"id": note_id},
                ).scalar_one()
            assert version == REV_040
            assert entry_claim == "Passkeys reduce phishing exposure"
            assert note_content == "Investigate recovery evidence"
        finally:
            engine.dispose()

    @pytest.mark.parametrize(
        ("statements", "match"),
        (
            (
                ("ALTER TABLE ledger_entries ALTER COLUMN summary SET NOT NULL",),
                r"ledger_entries\.summary has incompatible nullability",
            ),
            (
                ("ALTER TABLE ledger_entries " "ALTER COLUMN origin SET DEFAULT 'deepsearch-worker'",),
                r"ledger_entries\.origin has incompatible server default",
            ),
            (
                (
                    "ALTER TABLE ledger_entries DROP CONSTRAINT " "ck_ledger_entries_nonempty_claim",
                    "ALTER TABLE ledger_entries ADD CONSTRAINT "
                    "ck_ledger_entries_nonempty_claim "
                    "CHECK (length(trim(claim)) >= 0)",
                ),
                r"ledger_entries\.ck_ledger_entries_nonempty_claim " r"has incompatible expression",
            ),
            (
                ("ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_pkey",),
                r"ledger_entries has incompatible primary key columns=\(\)",
            ),
        ),
        ids=("nullability", "server-default", "check", "primary-key"),
    )
    def test_each_table_contract_validator_refuses_an_isolated_defect(
        self,
        alembic_cfg,
        migration_db_url,
        statements,
        match,
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_039)
            _create_model_ledger_tables(engine)
            with engine.begin() as conn:
                for statement in statements:
                    conn.execute(text(statement))

            _assert_upgrade_refused_at_039(
                alembic_cfg,
                engine,
                match=match,
            )
        finally:
            engine.dispose()

    def test_computed_column_refuses_upgrade(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_039)
            _create_model_ledger_tables(engine)
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE ledger_entries DROP COLUMN summary"))
                conn.execute(
                    text("ALTER TABLE ledger_entries ADD COLUMN summary text " "GENERATED ALWAYS AS (claim) STORED")
                )

            _assert_upgrade_refused_at_039(
                alembic_cfg,
                engine,
                match=r"ledger_entries\.summary has an incompatible computed definition",
            )
        finally:
            engine.dispose()

    def test_duplicate_foreign_key_refuses_upgrade(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_039)
            _create_model_ledger_tables(engine)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE ledger_entries ADD CONSTRAINT "
                        "fk_ledger_entries_project_duplicate "
                        "FOREIGN KEY (project_id) REFERENCES projects(id) "
                        "ON DELETE CASCADE"
                    )
                )

            _assert_upgrade_refused_at_039(
                alembic_cfg,
                engine,
                match=r"ledger_entries has incompatible foreign keys",
            )
        finally:
            engine.dispose()

    def test_cross_schema_foreign_key_refuses_upgrade(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_039)
            _create_model_ledger_tables(engine)
            project_foreign_key = next(
                foreign_key
                for foreign_key in inspect(engine).get_foreign_keys("ledger_entries")
                if foreign_key["constrained_columns"] == ["project_id"]
            )
            constraint_name = project_foreign_key["name"]
            assert constraint_name is not None
            quoted_constraint = engine.dialect.identifier_preparer.quote(constraint_name)
            with engine.begin() as conn:
                conn.execute(text("CREATE SCHEMA ledger_shadow"))
                conn.execute(text("CREATE TABLE ledger_shadow.projects (id uuid PRIMARY KEY)"))
                conn.execute(text("ALTER TABLE ledger_entries " f"DROP CONSTRAINT {quoted_constraint}"))
                conn.execute(
                    text(
                        "ALTER TABLE ledger_entries ADD CONSTRAINT "
                        f"{quoted_constraint} FOREIGN KEY (project_id) "
                        "REFERENCES ledger_shadow.projects(id) ON DELETE CASCADE"
                    )
                )

            _assert_upgrade_refused_at_039(
                alembic_cfg,
                engine,
                match=r"ledger_entries has incompatible foreign keys",
            )
        finally:
            engine.dispose()

    def test_missing_note_identity_unique_refuses_upgrade(
        self,
        alembic_cfg,
        migration_db_url,
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_039)
            _create_model_ledger_tables(engine)
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE ledger_notes DROP CONSTRAINT " "uq_ledger_notes_project_session_key"))

            _assert_upgrade_refused_at_039(
                alembic_cfg,
                engine,
                match=r"ledger_notes has incompatible unique constraints",
            )
        finally:
            engine.dispose()

    @pytest.mark.parametrize(
        "create_index",
        (
            "CREATE INDEX ix_ledger_entries_project_created "
            "ON ledger_entries (project_id, created_at) "
            "WHERE disposition = 'supporting'",
            "CREATE INDEX ix_ledger_entries_project_created "
            "ON ledger_entries (project_id, created_at) INCLUDE (claim)",
            "CREATE INDEX ix_ledger_entries_project_created " "ON ledger_entries (project_id, created_at DESC)",
            "CREATE INDEX ix_ledger_entries_project_created "
            "ON ledger_entries (project_id, created_at) WITH (fillfactor = 70)",
        ),
        ids=("partial", "include", "sort", "storage-option"),
    )
    def test_non_plain_lookup_index_refuses_upgrade(
        self,
        alembic_cfg,
        migration_db_url,
        create_index,
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_039)
            _create_model_ledger_tables(engine)
            with engine.begin() as conn:
                conn.execute(text("DROP INDEX ix_ledger_entries_project_created"))
                conn.execute(text(create_index))

            _assert_upgrade_refused_at_039(
                alembic_cfg,
                engine,
                match=r"Index ix_ledger_entries_project_created .* " r"has an incompatible definition",
            )
        finally:
            engine.dispose()

    def test_same_columns_with_incompatible_shape_refuses_upgrade(
        self,
        alembic_cfg,
        migration_db_url,
    ):
        """A lookalike table must not be accepted merely because names match."""
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_039)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE ledger_entries (
                            id text PRIMARY KEY,
                            project_id uuid NOT NULL REFERENCES projects(id),
                            mission_id uuid,
                            session_key varchar(255) NOT NULL,
                            origin varchar(32) DEFAULT 'deepsearch-worker',
                            claim text NOT NULL,
                            summary text,
                            source_url text NOT NULL,
                            snippet text,
                            query text,
                            disposition varchar(32) NOT NULL,
                            tags json NOT NULL DEFAULT '[]',
                            owner_id uuid,
                            workspace_id uuid,
                            created_at timestamp without time zone,
                            updated_at timestamp without time zone
                        )
                        """
                    )
                )

            assert set(_columns(inspect(engine), "ledger_entries")) == ENTRY_COLUMNS
            with pytest.raises(
                RuntimeError,
                match=r"ledger_entries\.id has incompatible type",
            ):
                command.upgrade(alembic_cfg, REV_040)

            with engine.connect() as conn:
                version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == REV_039
        finally:
            engine.dispose()

    def test_downgrade_then_reupgrade_is_repeatable(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_040)
            assert {"ledger_entries", "ledger_notes"} <= set(inspect(engine).get_table_names())

            command.downgrade(alembic_cfg, REV_039)
            assert {"ledger_entries", "ledger_notes"}.isdisjoint(inspect(engine).get_table_names())

            command.upgrade(alembic_cfg, REV_040)
            assert {"ledger_entries", "ledger_notes"} <= set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
