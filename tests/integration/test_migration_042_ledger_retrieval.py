"""Real-PostgreSQL contract tests for LEDGER-3 source normalization and FTS."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import String, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.services.evidence_ledger import _SEARCH_VECTOR_SQL as RUNTIME_SEARCH_VECTOR_SQL

pytestmark = pytest.mark.integration

REV_041 = "041_search_artifact_owners"
REV_042 = "042_ledger_retrieval_v1"
SOURCE_COLUMNS = {
    "id",
    "project_id",
    "source_url",
    "source_url_hash",
    "sighting_count",
    "first_seen_at",
    "last_seen_at",
}
SEARCH_VECTOR_SQL = """
to_tsvector(
    'english'::regconfig,
    COALESCE(claim, ''::text) || ' '::text ||
    COALESCE(summary, ''::text) || ' '::text ||
    COALESCE(source_url, ''::text) || ' '::text ||
    COALESCE(snippet, ''::text) || ' '::text ||
    COALESCE(query, ''::text)
)
""".strip()
EXPECTED_SEARCH_INDEX_DDL = """
CREATE INDEX ix_ledger_entries_expected_search_vector
ON ledger_entries USING gin (
    to_tsvector(
        'english'::regconfig,
        COALESCE(claim, ''::text) || ' '::text ||
        COALESCE(summary, ''::text) || ' '::text ||
        COALESCE(source_url, ''::text) || ' '::text ||
        COALESCE(snippet, ''::text) || ' '::text ||
        COALESCE(query, ''::text)
    )
)
"""
LOOKALIKE_SEARCH_INDEXES = (
    pytest.param(
        """
        CREATE INDEX ix_ledger_entries_search_vector
        ON ledger_entries USING gin (
            to_tsvector('english'::regconfig, COALESCE(claim, ''::text))
        )
        """,
        id="claim-only",
    ),
    pytest.param(
        """
        CREATE INDEX ix_ledger_entries_search_vector
        ON ledger_entries USING gin (
            to_tsvector(
                'simple'::regconfig,
                COALESCE(claim, ''::text) || ' '::text ||
                COALESCE(summary, ''::text) || ' '::text ||
                COALESCE(source_url, ''::text) || ' '::text ||
                COALESCE(snippet, ''::text) || ' '::text ||
                COALESCE(query, ''::text)
            )
        ) WHERE disposition = 'supporting'
        """,
        id="wrong-config-partial",
    ),
    pytest.param(
        """
        CREATE INDEX ix_ledger_entries_search_vector
        ON ledger_entries USING gin (
            to_tsvector(
                'english'::regconfig,
                COALESCE(claim, ''::text || ' '::text) ||
                COALESCE(summary, ''::text) || ' '::text ||
                COALESCE(source_url, ''::text) || ' '::text ||
                COALESCE(snippet, ''::text) || ' '::text ||
                COALESCE(query, ''::text)
            )
        )
        """,
        id="regrouped-separator-fallback",
    ),
)


def _seed_project(conn, label: str) -> dict[str, UUID]:
    ids = {
        "user_id": uuid4(),
        "workspace_id": uuid4(),
        "project_id": uuid4(),
    }
    conn.execute(
        text(
            """
            INSERT INTO users (
                id, email, display_name, password_hash, role, is_active,
                created_at, updated_at
            ) VALUES (
                :id, :email, :label, 'not-a-real-hash', 'member', true,
                now(), now()
            )
            """
        ),
        {
            "id": ids["user_id"],
            "email": f"ledger-042-{label}-{ids['user_id']}@example.test",
            "label": f"Ledger 042 {label}",
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO workspaces (id, name, created_at)
            VALUES (:id, :name, now())
            """
        ),
        {"id": ids["workspace_id"], "name": f"Ledger 042 {label} Space"},
    )
    conn.execute(
        text(
            """
            INSERT INTO projects (
                id, name, owner_id, workspace_id, created_at, updated_at
            ) VALUES (
                :id, :name, :owner_id, :workspace_id, now(), now()
            )
            """
        ),
        {
            "id": ids["project_id"],
            "name": f"Ledger 042 {label} Project",
            "owner_id": ids["user_id"],
            "workspace_id": ids["workspace_id"],
        },
    )
    return ids


def _insert_legacy_entry(
    conn,
    ids: dict[str, UUID],
    *,
    session_key: str,
    claim: str,
    source_url: str,
    created_at: datetime,
) -> UUID:
    entry_id = uuid4()
    conn.execute(
        text(
            """
            INSERT INTO ledger_entries (
                id, project_id, session_key, origin, claim, summary,
                source_url, snippet, query, disposition, tags, owner_id,
                workspace_id, created_at, updated_at
            ) VALUES (
                :id, :project_id, :session_key, 'mcp-agent', :claim,
                'Archived source evidence', :source_url,
                'A directly observed excerpt.',
                'source reuse', 'supporting', '[]'::jsonb,
                :owner_id, :workspace_id, :created_at, :created_at
            )
            """
        ),
        {
            "id": entry_id,
            "project_id": ids["project_id"],
            "session_key": session_key,
            "claim": claim,
            "source_url": source_url,
            "owner_id": ids["user_id"],
            "workspace_id": ids["workspace_id"],
            "created_at": created_at,
        },
    )
    return entry_id


def _seed_legacy_duplicates(conn) -> dict[str, object]:
    first_project = _seed_project(conn, "first")
    second_project = _seed_project(conn, "second")
    shared_url = "https://example.test/research/source"
    long_url = "https://example.test/" + ("a" * (4_096 - len("https://example.test/")))
    first_seen = datetime(2026, 8, 19, 10, 0, 0)
    last_seen = first_seen + timedelta(days=1)

    entry_ids = [
        _insert_legacy_entry(
            conn,
            first_project,
            session_key="legacy-session-one",
            claim="Researchers run phishing-resistant authentication studies.",
            source_url=shared_url,
            created_at=first_seen,
        ),
        _insert_legacy_entry(
            conn,
            first_project,
            session_key="legacy-session-two",
            claim="A later session corroborates the running study.",
            source_url=shared_url,
            created_at=last_seen,
        ),
        _insert_legacy_entry(
            conn,
            first_project,
            session_key="legacy-long-one",
            claim="A maximum-length source remains indexable by identity.",
            source_url=long_url,
            created_at=first_seen,
        ),
        _insert_legacy_entry(
            conn,
            first_project,
            session_key="legacy-long-two",
            claim="The maximum-length source is reused in another session.",
            source_url=long_url,
            created_at=last_seen,
        ),
        _insert_legacy_entry(
            conn,
            second_project,
            session_key="other-project-session",
            claim="The same URL in another project has independent provenance.",
            source_url=shared_url,
            created_at=last_seen,
        ),
    ]
    return {
        "first_project": first_project,
        "second_project": second_project,
        "shared_url": shared_url,
        "long_url": long_url,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "entry_ids": entry_ids,
    }


def _index_definition(conn, name: str) -> str | None:
    return conn.execute(
        text(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND indexname = :name
            """
        ),
        {"name": name},
    ).scalar_one_or_none()


def _index_contract(conn, name: str):
    return (
        conn.execute(
            text(
                """
            SELECT access_method.amname AS method,
                   pg_get_expr(index_row.indexprs, index_row.indrelid) AS expression,
                   pg_get_expr(index_row.indpred, index_row.indrelid) AS predicate,
                   index_row.indisvalid AS is_valid
            FROM pg_index AS index_row
            JOIN pg_class AS index_class
              ON index_class.oid = index_row.indexrelid
            JOIN pg_am AS access_method
              ON access_method.oid = index_class.relam
            WHERE index_class.relname = :name
              AND index_class.relnamespace = current_schema()::regnamespace
            """
            ),
            {"name": name},
        )
        .mappings()
        .one()
    )


def _assert_exact_search_index(conn) -> None:
    """Compare parsed expressions so field/config/predicate lookalikes cannot pass."""
    conn.execute(text(EXPECTED_SEARCH_INDEX_DDL))
    try:
        actual = _index_contract(conn, "ix_ledger_entries_search_vector")
        expected = _index_contract(
            conn,
            "ix_ledger_entries_expected_search_vector",
        )
        assert actual["method"] == expected["method"] == "gin"
        assert actual["expression"] == expected["expression"]
        assert actual["predicate"] is None
        assert actual["is_valid"] is True
    finally:
        conn.execute(text("DROP INDEX ix_ledger_entries_expected_search_vector"))


def test_041_to_042_backfills_project_sources_and_functional_search_index(
    alembic_cfg,
    migration_db_url,
):
    """Legacy duplicate URLs become reusable sources without an oversized URL index."""
    assert len(REV_042) <= 32, "production alembic_version.version_num is VARCHAR(32)"
    engine = create_engine(migration_db_url)
    try:
        command.upgrade(alembic_cfg, REV_041)
        with engine.begin() as conn:
            seeded = _seed_legacy_duplicates(conn)

        command.upgrade(alembic_cfg, REV_042)

        inspector = inspect(engine)
        assert "ledger_sources" in inspector.get_table_names()
        source_columns = {column["name"]: column for column in inspector.get_columns("ledger_sources")}
        assert set(source_columns) == SOURCE_COLUMNS
        assert isinstance(source_columns["id"]["type"], PGUUID)
        assert isinstance(source_columns["project_id"]["type"], PGUUID)
        assert isinstance(source_columns["source_url_hash"]["type"], String)
        assert source_columns["source_url_hash"]["type"].length == 64
        assert all(not column["nullable"] for column in source_columns.values())

        entry_columns = {column["name"]: column for column in inspector.get_columns("ledger_entries")}
        assert isinstance(entry_columns["source_id"]["type"], PGUUID)
        assert entry_columns["source_id"]["nullable"] is False
        source_fks = [
            foreign_key
            for foreign_key in inspector.get_foreign_keys("ledger_entries")
            if foreign_key["referred_table"] == "ledger_sources"
        ]
        assert len(source_fks) == 1
        assert source_fks[0]["constrained_columns"] == [
            "source_id",
            "project_id",
        ]
        assert source_fks[0]["referred_table"] == "ledger_sources"
        assert source_fks[0]["referred_columns"] == ["id", "project_id"]

        source_project_fks = [
            foreign_key
            for foreign_key in inspector.get_foreign_keys("ledger_sources")
            if foreign_key["constrained_columns"] == ["project_id"] and foreign_key["referred_table"] == "projects"
        ]
        entry_project_fks = [
            foreign_key
            for foreign_key in inspector.get_foreign_keys("ledger_entries")
            if foreign_key["constrained_columns"] == ["project_id"] and foreign_key["referred_table"] == "projects"
        ]
        assert len(source_project_fks) == 1
        assert len(entry_project_fks) == 1
        assert source_project_fks[0]["options"].get("ondelete") == "CASCADE"
        assert entry_project_fks[0]["options"].get("ondelete") == "CASCADE"

        source_uniques = {
            unique["name"]: tuple(unique["column_names"])
            for unique in inspector.get_unique_constraints("ledger_sources")
        }
        assert source_uniques["uq_ledger_sources_project_url_hash"] == (
            "project_id",
            "source_url_hash",
        )
        assert ("id", "project_id") in source_uniques.values()
        entry_indexes = {
            index["name"]: tuple(index.get("column_names") or ())
            for index in inspector.get_indexes("ledger_entries")
            if index["name"] != "ix_ledger_entries_search_vector"
        }
        assert entry_indexes["ix_ledger_entries_source_created"] == (
            "source_id",
            "created_at",
        )

        with engine.connect() as conn:
            sources = (
                conn.execute(
                    text(
                        """
                    SELECT id, project_id, source_url, source_url_hash,
                           sighting_count, first_seen_at, last_seen_at
                    FROM ledger_sources
                    ORDER BY project_id, source_url
                    """
                    )
                )
                .mappings()
                .all()
            )
            links = (
                conn.execute(
                    text(
                        """
                    SELECT entry.id, entry.project_id, entry.source_url,
                           source.id AS source_id, source.source_url AS normalized_url
                    FROM ledger_entries AS entry
                    JOIN ledger_sources AS source ON source.id = entry.source_id
                    """
                    )
                )
                .mappings()
                .all()
            )
            index_definition = _index_definition(conn, "ix_ledger_entries_search_vector")
            source_link_contract = (
                conn.execute(
                    text(
                        """
                    SELECT confdeltype AS delete_action,
                           condeferrable AS is_deferrable,
                           condeferred AS is_initially_deferred
                    FROM pg_constraint
                    WHERE conname = :constraint_name
                      AND conrelid = 'ledger_entries'::regclass
                    """
                    ),
                    {"constraint_name": source_fks[0]["name"]},
                )
                .mappings()
                .one()
            )

        assert len(sources) == 3
        assert dict(source_link_contract) == {
            "delete_action": "a",
            "is_deferrable": True,
            "is_initially_deferred": True,
        }, "project cascades require a deferred NO ACTION source link"
        first_project_id = seeded["first_project"]["project_id"]
        second_project_id = seeded["second_project"]["project_id"]
        shared_sources = [source for source in sources if source["source_url"] == seeded["shared_url"]]
        assert len(shared_sources) == 2
        assert {source["project_id"] for source in shared_sources} == {
            first_project_id,
            second_project_id,
        }
        first_shared = next(source for source in shared_sources if source["project_id"] == first_project_id)
        assert first_shared["sighting_count"] == 2
        assert first_shared["first_seen_at"] == seeded["first_seen"]
        assert first_shared["last_seen_at"] == seeded["last_seen"]

        long_source = next(source for source in sources if source["source_url"] == seeded["long_url"])
        assert len(long_source["source_url"]) == 4_096
        assert long_source["source_url_hash"] == hashlib.sha256(seeded["long_url"].encode("utf-8")).hexdigest()
        assert long_source["sighting_count"] == 2
        assert len(links) == 5
        assert all(link["source_url"] == link["normalized_url"] for link in links)

        assert index_definition is not None
        normalized_index = " ".join(index_definition.lower().split())
        assert "using gin" in normalized_index
        assert "to_tsvector('english'::regconfig" in normalized_index
        for field in ("claim", "summary", "source_url", "snippet", "query"):
            assert field in normalized_index
        with engine.begin() as conn:
            _assert_exact_search_index(conn)

        with engine.begin() as conn:
            conn.execute(text("SET LOCAL enable_seqscan = off"))
            plan = "\n".join(
                row[0]
                for row in conn.execute(
                    text(
                        # Constant-only interpolation must mirror the indexed expression.
                        f"""
                        EXPLAIN SELECT id FROM ledger_entries
                        WHERE ({RUNTIME_SEARCH_VECTOR_SQL})
                              @@ websearch_to_tsquery(
                                  'english'::regconfig,
                                  'running'
                              )
                        """  # noqa: S608
                    )
                )
            )
            matched_sessions = (
                conn.execute(
                    text(
                        # Constant-only interpolation must mirror the indexed expression.
                        f"""
                    SELECT session_key FROM ledger_entries
                    WHERE ({SEARCH_VECTOR_SQL})
                          @@ websearch_to_tsquery(
                              'english'::regconfig,
                              'running'
                          )
                    ORDER BY session_key
                    """  # noqa: S608
                    )
                )
                .scalars()
                .all()
            )
        assert "ix_ledger_entries_search_vector" in plan
        assert matched_sessions == ["legacy-session-one", "legacy-session-two"]

        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ledger_sources (
                        id, project_id, source_url, source_url_hash,
                        sighting_count, first_seen_at, last_seen_at
                    ) VALUES (
                        :id, :project_id, :url, :source_hash, 1, now(), now()
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "project_id": first_project_id,
                    "url": "https://collision.example.test/different",
                    "source_hash": first_shared["source_url_hash"],
                },
            )

        second_shared = next(source for source in shared_sources if source["project_id"] == second_project_id)
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE ledger_entries
                    SET source_id = :cross_project_source_id
                    WHERE id = :entry_id
                    """
                ),
                {
                    "cross_project_source_id": second_shared["id"],
                    "entry_id": seeded["entry_ids"][0],
                },
            )

        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM projects WHERE id = :project_id"),
                {"project_id": second_project_id},
            )
            remaining_entry_count = conn.execute(
                text(
                    """
                    SELECT count(*) FROM ledger_entries
                    WHERE project_id = :project_id
                    """
                ),
                {"project_id": second_project_id},
            ).scalar_one()
            remaining_source_count = conn.execute(
                text(
                    """
                    SELECT count(*) FROM ledger_sources
                    WHERE project_id = :project_id
                    """
                ),
                {"project_id": second_project_id},
            ).scalar_one()
        assert remaining_entry_count == 0
        assert remaining_source_count == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize("lookalike_index_sql", LOOKALIKE_SEARCH_INDEXES)
def test_042_rejects_named_gin_indexes_that_do_not_match_the_search_contract(
    alembic_cfg,
    migration_db_url,
    lookalike_index_sql,
):
    """A familiar name and GIN method cannot disguise an incomplete FTS index."""
    engine = create_engine(migration_db_url)
    try:
        command.upgrade(alembic_cfg, REV_041)
        with engine.begin() as conn:
            conn.execute(text(lookalike_index_sql))

        with pytest.raises(
            RuntimeError,
            match="ledger full-text search index is incompatible",
        ):
            command.upgrade(alembic_cfg, REV_042)

        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REV_041
            assert (
                _index_definition(
                    conn,
                    "ix_ledger_entries_search_vector",
                )
                is not None
            )
    finally:
        engine.dispose()


def test_downgrade_and_reupgrade_preserve_legacy_entries(
    alembic_cfg,
    migration_db_url,
):
    """A rollback may remove derived source rows but never the captured evidence."""
    engine = create_engine(migration_db_url)
    try:
        command.upgrade(alembic_cfg, REV_041)
        with engine.begin() as conn:
            seeded = _seed_legacy_duplicates(conn)
        command.upgrade(alembic_cfg, REV_042)

        command.downgrade(alembic_cfg, REV_041)
        inspector = inspect(engine)
        assert "ledger_sources" not in inspector.get_table_names()
        assert "source_id" not in {column["name"] for column in inspector.get_columns("ledger_entries")}
        with engine.connect() as conn:
            downgraded = conn.execute(text("SELECT id, source_url FROM ledger_entries ORDER BY id")).all()
            assert _index_definition(conn, "ix_ledger_entries_search_vector") is None
        assert {row.id for row in downgraded} == set(seeded["entry_ids"])

        command.upgrade(alembic_cfg, REV_042)
        with engine.connect() as conn:
            reupgraded = conn.execute(
                text(
                    """
                    SELECT entry.id, entry.source_url, source.sighting_count
                    FROM ledger_entries AS entry
                    JOIN ledger_sources AS source ON source.id = entry.source_id
                    ORDER BY entry.id
                    """
                )
            ).all()
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert {row.id for row in reupgraded} == set(seeded["entry_ids"])
        assert {row.source_url for row in reupgraded} == {
            seeded["shared_url"],
            seeded["long_url"],
        }
        assert sorted(row.sighting_count for row in reupgraded) == [1, 2, 2, 2, 2]
        assert version == REV_042
    finally:
        engine.dispose()
