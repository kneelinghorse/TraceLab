"""Real-PostgreSQL tests for stable saved-search/history ownership."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import command

pytestmark = pytest.mark.integration

REV_040 = "040_evidence_ledger_v1"
REV_041 = "041_search_artifact_owners"


def _insert_user(conn, *, display_name: str, email: str) -> UUID:
    user_id = uuid4()
    conn.execute(
        text(
            """
            INSERT INTO users (
                id, email, display_name, password_hash, role, is_active,
                created_at, updated_at
            ) VALUES (
                :id, :email, :display_name, 'not-a-real-hash', 'member', true,
                now(), now()
            )
            """
        ),
        {"id": user_id, "email": email, "display_name": display_name},
    )
    return user_id


def _insert_saved_search(conn, *, owner: str, name: str) -> UUID:
    artifact_id = uuid4()
    conn.execute(
        text(
            """
            INSERT INTO saved_searches (
                id, name, query_text, search_mode, filters, top_k, owner,
                use_count, created_at, updated_at
            ) VALUES (
                :id, :name, 'ownership query', 'semantic', '{}', 5, :owner,
                0, now(), now()
            )
            """
        ),
        {"id": artifact_id, "name": name, "owner": owner},
    )
    return artifact_id


def _insert_history(conn, *, user_label: str) -> UUID:
    artifact_id = uuid4()
    conn.execute(
        text(
            """
            INSERT INTO search_history (
                id, query_text, search_mode, filters, result_count, top_k,
                cache_hit, user_label, metadata_payload, top_chunks,
                created_at, updated_at
            ) VALUES (
                :id, 'ownership query', 'semantic', '{}', 0, 5, false,
                :user_label, '{}', '[]', now(), now()
            )
            """
        ),
        {"id": artifact_id, "user_label": user_label},
    )
    return artifact_id


def _insert_owned_saved_search(
    conn, *, owner_id: UUID, owner: str, name: str
) -> UUID:
    artifact_id = uuid4()
    conn.execute(
        text(
            """
            INSERT INTO saved_searches (
                id, name, query_text, search_mode, filters, top_k, owner,
                owner_id, use_count, created_at, updated_at
            ) VALUES (
                :id, :name, 'ownership query', 'semantic', '{}', 5, :owner,
                :owner_id, 0, now(), now()
            )
            """
        ),
        {
            "id": artifact_id,
            "name": name,
            "owner": owner,
            "owner_id": owner_id,
        },
    )
    return artifact_id


def _insert_owned_history(
    conn, *, owner_id: UUID, user_label: str
) -> UUID:
    artifact_id = uuid4()
    conn.execute(
        text(
            """
            INSERT INTO search_history (
                id, query_text, search_mode, filters, result_count, top_k,
                cache_hit, user_label, owner_id, metadata_payload, top_chunks,
                created_at, updated_at
            ) VALUES (
                :id, 'ownership query', 'semantic', '{}', 0, 5, false,
                :user_label, :owner_id, '{}', '[]', now(), now()
            )
            """
        ),
        {
            "id": artifact_id,
            "user_label": user_label,
            "owner_id": owner_id,
        },
    )
    return artifact_id


def _foreign_key(inspector, table: str) -> dict:
    matches = [
        foreign_key
        for foreign_key in inspector.get_foreign_keys(table)
        if foreign_key["constrained_columns"] == ["owner_id"]
    ]
    assert len(matches) == 1
    return matches[0]


def _assert_revision_041_schema(engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == REV_041

    inspector = inspect(engine)
    for table in ("saved_searches", "search_history"):
        assert "owner_id" in {
            column["name"] for column in inspector.get_columns(table)
        }
    assert "uq_saved_search_owner_id_name" in {
        unique["name"]
        for unique in inspector.get_unique_constraints("saved_searches")
    }
    assert "ix_saved_searches_owner_id_created_at" in {
        index["name"] for index in inspector.get_indexes("saved_searches")
    }
    assert "ix_search_history_owner_id_created_at" in {
        index["name"] for index in inspector.get_indexes("search_history")
    }


class TestSearchArtifactOwnerMigration:
    def test_all_legacy_labels_fail_closed_and_new_rows_cascade(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_040)
            with engine.begin() as conn:
                unique_user_id = _insert_user(
                    conn,
                    display_name="Unique Researcher",
                    email="unique@example.test",
                )
                _insert_user(
                    conn,
                    display_name="Ambiguous Researcher",
                    email="ambiguous-a@example.test",
                )
                _insert_user(
                    conn,
                    display_name="Ambiguous Researcher",
                    email="ambiguous-b@example.test",
                )
                _insert_user(
                    conn,
                    display_name="Email Is Not Identity",
                    email="legacy-label@example.test",
                )

                unique_saved = _insert_saved_search(
                    conn, owner="Unique Researcher", name="unique"
                )
                ambiguous_saved = _insert_saved_search(
                    conn, owner="Ambiguous Researcher", name="ambiguous"
                )
                unmatched_saved = _insert_saved_search(
                    conn, owner="No Such User", name="unmatched"
                )
                email_saved = _insert_saved_search(
                    conn, owner="legacy-label@example.test", name="email-label"
                )
                unique_history = _insert_history(
                    conn, user_label="Unique Researcher"
                )
                ambiguous_history = _insert_history(
                    conn, user_label="Ambiguous Researcher"
                )
                unmatched_history = _insert_history(
                    conn, user_label="No Such User"
                )
                email_history = _insert_history(
                    conn, user_label="legacy-label@example.test"
                )

            command.upgrade(alembic_cfg, REV_041)

            inspector = inspect(engine)
            for table in ("saved_searches", "search_history"):
                columns = {
                    column["name"]: column
                    for column in inspector.get_columns(table)
                }
                assert isinstance(columns["owner_id"]["type"], PGUUID)
                assert columns["owner_id"]["nullable"] is True
                foreign_key = _foreign_key(inspector, table)
                assert foreign_key["referred_table"] == "users"
                assert foreign_key["referred_columns"] == ["id"]
                assert foreign_key["options"].get("ondelete") == "CASCADE"

            saved_uniques = {
                unique["name"]: tuple(unique["column_names"])
                for unique in inspector.get_unique_constraints("saved_searches")
            }
            assert saved_uniques["uq_saved_search_owner_id_name"] == (
                "owner_id",
                "name",
            )
            assert "uq_saved_search_owner_name" not in saved_uniques

            saved_indexes = {
                index["name"]: tuple(index["column_names"])
                for index in inspector.get_indexes("saved_searches")
            }
            history_indexes = {
                index["name"]: tuple(index["column_names"])
                for index in inspector.get_indexes("search_history")
            }
            assert saved_indexes["ix_saved_searches_owner_id_created_at"] == (
                "owner_id",
                "created_at",
            )
            assert history_indexes["ix_search_history_owner_id_created_at"] == (
                "owner_id",
                "created_at",
            )

            with engine.connect() as conn:
                saved_owners = dict(
                    conn.execute(
                        text("SELECT id, owner_id FROM saved_searches")
                    ).all()
                )
                history_owners = dict(
                    conn.execute(
                        text("SELECT id, owner_id FROM search_history")
                    ).all()
                )
            for artifact_id in (
                unique_saved,
                ambiguous_saved,
                unmatched_saved,
                email_saved,
            ):
                assert saved_owners[artifact_id] is None
            for artifact_id in (
                unique_history,
                ambiguous_history,
                unmatched_history,
                email_history,
            ):
                assert history_owners[artifact_id] is None

            with engine.begin() as conn:
                owned_saved = _insert_owned_saved_search(
                    conn,
                    owner_id=unique_user_id,
                    owner="Unique Researcher",
                    name="owned-after-041",
                )
                owned_history = _insert_owned_history(
                    conn,
                    owner_id=unique_user_id,
                    user_label="Unique Researcher",
                )
                conn.execute(
                    text("DELETE FROM users WHERE id = :id"),
                    {"id": unique_user_id},
                )
            with engine.connect() as conn:
                assert conn.execute(
                    text("SELECT count(*) FROM saved_searches WHERE id = :id"),
                    {"id": owned_saved},
                ).scalar_one() == 0
                assert conn.execute(
                    text("SELECT count(*) FROM search_history WHERE id = :id"),
                    {"id": owned_history},
                ).scalar_one() == 0
                assert conn.execute(
                    text("SELECT count(*) FROM saved_searches WHERE id = :id"),
                    {"id": unique_saved},
                ).scalar_one() == 1
                assert conn.execute(
                    text("SELECT count(*) FROM search_history WHERE id = :id"),
                    {"id": unique_history},
                ).scalar_one() == 1
                assert conn.execute(
                    text("SELECT count(*) FROM saved_searches WHERE owner_id IS NULL")
                ).scalar_one() == 4
                assert conn.execute(
                    text("SELECT count(*) FROM search_history WHERE owner_id IS NULL")
                ).scalar_one() == 4
        finally:
            engine.dispose()

    def test_downgrade_restores_labels_and_reupgrade_fails_closed(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_040)
            with engine.begin() as conn:
                owner_id = _insert_user(
                    conn,
                    display_name="Round Trip Researcher",
                    email="round-trip@example.test",
                )

            command.upgrade(alembic_cfg, REV_041)
            with engine.begin() as conn:
                saved_id = _insert_owned_saved_search(
                    conn,
                    owner_id=owner_id,
                    owner="Round Trip Researcher",
                    name="round-trip",
                )
                history_id = _insert_owned_history(
                    conn,
                    owner_id=owner_id,
                    user_label="Round Trip Researcher",
                )
                conn.execute(
                    text(
                        "UPDATE users SET display_name = :display_name "
                        "WHERE id = :id"
                    ),
                    {
                        "id": owner_id,
                        "display_name": "Renamed Round Trip Researcher",
                    },
                )
            command.downgrade(alembic_cfg, REV_040)

            inspector = inspect(engine)
            for table in ("saved_searches", "search_history"):
                assert "owner_id" not in {
                    column["name"] for column in inspector.get_columns(table)
                }
            saved_uniques = {
                unique["name"]: tuple(unique["column_names"])
                for unique in inspector.get_unique_constraints("saved_searches")
            }
            saved_indexes = {
                index["name"]: tuple(index["column_names"])
                for index in inspector.get_indexes("saved_searches")
            }
            assert saved_uniques["uq_saved_search_owner_name"] == (
                "owner",
                "name",
            )
            assert saved_indexes["ix_saved_searches_owner_created_at"] == (
                "owner",
                "created_at",
            )
            with engine.connect() as conn:
                assert conn.execute(
                    text("SELECT owner FROM saved_searches WHERE id = :id"),
                    {"id": saved_id},
                ).scalar_one() == "Renamed Round Trip Researcher"
                assert conn.execute(
                    text(
                        "SELECT user_label FROM search_history WHERE id = :id"
                    ),
                    {"id": history_id},
                ).scalar_one() == "Renamed Round Trip Researcher"

            command.upgrade(alembic_cfg, REV_041)
            with engine.connect() as conn:
                assert conn.execute(
                    text("SELECT owner_id FROM saved_searches WHERE id = :id"),
                    {"id": saved_id},
                ).scalar_one() is None
                assert conn.execute(
                    text("SELECT owner_id FROM search_history WHERE id = :id"),
                    {"id": history_id},
                ).scalar_one() is None
        finally:
            engine.dispose()

    def test_renamed_and_reused_legacy_label_never_becomes_identity(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_040)
            with engine.begin() as conn:
                original_user_id = _insert_user(
                    conn,
                    display_name="Reusable Legacy Label",
                    email="original-legacy-owner@example.test",
                )
                saved_id = _insert_saved_search(
                    conn, owner="Reusable Legacy Label", name="legacy-query"
                )
                history_id = _insert_history(
                    conn, user_label="Reusable Legacy Label"
                )

            command.upgrade(alembic_cfg, REV_041)
            with engine.begin() as conn:
                assert conn.execute(
                    text("SELECT owner_id FROM saved_searches WHERE id = :id"),
                    {"id": saved_id},
                ).scalar_one() is None
                assert conn.execute(
                    text("SELECT owner_id FROM search_history WHERE id = :id"),
                    {"id": history_id},
                ).scalar_one() is None
                conn.execute(
                    text(
                        "UPDATE users SET display_name = 'Renamed Original User' "
                        "WHERE id = :id"
                    ),
                    {"id": original_user_id},
                )
                reused_user_id = _insert_user(
                    conn,
                    display_name="Reusable Legacy Label",
                    email="reused-legacy-label@example.test",
                )

            command.downgrade(alembic_cfg, REV_040)
            command.upgrade(alembic_cfg, REV_041)
            with engine.connect() as conn:
                assert conn.execute(
                    text("SELECT owner_id FROM saved_searches WHERE id = :id"),
                    {"id": saved_id},
                ).scalar_one() is None
                assert conn.execute(
                    text("SELECT owner_id FROM search_history WHERE id = :id"),
                    {"id": history_id},
                ).scalar_one() is None
                assert conn.execute(
                    text("SELECT count(*) FROM users WHERE id = :id"),
                    {"id": reused_user_id},
                ).scalar_one() == 1
        finally:
            engine.dispose()

    def test_downgrade_refuses_non_unique_referenced_display_name_atomically(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_040)
            with engine.begin() as conn:
                owner_id = _insert_user(
                    conn,
                    display_name="Original Owner Label",
                    email="ambiguous-round-trip@example.test",
                )

            command.upgrade(alembic_cfg, REV_041)
            with engine.begin() as conn:
                saved_id = _insert_owned_saved_search(
                    conn,
                    owner_id=owner_id,
                    owner="Original Owner Label",
                    name="ambiguous-owner",
                )
                history_id = _insert_owned_history(
                    conn,
                    owner_id=owner_id,
                    user_label="Original Owner Label",
                )
                conn.execute(
                    text(
                        "UPDATE users SET display_name = 'Shared Owner Label' "
                        "WHERE id = :id"
                    ),
                    {"id": owner_id},
                )
                _insert_user(
                    conn,
                    display_name="Shared Owner Label",
                    email="duplicate-round-trip@example.test",
                )

            with pytest.raises(RuntimeError, match="display_name.*non-unique"):
                command.downgrade(alembic_cfg, REV_040)

            _assert_revision_041_schema(engine)
            with engine.connect() as conn:
                saved_owner, saved_owner_id = conn.execute(
                    text(
                        "SELECT owner, owner_id FROM saved_searches "
                        "WHERE id = :id"
                    ),
                    {"id": saved_id},
                ).one()
                history_label, history_owner_id = conn.execute(
                    text(
                        "SELECT user_label, owner_id FROM search_history "
                        "WHERE id = :id"
                    ),
                    {"id": history_id},
                ).one()
            assert (saved_owner, saved_owner_id) == (
                "Original Owner Label",
                owner_id,
            )
            assert (history_label, history_owner_id) == (
                "Original Owner Label",
                owner_id,
            )
        finally:
            engine.dispose()

    def test_downgrade_refuses_restored_saved_search_collision_atomically(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_040)
            with engine.begin() as conn:
                owner_id = _insert_user(
                    conn,
                    display_name="Original Collision Owner",
                    email="collision-round-trip@example.test",
                )
                legacy_saved_id = _insert_saved_search(
                    conn,
                    owner="Renamed Collision Owner",
                    name="same-name",
                )

            command.upgrade(alembic_cfg, REV_041)
            with engine.begin() as conn:
                owned_saved_id = _insert_owned_saved_search(
                    conn,
                    owner_id=owner_id,
                    owner="Original Collision Owner",
                    name="same-name",
                )
                conn.execute(
                    text(
                        "UPDATE users SET display_name = 'Renamed Collision Owner' "
                        "WHERE id = :id"
                    ),
                    {"id": owner_id},
                )

            with pytest.raises(RuntimeError, match="owner/name values would collide"):
                command.downgrade(alembic_cfg, REV_040)

            _assert_revision_041_schema(engine)
            with engine.connect() as conn:
                rows = {
                    row.id: (row.owner, row.owner_id)
                    for row in conn.execute(
                        text(
                            "SELECT id, owner, owner_id FROM saved_searches "
                            "WHERE id IN (:owned_id, :legacy_id)"
                        ),
                        {
                            "owned_id": owned_saved_id,
                            "legacy_id": legacy_saved_id,
                        },
                    )
                }
            assert rows[owned_saved_id] == (
                "Original Collision Owner",
                owner_id,
            )
            assert rows[legacy_saved_id] == ("Renamed Collision Owner", None)
        finally:
            engine.dispose()
