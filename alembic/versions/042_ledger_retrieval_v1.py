"""Normalize ledger sources and add PostgreSQL full-text retrieval.

Source identity uses a SHA-256 digest rather than a B-tree over the full URL.
Evidence URLs may be 4,096 characters, which is larger than PostgreSQL's
maximum index-row size.  The original URL remains authoritative and is checked
against its digest whenever application code resolves a source.

Revision ID: 042_ledger_retrieval_v1
Revises: 041_search_artifact_owners
Create Date: 2026-08-21
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from types import SimpleNamespace

import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "042_ledger_retrieval_v1"
down_revision = "041_search_artifact_owners"
branch_labels = None
depends_on = None

_SOURCE_COLUMNS = {
    "id",
    "project_id",
    "source_url",
    "source_url_hash",
    "sighting_count",
    "first_seen_at",
    "last_seen_at",
}
_SOURCE_UNIQUE = "uq_ledger_sources_project_url_hash"
_SOURCE_ENTRY_UNIQUE = "uq_ledger_sources_id_project"
_SOURCE_INDEX = "ix_ledger_sources_project_last_seen"
_ENTRY_SOURCE_INDEX = "ix_ledger_entries_source_created"
_SEARCH_INDEX = "ix_ledger_entries_search_vector"
_ENTRY_SOURCE_FK = "fk_ledger_entries_source_project"
_SEARCH_VECTOR_SQL = """
to_tsvector(
    'english'::regconfig,
    COALESCE(claim, ''::text) || ' '::text ||
    COALESCE(summary, ''::text) || ' '::text ||
    COALESCE(source_url, ''::text) || ' '::text ||
    COALESCE(snippet, ''::text) || ' '::text ||
    COALESCE(query, ''::text)
)
""".strip()


def _uuid_type(bind: sa.engine.Connection) -> sa.types.TypeEngine:
    if bind.dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.String(36)


def _database_uuid(bind: sa.engine.Connection, value: uuid.UUID) -> uuid.UUID | str:
    return value if bind.dialect.name == "postgresql" else str(value)


def _column_map(inspector: sa.Inspector, table_name: str) -> dict[str, Mapping]:
    return {str(column["name"]): column for column in inspector.get_columns(table_name)}


def _ensure_sources_table(bind: sa.engine.Connection) -> None:
    inspector = inspect(bind)
    if not inspector.has_table("ledger_sources"):
        op.create_table(
            "ledger_sources",
            sa.Column("id", _uuid_type(bind), nullable=False),
            sa.Column("project_id", _uuid_type(bind), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("source_url_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "sighting_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            ),
            sa.Column(
                "first_seen_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "last_seen_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "length(trim(source_url)) > 0",
                name="ck_ledger_sources_nonempty_url",
            ),
            sa.CheckConstraint(
                "length(source_url_hash) = 64",
                name="ck_ledger_sources_hash_length",
            ),
            sa.CheckConstraint(
                "sighting_count > 0",
                name="ck_ledger_sources_positive_sightings",
            ),
            sa.ForeignKeyConstraint(
                ["project_id"],
                ["projects.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "project_id",
                "source_url_hash",
                name=_SOURCE_UNIQUE,
            ),
            sa.UniqueConstraint(
                "id",
                "project_id",
                name=_SOURCE_ENTRY_UNIQUE,
            ),
        )
    else:
        columns = _column_map(inspector, "ledger_sources")
        if set(columns) != _SOURCE_COLUMNS:
            raise RuntimeError(f"ledger_sources already exists with incompatible columns: actual={sorted(columns)}")
        if columns["source_url_hash"]["type"].length != 64:
            raise RuntimeError("ledger_sources.source_url_hash must be String(64)")
        if columns["source_url"]["nullable"]:
            raise RuntimeError("ledger_sources.source_url must be non-null")
        if columns["sighting_count"]["nullable"]:
            raise RuntimeError("ledger_sources.sighting_count must be non-null")

    inspector = inspect(bind)
    uniques = {
        str(item["name"]): tuple(str(value) for value in item.get("column_names", ()))
        for item in inspector.get_unique_constraints("ledger_sources")
        if item.get("name")
    }
    expected_unique = ("project_id", "source_url_hash")
    actual_unique = uniques.get(_SOURCE_UNIQUE)
    if actual_unique is None:
        op.create_unique_constraint(
            _SOURCE_UNIQUE,
            "ledger_sources",
            list(expected_unique),
        )
    elif actual_unique != expected_unique:
        raise RuntimeError("ledger source identity constraint is incompatible")

    expected_entry_unique = ("id", "project_id")
    actual_entry_unique = uniques.get(_SOURCE_ENTRY_UNIQUE)
    if actual_entry_unique is None:
        op.create_unique_constraint(
            _SOURCE_ENTRY_UNIQUE,
            "ledger_sources",
            list(expected_entry_unique),
        )
    elif actual_entry_unique != expected_entry_unique:
        raise RuntimeError("ledger source entry-link constraint is incompatible")

    indexes = {
        str(item["name"]): tuple(str(value) for value in item.get("column_names", ()))
        for item in inspect(bind).get_indexes("ledger_sources")
        if item.get("name") and not item.get("duplicates_constraint")
    }
    expected_index = ("project_id", "last_seen_at")
    actual_index = indexes.get(_SOURCE_INDEX)
    if actual_index is None:
        op.create_index(
            _SOURCE_INDEX,
            "ledger_sources",
            list(expected_index),
        )
    elif actual_index != expected_index:
        raise RuntimeError("ledger source recency index is incompatible")


def _ensure_entry_source_column(bind: sa.engine.Connection) -> None:
    columns = _column_map(inspect(bind), "ledger_entries")
    if "source_id" not in columns:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("ledger_entries") as batch_op:
                batch_op.add_column(sa.Column("source_id", _uuid_type(bind), nullable=True))
        else:
            op.add_column(
                "ledger_entries",
                sa.Column("source_id", _uuid_type(bind), nullable=True),
            )


def _source_hash(source_url: str) -> str:
    return hashlib.sha256(source_url.encode("utf-8")).hexdigest()


def _backfill_sources(bind: sa.engine.Connection) -> None:
    source_table = sa.table(
        "ledger_sources",
        sa.column("id", _uuid_type(bind)),
        sa.column("project_id", _uuid_type(bind)),
        sa.column("source_url", sa.Text()),
        sa.column("source_url_hash", sa.String(64)),
        sa.column("sighting_count", sa.Integer()),
        sa.column("first_seen_at", sa.DateTime()),
        sa.column("last_seen_at", sa.DateTime()),
    )
    entry_table = sa.table(
        "ledger_entries",
        sa.column("project_id", _uuid_type(bind)),
        sa.column("source_id", _uuid_type(bind)),
        sa.column("source_url", sa.Text()),
        sa.column("created_at", sa.DateTime()),
    )

    groups = bind.execute(
        sa.select(
            entry_table.c.project_id,
            entry_table.c.source_url,
            sa.func.count().label("sighting_count"),
            sa.func.min(entry_table.c.created_at).label("first_seen_at"),
            sa.func.max(entry_table.c.created_at).label("last_seen_at"),
        ).group_by(entry_table.c.project_id, entry_table.c.source_url)
    ).all()
    existing_rows = bind.execute(sa.select(source_table)).all()
    sources = {(str(row.project_id), str(row.source_url_hash)): row for row in existing_rows}

    for group in groups:
        source_url = str(group.source_url)
        source_url_hash = _source_hash(source_url)
        key = (str(group.project_id), source_url_hash)
        current = sources.get(key)
        if current is not None and current.source_url != source_url:
            raise RuntimeError(
                f"ledger source hash collision for project {group.project_id}: existing and backfill URLs differ"
            )

        if current is None:
            source_id = _database_uuid(bind, uuid.uuid4())
            values = {
                "id": source_id,
                "project_id": group.project_id,
                "source_url": source_url,
                "source_url_hash": source_url_hash,
                "sighting_count": int(group.sighting_count),
                "first_seen_at": group.first_seen_at,
                "last_seen_at": group.last_seen_at,
            }
            bind.execute(sa.insert(source_table).values(**values))
            current = SimpleNamespace(**values)
            sources[key] = current
        else:
            first_seen_at = min(value for value in (current.first_seen_at, group.first_seen_at) if value is not None)
            last_seen_at = max(value for value in (current.last_seen_at, group.last_seen_at) if value is not None)
            bind.execute(
                sa.update(source_table)
                .where(source_table.c.id == current.id)
                .values(
                    sighting_count=max(
                        int(current.sighting_count),
                        int(group.sighting_count),
                    ),
                    first_seen_at=first_seen_at,
                    last_seen_at=last_seen_at,
                )
            )

        bind.execute(
            sa.update(entry_table)
            .where(
                entry_table.c.project_id == group.project_id,
                entry_table.c.source_url == source_url,
            )
            .values(source_id=current.id)
        )

    invalid_links = bind.execute(
        text(
            """
            SELECT count(*)
            FROM ledger_entries AS entry
            LEFT JOIN ledger_sources AS source ON source.id = entry.source_id
            WHERE entry.source_id IS NULL
               OR source.id IS NULL
               OR source.project_id <> entry.project_id
               OR source.source_url <> entry.source_url
            """
        )
    ).scalar_one()
    if invalid_links:
        raise RuntimeError(f"ledger source backfill left {invalid_links} invalid entry link(s)")


def _entry_source_foreign_keys(inspector: sa.Inspector) -> list[dict]:
    return [
        item
        for item in inspector.get_foreign_keys("ledger_entries")
        if "source_id" in item.get("constrained_columns", ())
    ]


def _finalize_entry_source_contract(bind: sa.engine.Connection) -> None:
    columns = _column_map(inspect(bind), "ledger_entries")
    if columns["source_id"]["nullable"]:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("ledger_entries") as batch_op:
                batch_op.alter_column(
                    "source_id",
                    existing_type=_uuid_type(bind),
                    nullable=False,
                )
        else:
            op.alter_column(
                "ledger_entries",
                "source_id",
                existing_type=_uuid_type(bind),
                nullable=False,
            )

    foreign_keys = _entry_source_foreign_keys(inspect(bind))
    if len(foreign_keys) > 1:
        raise RuntimeError("ledger_entries.source_id has multiple foreign keys")
    if not foreign_keys:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("ledger_entries") as batch_op:
                batch_op.create_foreign_key(
                    _ENTRY_SOURCE_FK,
                    "ledger_sources",
                    ["source_id", "project_id"],
                    ["id", "project_id"],
                    ondelete="NO ACTION",
                    deferrable=True,
                    initially="DEFERRED",
                )
        else:
            op.create_foreign_key(
                _ENTRY_SOURCE_FK,
                "ledger_entries",
                "ledger_sources",
                ["source_id", "project_id"],
                ["id", "project_id"],
                ondelete="NO ACTION",
                deferrable=True,
                initially="DEFERRED",
            )
    else:
        foreign_key = foreign_keys[0]
        options = foreign_key.get("options", {})
        if (
            foreign_key.get("constrained_columns") != ["source_id", "project_id"]
            or foreign_key.get("referred_table") != "ledger_sources"
            or foreign_key.get("referred_columns") != ["id", "project_id"]
            or str(options.get("ondelete") or "NO ACTION").upper() != "NO ACTION"
            or options.get("deferrable") is not True
            or str(options.get("initially") or "").upper() != "DEFERRED"
        ):
            raise RuntimeError("ledger_entries.source_id foreign key is incompatible")

    indexes = {
        str(item["name"]): tuple(str(value) for value in item.get("column_names", ()))
        for item in inspect(bind).get_indexes("ledger_entries")
        if item.get("name") and not item.get("duplicates_constraint")
    }
    expected_index = ("source_id", "created_at")
    actual_index = indexes.get(_ENTRY_SOURCE_INDEX)
    if actual_index is None:
        op.create_index(
            _ENTRY_SOURCE_INDEX,
            "ledger_entries",
            list(expected_index),
        )
    elif actual_index != expected_index:
        raise RuntimeError("ledger entry source index is incompatible")


def _ensure_search_index(bind: sa.engine.Connection) -> None:
    if bind.dialect.name != "postgresql":
        return
    index_contract = (
        bind.execute(
            text(
                """
            SELECT access_method.amname AS access_method,
                   pg_get_expr(index_metadata.indpred,
                               index_metadata.indrelid) AS predicate,
                   index_metadata.indisvalid AS is_valid,
                   index_metadata.indisready AS is_ready,
                   index_metadata.indnkeyatts AS key_count,
                   operator_class.opcname AS operator_class
            FROM pg_class AS index_relation
            JOIN pg_index AS index_metadata
              ON index_metadata.indexrelid = index_relation.oid
            JOIN pg_class AS table_relation
              ON table_relation.oid = index_metadata.indrelid
            JOIN pg_namespace AS table_namespace
              ON table_namespace.oid = table_relation.relnamespace
            JOIN pg_am AS access_method
              ON access_method.oid = index_relation.relam
            LEFT JOIN pg_opclass AS operator_class
              ON operator_class.oid = index_metadata.indclass[0]
            WHERE table_namespace.nspname = current_schema()
              AND table_relation.relname = 'ledger_entries'
              AND index_relation.relname = :index_name
            """
            ),
            {"index_name": _SEARCH_INDEX},
        )
        .mappings()
        .one_or_none()
    )
    if index_contract is None:
        op.execute(f"CREATE INDEX {_SEARCH_INDEX} ON ledger_entries USING gin ({_SEARCH_VECTOR_SQL})")
        return

    bind.execute(text("SET LOCAL enable_seqscan = off"))
    runtime_plan = "\n".join(
        bind.execute(
            text(
                # Constant-only interpolation must mirror the runtime predicate.
                f"""
                EXPLAIN SELECT id FROM ledger_entries
                WHERE ({_SEARCH_VECTOR_SQL})
                      @@ websearch_to_tsquery(
                          'english'::regconfig,
                          'ledger index contract'
                      )
                """  # noqa: S608
            )
        ).scalars()
    )
    if (
        index_contract["access_method"] != "gin"
        or index_contract["predicate"] is not None
        or index_contract["is_valid"] is not True
        or index_contract["is_ready"] is not True
        or index_contract["key_count"] != 1
        or index_contract["operator_class"] != "tsvector_ops"
        or _SEARCH_INDEX not in runtime_plan
    ):
        raise RuntimeError("ledger full-text search index is incompatible")


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_sources_table(bind)
    _ensure_entry_source_column(bind)
    _backfill_sources(bind)
    _finalize_entry_source_contract(bind)
    _ensure_search_index(bind)


def _drop_entry_source_contract(bind: sa.engine.Connection) -> None:
    indexes = {str(item["name"]) for item in inspect(bind).get_indexes("ledger_entries") if item.get("name")}
    if _ENTRY_SOURCE_INDEX in indexes:
        op.drop_index(_ENTRY_SOURCE_INDEX, table_name="ledger_entries")

    foreign_keys = _entry_source_foreign_keys(inspect(bind))
    if foreign_keys:
        constraint_name = foreign_keys[0].get("name")
        if not constraint_name:
            raise RuntimeError("ledger_entries.source_id foreign key has no name")
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("ledger_entries") as batch_op:
                batch_op.drop_constraint(constraint_name, type_="foreignkey")
                batch_op.drop_column("source_id")
        else:
            op.drop_constraint(
                constraint_name,
                "ledger_entries",
                type_="foreignkey",
            )
            op.drop_column("ledger_entries", "source_id")
    elif "source_id" in _column_map(inspect(bind), "ledger_entries"):
        op.drop_column("ledger_entries", "source_id")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"DROP INDEX IF EXISTS {_SEARCH_INDEX}")
    _drop_entry_source_contract(bind)
    if inspect(bind).has_table("ledger_sources"):
        op.drop_table("ledger_sources")
