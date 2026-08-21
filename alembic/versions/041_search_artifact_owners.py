"""Add stable ownership to saved searches and search history.

Legacy ``saved_searches.owner`` and ``search_history.user_label`` values are
display metadata, not stable identities. This migration adds nullable UUID
foreign keys and deliberately does not derive identity from those labels.
Every pre-migration row remains NULL so ordinary-user queries fail closed.
Rows created after the migration carry authoritative user IDs, and the foreign
keys cascade on user deletion so ephemeral verification principals cannot
leave history behind.

Revision ID: 041_search_artifact_owners
Revises: 040_evidence_ledger_v1
Create Date: 2026-08-21
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "041_search_artifact_owners"
down_revision = "040_evidence_ledger_v1"
branch_labels = None
depends_on = None

_OWNER_FKS = {
    "saved_searches": "fk_saved_searches_owner_id",
    "search_history": "fk_search_history_owner_id",
}


def _owner_foreign_key(inspector: sa.Inspector, table: str) -> dict | None:
    matches = [
        foreign_key
        for foreign_key in inspector.get_foreign_keys(table)
        if foreign_key.get("constrained_columns") == ["owner_id"]
    ]
    if len(matches) > 1:
        raise RuntimeError(f"{table}.owner_id has multiple foreign keys")
    return matches[0] if matches else None


def _validate_owner_column(
    bind: sa.engine.Connection, inspector: sa.Inspector, table: str
) -> None:
    columns = {
        str(column["name"]): column for column in inspector.get_columns(table)
    }
    column = columns["owner_id"]
    if not column["nullable"]:
        raise RuntimeError(f"{table}.owner_id must remain nullable for legacy rows")
    if bind.dialect.name == "postgresql" and not isinstance(
        column["type"], postgresql.UUID
    ):
        raise RuntimeError(f"{table}.owner_id must use PostgreSQL UUID")


def _ensure_owner_column(bind: sa.engine.Connection, table: str) -> None:
    inspector = inspect(bind)
    columns = {str(column["name"]) for column in inspector.get_columns(table)}
    if "owner_id" not in columns:
        op.add_column(table, sa.Column("owner_id", sa.UUID(), nullable=True))

    inspector = inspect(bind)
    _validate_owner_column(bind, inspector, table)
    foreign_key = _owner_foreign_key(inspector, table)
    if foreign_key is None:
        op.create_foreign_key(
            _OWNER_FKS[table],
            table,
            "users",
            ["owner_id"],
            ["id"],
            ondelete="CASCADE",
        )
        return

    if (
        foreign_key.get("referred_table") != "users"
        or foreign_key.get("referred_columns") != ["id"]
        or foreign_key.get("options", {}).get("ondelete") != "CASCADE"
    ):
        raise RuntimeError(f"{table}.owner_id has an incompatible foreign key")


def _ensure_saved_search_indexes(bind: sa.engine.Connection) -> None:
    inspector = inspect(bind)
    uniques = {
        unique["name"]: tuple(unique.get("column_names") or ())
        for unique in inspector.get_unique_constraints("saved_searches")
    }
    if "uq_saved_search_owner_name" in uniques:
        op.drop_constraint(
            "uq_saved_search_owner_name", "saved_searches", type_="unique"
        )

    inspector = inspect(bind)
    indexes = {
        index["name"]: tuple(index.get("column_names") or ())
        for index in inspector.get_indexes("saved_searches")
    }
    if "ix_saved_searches_owner_created_at" in indexes:
        op.drop_index(
            "ix_saved_searches_owner_created_at", table_name="saved_searches"
        )

    inspector = inspect(bind)
    uniques = {
        unique["name"]: tuple(unique.get("column_names") or ())
        for unique in inspector.get_unique_constraints("saved_searches")
    }
    expected_unique = ("owner_id", "name")
    actual_unique = uniques.get("uq_saved_search_owner_id_name")
    if actual_unique is None:
        op.create_unique_constraint(
            "uq_saved_search_owner_id_name",
            "saved_searches",
            ["owner_id", "name"],
        )
    elif actual_unique != expected_unique:
        raise RuntimeError("saved-search owner/name unique constraint is incompatible")

    inspector = inspect(bind)
    indexes = {
        index["name"]: tuple(index.get("column_names") or ())
        for index in inspector.get_indexes("saved_searches")
    }
    expected_index = ("owner_id", "created_at")
    actual_index = indexes.get("ix_saved_searches_owner_id_created_at")
    if actual_index is None:
        op.create_index(
            "ix_saved_searches_owner_id_created_at",
            "saved_searches",
            ["owner_id", "created_at"],
        )
    elif actual_index != expected_index:
        raise RuntimeError("saved-search owner index is incompatible")


def _ensure_history_index(bind: sa.engine.Connection) -> None:
    indexes = {
        index["name"]: tuple(index.get("column_names") or ())
        for index in inspect(bind).get_indexes("search_history")
    }
    expected = ("owner_id", "created_at")
    actual = indexes.get("ix_search_history_owner_id_created_at")
    if actual is None:
        op.create_index(
            "ix_search_history_owner_id_created_at",
            "search_history",
            ["owner_id", "created_at"],
        )
    elif actual != expected:
        raise RuntimeError("search-history owner index is incompatible")


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_owner_column(bind, "saved_searches")
    _ensure_owner_column(bind, "search_history")
    _ensure_saved_search_indexes(bind)
    _ensure_history_index(bind)


def _drop_owner_column(bind: sa.engine.Connection, table: str) -> None:
    inspector = inspect(bind)
    foreign_key = _owner_foreign_key(inspector, table)
    if foreign_key is not None:
        constraint_name = foreign_key.get("name")
        if not constraint_name:
            raise RuntimeError(f"{table}.owner_id foreign key has no name")
        op.drop_constraint(constraint_name, table, type_="foreignkey")
    op.drop_column(table, "owner_id")


def _restore_legacy_owner_metadata(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "postgresql":
        # Keep the safety checks and metadata rewrite stable against concurrent
        # user/artifact writes until the downgrade DDL completes.
        bind.execute(
            text(
                "LOCK TABLE saved_searches, search_history, users "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
        )

    ambiguous_display_name = bind.execute(
        text(
            """
            WITH referenced_owner_ids AS (
                SELECT owner_id
                FROM saved_searches
                WHERE owner_id IS NOT NULL
                UNION
                SELECT owner_id
                FROM search_history
                WHERE owner_id IS NOT NULL
            )
            SELECT referenced_user.display_name
            FROM referenced_owner_ids AS referenced
            JOIN users AS referenced_user
              ON referenced_user.id = referenced.owner_id
            JOIN users AS duplicate_user
              ON duplicate_user.display_name = referenced_user.display_name
             AND duplicate_user.id <> referenced_user.id
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if ambiguous_display_name is not None:
        raise RuntimeError(
            "cannot downgrade search artifact ownership: referenced "
            f"display_name {ambiguous_display_name!r} is non-unique"
        )

    restored_collision = bind.execute(
        text(
            """
            WITH restored_saved_searches AS (
                SELECT
                    CASE
                        WHEN artifact.owner_id IS NULL THEN artifact.owner
                        ELSE matched_user.display_name
                    END AS restored_owner,
                    artifact.name
                FROM saved_searches AS artifact
                LEFT JOIN users AS matched_user
                  ON matched_user.id = artifact.owner_id
            )
            SELECT restored_owner, name
            FROM restored_saved_searches
            WHERE restored_owner IS NOT NULL
              AND name IS NOT NULL
            GROUP BY restored_owner, name
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if restored_collision is not None:
        raise RuntimeError(
            "cannot downgrade search artifact ownership: restored saved-search "
            "owner/name values would collide for "
            f"({restored_collision.restored_owner!r}, {restored_collision.name!r})"
        )

    bind.execute(
        text(
            """
            UPDATE saved_searches AS artifact
            SET owner = matched_user.display_name
            FROM users AS matched_user
            WHERE artifact.owner_id = matched_user.id
            """
        )
    )
    bind.execute(
        text(
            """
            UPDATE search_history AS artifact
            SET user_label = matched_user.display_name
            FROM users AS matched_user
            WHERE artifact.owner_id = matched_user.id
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    _restore_legacy_owner_metadata(bind)

    saved_indexes = {
        index["name"] for index in inspect(bind).get_indexes("saved_searches")
    }
    if "ix_saved_searches_owner_id_created_at" in saved_indexes:
        op.drop_index(
            "ix_saved_searches_owner_id_created_at", table_name="saved_searches"
        )

    saved_uniques = {
        unique["name"]
        for unique in inspect(bind).get_unique_constraints("saved_searches")
    }
    if "uq_saved_search_owner_id_name" in saved_uniques:
        op.drop_constraint(
            "uq_saved_search_owner_id_name", "saved_searches", type_="unique"
        )

    history_indexes = {
        index["name"] for index in inspect(bind).get_indexes("search_history")
    }
    if "ix_search_history_owner_id_created_at" in history_indexes:
        op.drop_index(
            "ix_search_history_owner_id_created_at", table_name="search_history"
        )

    _drop_owner_column(bind, "saved_searches")
    _drop_owner_column(bind, "search_history")

    saved_uniques = {
        unique["name"]
        for unique in inspect(bind).get_unique_constraints("saved_searches")
    }
    if "uq_saved_search_owner_name" not in saved_uniques:
        op.create_unique_constraint(
            "uq_saved_search_owner_name",
            "saved_searches",
            ["owner", "name"],
        )

    saved_indexes = {
        index["name"] for index in inspect(bind).get_indexes("saved_searches")
    }
    if "ix_saved_searches_owner_created_at" not in saved_indexes:
        op.create_index(
            "ix_saved_searches_owner_created_at",
            "saved_searches",
            ["owner", "created_at"],
        )
