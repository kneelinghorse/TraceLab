"""Create the project-scoped evidence ledger.

The table guards keep this migration idempotent in test databases where
``Base.metadata.create_all`` has already created the exact ORM tables.

Revision ID: 040_evidence_ledger_v1
Revises: 039_deepsearch_lease_v1
Create Date: 2026-08-20
"""

from __future__ import annotations

import re
from collections import Counter

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "040_evidence_ledger_v1"
down_revision = "039_deepsearch_lease_v1"
branch_labels = None
depends_on = None

_ENTRY_COLUMNS = {
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
_NOTE_COLUMNS = {
    "id",
    "project_id",
    "mission_id",
    "session_key",
    "note_key",
    "origin",
    "content",
    "tags",
    "owner_id",
    "workspace_id",
    "created_at",
    "updated_at",
}
_ENTRY_INDEXES = (
    ("ix_ledger_entries_project_created", ("project_id", "created_at")),
    (
        "ix_ledger_entries_project_session_created",
        ("project_id", "session_key", "created_at"),
    ),
    (
        "ix_ledger_entries_project_mission_created",
        ("project_id", "mission_id", "created_at"),
    ),
    (
        "ix_ledger_entries_workspace_owner_created",
        ("workspace_id", "owner_id", "created_at"),
    ),
)
_NOTE_INDEXES = (
    (
        "ix_ledger_notes_project_session_updated",
        ("project_id", "session_key", "updated_at"),
    ),
    (
        "ix_ledger_notes_project_mission_updated",
        ("project_id", "mission_id", "updated_at"),
    ),
    (
        "ix_ledger_notes_workspace_owner_updated",
        ("workspace_id", "owner_id", "updated_at"),
    ),
)
_ENTRY_COLUMN_SPECS = {
    "id": ("uuid", None, False, None),
    "project_id": ("uuid", None, False, None),
    "mission_id": ("uuid", None, True, None),
    "session_key": ("string", 255, False, None),
    "origin": ("string", 32, False, "mcp-agent"),
    "claim": ("text", None, False, None),
    "summary": ("text", None, True, None),
    "source_url": ("text", None, False, None),
    "snippet": ("text", None, True, None),
    "query": ("text", None, True, None),
    "disposition": ("string", 32, False, None),
    "tags": ("jsonb", None, False, "empty-json-array"),
    "owner_id": ("uuid", None, True, None),
    "workspace_id": ("uuid", None, True, None),
    "created_at": ("timestamp", None, False, "now"),
    "updated_at": ("timestamp", None, False, "now"),
}
_NOTE_COLUMN_SPECS = {
    "id": ("uuid", None, False, None),
    "project_id": ("uuid", None, False, None),
    "mission_id": ("uuid", None, True, None),
    "session_key": ("string", 255, False, None),
    "note_key": ("string", 100, False, None),
    "origin": ("string", 32, False, "mcp-agent"),
    "content": ("text", None, False, None),
    "tags": ("jsonb", None, False, "empty-json-array"),
    "owner_id": ("uuid", None, True, None),
    "workspace_id": ("uuid", None, True, None),
    "created_at": ("timestamp", None, False, "now"),
    "updated_at": ("timestamp", None, False, "now"),
}
_FOREIGN_KEYS = {
    "project_id": ("projects", "id", "CASCADE"),
    "mission_id": ("missions", "id", "SET NULL"),
    "owner_id": ("users", "id", "SET NULL"),
    "workspace_id": ("workspaces", "id", "SET NULL"),
}
_ENTRY_CHECKS = {
    "ck_ledger_entries_origin": (
        "origin=any(array['mcp-agent','deepsearch-worker'])",
        "originin('mcp-agent','deepsearch-worker')",
    ),
    "ck_ledger_entries_disposition": (
        "disposition=any(array['supporting','contradicting','rejected','background'])",
        "dispositionin('supporting','contradicting','rejected','background')",
    ),
    "ck_ledger_entries_nonempty_session": ("length(trim(session_key))>0",),
    "ck_ledger_entries_nonempty_claim": ("length(trim(claim))>0",),
    "ck_ledger_entries_nonempty_source_url": ("length(trim(source_url))>0",),
}
_NOTE_CHECKS = {
    "ck_ledger_notes_origin": (
        "origin=any(array['mcp-agent','deepsearch-worker'])",
        "originin('mcp-agent','deepsearch-worker')",
    ),
    "ck_ledger_notes_nonempty_session": ("length(trim(session_key))>0",),
    "ck_ledger_notes_nonempty_key": ("length(trim(note_key))>0",),
    "ck_ledger_notes_nonempty_content": ("length(trim(content))>0",),
}


def _uuid_type(bind: sa.engine.Connection) -> sa.types.TypeEngine:
    if bind.dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.String(36)


def _json_type(bind: sa.engine.Connection) -> sa.types.TypeEngine:
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def _json_empty_list_default(bind: sa.engine.Connection) -> sa.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text("'[]'::jsonb")
    return sa.text("'[]'")


def _assert_exact_columns(
    bind: sa.engine.Connection,
    table_name: str,
    expected: set[str],
) -> None:
    actual = {str(column["name"]) for column in sa.inspect(bind).get_columns(table_name)}
    if actual != expected:
        raise RuntimeError(
            f"{table_name} already exists with incompatible columns: "
            f"expected={sorted(expected)}, actual={sorted(actual)}"
        )


def _normalize_default(value: object | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", "", str(value).lower().replace('"', ""))


def _default_matches(actual: object | None, expected: str | None) -> bool:
    normalized = _normalize_default(actual)
    if expected is None:
        return normalized is None
    allowed = {
        "mcp-agent": {"'mcp-agent'", "'mcp-agent'::charactervarying", "'mcp-agent'::text"},
        "empty-json-array": {"'[]'", "'[]'::jsonb"},
        "now": {"now()", "current_timestamp"},
    }
    return normalized in allowed[expected]


def _type_matches(
    actual: sa.types.TypeEngine,
    expected_kind: str,
    expected_length: int | None,
) -> bool:
    if expected_kind == "uuid":
        return isinstance(actual, postgresql.UUID)
    if expected_kind == "string":
        return isinstance(actual, sa.String) and not isinstance(actual, sa.Text) and actual.length == expected_length
    if expected_kind == "text":
        return isinstance(actual, sa.Text)
    if expected_kind == "jsonb":
        return isinstance(actual, postgresql.JSONB)
    if expected_kind == "timestamp":
        return isinstance(actual, sa.DateTime) and actual.timezone is False
    return False


def _normalize_check(value: str) -> str:
    normalized = value.lower().replace('"', "")
    normalized = re.sub(
        r"::\s*(?:character varying|text)(?:\[\])?",
        "",
        normalized,
    )
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.replace("trim(bothfrom", "trim(")
    while normalized.startswith("(") and normalized.endswith(")"):
        depth = 0
        wraps_entire_expression = True
        for index, character in enumerate(normalized):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0 and index != len(normalized) - 1:
                    wraps_entire_expression = False
                    break
        if not wraps_entire_expression:
            break
        normalized = normalized[1:-1]
    return normalized


def _validate_column_contract(
    inspector: sa.Inspector,
    table_name: str,
    specs: dict[str, tuple[str, int | None, bool, str | None]],
) -> None:
    columns = {str(column["name"]): column for column in inspector.get_columns(table_name)}
    if set(columns) != set(specs):
        raise RuntimeError(f"{table_name} has incompatible columns")
    for name, (kind, length, nullable, default) in specs.items():
        column = columns[name]
        if column.get("computed") is not None:
            raise RuntimeError(f"{table_name}.{name} has an incompatible computed definition")
        if column.get("identity") is not None:
            raise RuntimeError(f"{table_name}.{name} has an incompatible identity definition")
        if not _type_matches(column["type"], kind, length):
            raise RuntimeError(f"{table_name}.{name} has incompatible type {column['type']}")
        if bool(column["nullable"]) is not nullable:
            raise RuntimeError(f"{table_name}.{name} has incompatible nullability")
        if not _default_matches(column.get("default"), default):
            raise RuntimeError(f"{table_name}.{name} has incompatible server default " f"{column.get('default')}")


def _validate_primary_key(inspector: sa.Inspector, table_name: str) -> None:
    columns = tuple(str(value) for value in inspector.get_pk_constraint(table_name).get("constrained_columns", ()))
    if columns != ("id",):
        raise RuntimeError(f"{table_name} has incompatible primary key columns={columns}")


def _validate_foreign_keys(inspector: sa.Inspector, table_name: str) -> None:
    actual: Counter[
        tuple[
            tuple[str, ...],
            str | None,
            str,
            tuple[str, ...],
            tuple[tuple[str, str], ...],
        ]
    ] = Counter()
    for foreign_key in inspector.get_foreign_keys(table_name):
        constrained = tuple(str(value) for value in foreign_key.get("constrained_columns", ()))
        referred = tuple(str(value) for value in foreign_key.get("referred_columns", ()))
        options = foreign_key.get("options") or {}
        normalized_options = tuple(
            sorted(
                (
                    str(key),
                    str(value).upper() if isinstance(value, str) else str(value),
                )
                for key, value in options.items()
                if value is not None
            )
        )
        referred_schema = foreign_key.get("referred_schema")
        signature = (
            constrained,
            str(referred_schema) if referred_schema is not None else None,
            str(foreign_key.get("referred_table")),
            referred,
            normalized_options,
        )
        actual[signature] += 1

    expected = Counter(
        {
            (
                (column,),
                None,
                referred_table,
                (referred_column,),
                (("ondelete", ondelete),),
            ): 1
            for column, (referred_table, referred_column, ondelete) in _FOREIGN_KEYS.items()
        }
    )
    if actual != expected:
        raise RuntimeError(f"{table_name} has incompatible foreign keys: actual={actual}")


def _validate_checks(
    inspector: sa.Inspector,
    table_name: str,
    expected: dict[str, tuple[str, ...]],
) -> None:
    actual = {
        str(check["name"]): _normalize_check(str(check["sqltext"]))
        for check in inspector.get_check_constraints(table_name)
        if check.get("name")
    }
    if set(actual) != set(expected):
        raise RuntimeError(f"{table_name} has incompatible check constraints: " f"actual={sorted(actual)}")
    for name, accepted_expressions in expected.items():
        if actual[name] not in accepted_expressions:
            raise RuntimeError(f"{table_name}.{name} has incompatible expression {actual[name]}")


def _validate_unique_constraints(
    inspector: sa.Inspector,
    table_name: str,
) -> None:
    actual = {
        str(constraint["name"]): tuple(str(value) for value in constraint.get("column_names", ()))
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }
    expected = (
        {
            "uq_ledger_notes_project_session_key": (
                "project_id",
                "session_key",
                "note_key",
            )
        }
        if table_name == "ledger_notes"
        else {}
    )
    if actual != expected:
        raise RuntimeError(f"{table_name} has incompatible unique constraints: actual={actual}")


def _validate_postgres_table(
    bind: sa.engine.Connection,
    table_name: str,
    specs: dict[str, tuple[str, int | None, bool, str | None]],
    checks: dict[str, tuple[str, ...]],
) -> None:
    inspector = sa.inspect(bind)
    _validate_column_contract(inspector, table_name, specs)
    _validate_primary_key(inspector, table_name)
    _validate_foreign_keys(inspector, table_name)
    _validate_checks(inspector, table_name, checks)
    _validate_unique_constraints(inspector, table_name)


def _validate_plain_index_definition(
    table_name: str,
    name: str,
    index: dict[str, object],
    expected_columns: tuple[str, ...],
) -> None:
    columns = tuple(None if value is None else str(value) for value in index.get("column_names", ()))
    include_columns = tuple(str(value) for value in index.get("include_columns", ()))
    expressions = tuple(str(value) for value in index.get("expressions", ()))
    column_sorting = index.get("column_sorting") or {}
    dialect_options = dict(index.get("dialect_options") or {})
    dialect_include = tuple(str(value) for value in (dialect_options.pop("postgresql_include", ()) or ()))
    incompatible = (
        columns != expected_columns
        or bool(index.get("unique"))
        or bool(index.get("duplicates_constraint"))
        or bool(include_columns)
        or bool(dialect_include)
        or bool(expressions)
        or bool(column_sorting)
        or bool(dialect_options)
    )
    if incompatible:
        raise RuntimeError(
            f"Index {name} on {table_name} has an incompatible definition: "
            f"columns={columns}, unique={index.get('unique')}, "
            f"include_columns={include_columns or dialect_include}, "
            f"expressions={expressions}, column_sorting={column_sorting}, "
            f"dialect_options={dialect_options}"
        )


def _ensure_indexes(
    bind: sa.engine.Connection,
    table_name: str,
    definitions: tuple[tuple[str, tuple[str, ...]], ...],
) -> None:
    existing = {str(index["name"]): index for index in sa.inspect(bind).get_indexes(table_name) if index.get("name")}
    for name, columns in definitions:
        current = existing.get(name)
        if current is None:
            op.create_index(name, table_name, list(columns), unique=False)
            continue
        _validate_plain_index_definition(table_name, name, current, columns)


def _validate_indexes(
    bind: sa.engine.Connection,
    table_name: str,
    definitions: tuple[tuple[str, tuple[str, ...]], ...],
) -> None:
    actual = {
        str(index["name"]): index
        for index in sa.inspect(bind).get_indexes(table_name)
        if index.get("name") and not index.get("duplicates_constraint")
    }
    expected_names = {name for name, _columns in definitions}
    if set(actual) != expected_names:
        raise RuntimeError(f"{table_name} has incompatible indexes: actual={sorted(actual)}")
    for name, columns in definitions:
        _validate_plain_index_definition(table_name, name, actual[name], columns)


def _ensure_entries_table(bind: sa.engine.Connection) -> None:
    if sa.inspect(bind).has_table("ledger_entries"):
        _assert_exact_columns(bind, "ledger_entries", _ENTRY_COLUMNS)
        if bind.dialect.name == "postgresql":
            _validate_postgres_table(
                bind,
                "ledger_entries",
                _ENTRY_COLUMN_SPECS,
                _ENTRY_CHECKS,
            )
        return

    op.create_table(
        "ledger_entries",
        sa.Column("id", _uuid_type(bind), nullable=False),
        sa.Column("project_id", _uuid_type(bind), nullable=False),
        sa.Column("mission_id", _uuid_type(bind), nullable=True),
        sa.Column("session_key", sa.String(length=255), nullable=False),
        sa.Column(
            "origin",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'mcp-agent'"),
        ),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("disposition", sa.String(length=32), nullable=False),
        sa.Column(
            "tags",
            _json_type(bind),
            nullable=False,
            server_default=_json_empty_list_default(bind),
        ),
        sa.Column("owner_id", _uuid_type(bind), nullable=True),
        sa.Column("workspace_id", _uuid_type(bind), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "origin IN ('mcp-agent', 'deepsearch-worker')",
            name="ck_ledger_entries_origin",
        ),
        sa.CheckConstraint(
            "disposition IN ('supporting', 'contradicting', 'rejected', 'background')",
            name="ck_ledger_entries_disposition",
        ),
        sa.CheckConstraint(
            "length(trim(session_key)) > 0",
            name="ck_ledger_entries_nonempty_session",
        ),
        sa.CheckConstraint(
            "length(trim(claim)) > 0",
            name="ck_ledger_entries_nonempty_claim",
        ),
        sa.CheckConstraint(
            "length(trim(source_url)) > 0",
            name="ck_ledger_entries_nonempty_source_url",
        ),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def _ensure_notes_table(bind: sa.engine.Connection) -> None:
    if sa.inspect(bind).has_table("ledger_notes"):
        _assert_exact_columns(bind, "ledger_notes", _NOTE_COLUMNS)
        if bind.dialect.name == "postgresql":
            _validate_postgres_table(
                bind,
                "ledger_notes",
                _NOTE_COLUMN_SPECS,
                _NOTE_CHECKS,
            )
        return

    op.create_table(
        "ledger_notes",
        sa.Column("id", _uuid_type(bind), nullable=False),
        sa.Column("project_id", _uuid_type(bind), nullable=False),
        sa.Column("mission_id", _uuid_type(bind), nullable=True),
        sa.Column("session_key", sa.String(length=255), nullable=False),
        sa.Column("note_key", sa.String(length=100), nullable=False),
        sa.Column(
            "origin",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'mcp-agent'"),
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            _json_type(bind),
            nullable=False,
            server_default=_json_empty_list_default(bind),
        ),
        sa.Column("owner_id", _uuid_type(bind), nullable=True),
        sa.Column("workspace_id", _uuid_type(bind), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "origin IN ('mcp-agent', 'deepsearch-worker')",
            name="ck_ledger_notes_origin",
        ),
        sa.CheckConstraint(
            "length(trim(session_key)) > 0",
            name="ck_ledger_notes_nonempty_session",
        ),
        sa.CheckConstraint(
            "length(trim(note_key)) > 0",
            name="ck_ledger_notes_nonempty_key",
        ),
        sa.CheckConstraint(
            "length(trim(content)) > 0",
            name="ck_ledger_notes_nonempty_content",
        ),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "session_key",
            "note_key",
            name="uq_ledger_notes_project_session_key",
        ),
    )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_entries_table(bind)
    _ensure_indexes(bind, "ledger_entries", _ENTRY_INDEXES)
    _ensure_notes_table(bind)
    _ensure_indexes(bind, "ledger_notes", _NOTE_INDEXES)
    if bind.dialect.name == "postgresql":
        _validate_postgres_table(
            bind,
            "ledger_entries",
            _ENTRY_COLUMN_SPECS,
            _ENTRY_CHECKS,
        )
        _validate_indexes(bind, "ledger_entries", _ENTRY_INDEXES)
        _validate_postgres_table(
            bind,
            "ledger_notes",
            _NOTE_COLUMN_SPECS,
            _NOTE_CHECKS,
        )
        _validate_indexes(bind, "ledger_notes", _NOTE_INDEXES)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("ledger_notes"):
        op.drop_table("ledger_notes")
    if sa.inspect(bind).has_table("ledger_entries"):
        op.drop_table("ledger_entries")
