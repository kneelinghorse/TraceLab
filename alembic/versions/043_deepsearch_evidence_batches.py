"""Add idempotent DeepSearch evidence-ledger batch ownership.

The batch/link guards support test databases where ``Base.metadata.create_all``
has already created their exact ORM shape. The durable outbox is migration-owned
and any pre-existing same-name table is rejected fail-closed.

Revision ID: 043_deepsearch_evidence
Revises: 042_ledger_retrieval_v1
Create Date: 2026-08-21
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "043_deepsearch_evidence"
down_revision = "042_ledger_retrieval_v1"
branch_labels = None
depends_on = None

_BATCH_TABLE = "deepsearch_ledger_batches"
_BATCH_COLUMNS = {
    "id",
    "mission_id",
    "deepsearch_job_id",
    "session_key",
    "payload_hash",
    "entry_count",
    "created_at",
    "updated_at",
}
_BATCH_MISSION_FK = "fk_deepsearch_ledger_batches_mission"
_BATCH_IDENTITY = "uq_deepsearch_ledger_batches_mission_job"
_BATCH_INDEX = "ix_deepsearch_ledger_batches_mission_created"
_ENTRY_BATCH_FK = "fk_ledger_entries_deepsearch_batch"
_ENTRY_BATCH_INDEX = "ix_ledger_entries_deepsearch_batch_created"
_SQLITE_FK_NAMING_CONVENTION = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
_OUTBOX_TABLE = "deepsearch_evidence_outbox"
_OUTBOX_COLUMNS = {
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
_OUTBOX_PK = "pk_deepsearch_evidence_outbox"
_OUTBOX_MISSION_FK = "fk_deepsearch_evidence_outbox_mission"
_OUTBOX_INDEX = "ix_deepsearch_evidence_outbox_delivery"
_OUTBOX_CHECK_SQL = {
    "ck_deepsearch_evidence_outbox_nonempty_job": ("length(trim(deepsearch_job_id)) > 0"),
    "ck_deepsearch_evidence_outbox_nonempty_result_key": ("length(trim(deepsearch_result_key)) > 0"),
    "ck_deepsearch_evidence_outbox_positive_attempt": ("mission_attempt_count > 0"),
    "ck_deepsearch_evidence_outbox_terminal_status": ("terminal_status IN ('completed', 'validation_failed')"),
    "ck_deepsearch_evidence_outbox_schema_version": "schema_version = 1",
    "ck_deepsearch_evidence_outbox_state": ("state IN ('pending', 'leased', 'acked', 'dead_letter')"),
    "ck_deepsearch_evidence_outbox_delivery_attempts": ("delivery_attempt_count >= 0"),
    "ck_deepsearch_evidence_outbox_http_status": (
        "last_http_status IS NULL OR (last_http_status >= 100 AND last_http_status <= 599)"
    ),
    "ck_deepsearch_evidence_outbox_state_coherence": (
        "(state = 'leased' AND lease_token IS NOT NULL "
        "AND lease_expires_at IS NOT NULL "
        "AND next_attempt_at = lease_expires_at AND acked_at IS NULL) OR "
        "(state = 'acked' AND lease_token IS NULL "
        "AND lease_expires_at IS NULL AND acked_at IS NOT NULL) OR "
        "(state IN ('pending', 'dead_letter') AND lease_token IS NULL "
        "AND lease_expires_at IS NULL AND acked_at IS NULL)"
    ),
}
_BATCH_CHECKS = {
    "ck_deepsearch_ledger_batches_nonempty_job": ("lengthtrimdeepsearch_job_id>0"),
    "ck_deepsearch_ledger_batches_nonempty_session": ("lengthtrimsession_key>0"),
    "ck_deepsearch_ledger_batches_hash_length": "lengthpayload_hash=64",
    "ck_deepsearch_ledger_batches_entry_count": ("entry_count>0andentry_count<=1000"),
}


def _uuid_type(bind: sa.engine.Connection) -> sa.types.TypeEngine:
    if bind.dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.String(36)


def _is_uuid_type(
    bind: sa.engine.Connection,
    value: sa.types.TypeEngine,
) -> bool:
    if bind.dialect.name == "postgresql":
        return isinstance(value, postgresql.UUID)
    return isinstance(value, sa.String) and value.length == 36


def _column_map(
    bind: sa.engine.Connection,
    table_name: str,
) -> dict[str, dict]:
    return {str(column["name"]): column for column in sa.inspect(bind).get_columns(table_name)}


def _validate_batch_columns(bind: sa.engine.Connection) -> None:
    columns = _column_map(bind, _BATCH_TABLE)
    if set(columns) != _BATCH_COLUMNS:
        raise RuntimeError(f"{_BATCH_TABLE} has incompatible columns: actual={sorted(columns)}")
    for name in ("id", "mission_id"):
        if not _is_uuid_type(bind, columns[name]["type"]):
            raise RuntimeError(f"{_BATCH_TABLE}.{name} has incompatible type")
    expected_strings = {
        "deepsearch_job_id": 100,
        "session_key": 255,
        "payload_hash": 64,
    }
    for name, length in expected_strings.items():
        value = columns[name]["type"]
        if not isinstance(value, sa.String) or value.length != length:
            raise RuntimeError(f"{_BATCH_TABLE}.{name} has incompatible type")
    if not isinstance(columns["entry_count"]["type"], sa.Integer):
        raise RuntimeError(f"{_BATCH_TABLE}.entry_count has incompatible type")
    for name in ("created_at", "updated_at"):
        if not isinstance(columns[name]["type"], sa.DateTime):
            raise RuntimeError(f"{_BATCH_TABLE}.{name} has incompatible type")
    if any(bool(column["nullable"]) for column in columns.values()):
        raise RuntimeError(f"{_BATCH_TABLE} columns must all be non-null")


def _validate_batch_constraints(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    primary_key = tuple(
        str(value) for value in inspector.get_pk_constraint(_BATCH_TABLE).get("constrained_columns", ())
    )
    if primary_key != ("id",):
        raise RuntimeError(f"{_BATCH_TABLE} has incompatible primary key")

    uniques = {
        str(item["name"]): tuple(str(value) for value in item.get("column_names", ()))
        for item in inspector.get_unique_constraints(_BATCH_TABLE)
        if item.get("name")
    }
    if uniques != {_BATCH_IDENTITY: ("mission_id", "deepsearch_job_id")}:
        raise RuntimeError(f"{_BATCH_TABLE} has incompatible unique constraints: {uniques}")

    checks = {
        str(item["name"]): _normalize_check(str(item.get("sqltext") or ""))
        for item in inspector.get_check_constraints(_BATCH_TABLE)
        if item.get("name")
    }
    if checks != _BATCH_CHECKS:
        raise RuntimeError(f"{_BATCH_TABLE} has incompatible check constraints: {checks}")

    mission_foreign_keys = [
        item for item in inspector.get_foreign_keys(_BATCH_TABLE) if item.get("constrained_columns") == ["mission_id"]
    ]
    if len(mission_foreign_keys) != 1:
        raise RuntimeError(f"{_BATCH_TABLE} has incompatible mission foreign key")
    foreign_key = mission_foreign_keys[0]
    if (
        foreign_key.get("name") != _BATCH_MISSION_FK
        or foreign_key.get("referred_table") != "missions"
        or foreign_key.get("referred_columns") != ["id"]
        or str((foreign_key.get("options") or {}).get("ondelete") or "").upper() != "CASCADE"
    ):
        raise RuntimeError(f"{_BATCH_TABLE} has incompatible mission foreign key")


def _normalize_check(value: str) -> str:
    """Normalize PostgreSQL/SQLite rendering without weakening semantics."""
    normalized = value.lower().replace('"', "")
    normalized = re.sub(
        r"::\s*(?:character varying|text|integer|smallint)(?:\[\])?",
        "",
        normalized,
    )
    normalized = normalized.replace("btrim", "trim")
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.replace("trim(bothfrom", "trim(")
    normalized = normalized.replace("(", "").replace(")", "")
    return re.sub(r"=anyarray\[(.*?)\]", r"in\1", normalized)


def _normalize_default(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).lower().replace('"', "")
    normalized = re.sub(
        r"::\s*(?:character varying|text|integer|smallint)(?:\[\])?",
        "",
        normalized,
    )
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.replace("(", "").replace(")", "")


def _validate_plain_index(
    index: dict,
    expected_columns: tuple[str, ...],
) -> None:
    columns = tuple(None if value is None else str(value) for value in index.get("column_names", ()))
    incompatible = (
        columns != expected_columns
        or bool(index.get("unique"))
        or bool(index.get("duplicates_constraint"))
        or bool(index.get("expressions"))
        or bool(index.get("column_sorting"))
        or bool(index.get("include_columns"))
    )
    if incompatible:
        raise RuntimeError(f"Index {index.get('name')} has an incompatible definition")


def _ensure_batch_index(bind: sa.engine.Connection) -> None:
    indexes = {
        str(item["name"]): item
        for item in sa.inspect(bind).get_indexes(_BATCH_TABLE)
        if item.get("name") and not item.get("duplicates_constraint")
    }
    current = indexes.get(_BATCH_INDEX)
    if set(indexes) - {_BATCH_INDEX}:
        raise RuntimeError(f"{_BATCH_TABLE} has unexpected indexes: {sorted(indexes)}")
    if current is None:
        op.create_index(
            _BATCH_INDEX,
            _BATCH_TABLE,
            ["mission_id", "created_at"],
            unique=False,
        )
        return
    _validate_plain_index(current, ("mission_id", "created_at"))


def _ensure_batch_table(bind: sa.engine.Connection) -> None:
    if not sa.inspect(bind).has_table(_BATCH_TABLE):
        op.create_table(
            _BATCH_TABLE,
            sa.Column("id", _uuid_type(bind), nullable=False),
            sa.Column("mission_id", _uuid_type(bind), nullable=False),
            sa.Column("deepsearch_job_id", sa.String(length=100), nullable=False),
            sa.Column("session_key", sa.String(length=255), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("entry_count", sa.Integer(), nullable=False),
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
                "length(trim(deepsearch_job_id)) > 0",
                name="ck_deepsearch_ledger_batches_nonempty_job",
            ),
            sa.CheckConstraint(
                "length(trim(session_key)) > 0",
                name="ck_deepsearch_ledger_batches_nonempty_session",
            ),
            sa.CheckConstraint(
                "length(payload_hash) = 64",
                name="ck_deepsearch_ledger_batches_hash_length",
            ),
            sa.CheckConstraint(
                "entry_count > 0 AND entry_count <= 1000",
                name="ck_deepsearch_ledger_batches_entry_count",
            ),
            sa.ForeignKeyConstraint(
                ["mission_id"],
                ["missions.id"],
                name=_BATCH_MISSION_FK,
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "mission_id",
                "deepsearch_job_id",
                name=_BATCH_IDENTITY,
            ),
        )
    _validate_batch_columns(bind)
    _validate_batch_constraints(bind)
    _ensure_batch_index(bind)


def _validate_outbox_columns(bind: sa.engine.Connection) -> None:
    columns = _column_map(bind, _OUTBOX_TABLE)
    if set(columns) != _OUTBOX_COLUMNS:
        raise RuntimeError(f"{_OUTBOX_TABLE} has incompatible columns: actual={sorted(columns)}")

    for name in ("mission_id", "lease_token"):
        if not _is_uuid_type(bind, columns[name]["type"]):
            raise RuntimeError(f"{_OUTBOX_TABLE}.{name} has incompatible type")
    expected_strings = {
        "deepsearch_job_id": 100,
        "terminal_status": 32,
        "state": 16,
        "last_error_code": 100,
    }
    for name, length in expected_strings.items():
        value = columns[name]["type"]
        if not isinstance(value, sa.String) or value.length != length:
            raise RuntimeError(f"{_OUTBOX_TABLE}.{name} has incompatible type")
    if not isinstance(columns["deepsearch_result_key"]["type"], sa.Text):
        raise RuntimeError(f"{_OUTBOX_TABLE}.deepsearch_result_key has incompatible type")
    for name in ("mission_attempt_count", "delivery_attempt_count"):
        value = columns[name]["type"]
        if not isinstance(value, sa.Integer) or isinstance(value, sa.SmallInteger):
            raise RuntimeError(f"{_OUTBOX_TABLE}.{name} has incompatible type")
    for name in ("schema_version", "last_http_status"):
        if not isinstance(columns[name]["type"], sa.SmallInteger):
            raise RuntimeError(f"{_OUTBOX_TABLE}.{name} has incompatible type")
    for name in (
        "next_attempt_at",
        "lease_expires_at",
        "acked_at",
        "created_at",
        "updated_at",
    ):
        value = columns[name]["type"]
        if not isinstance(value, sa.DateTime):
            raise RuntimeError(f"{_OUTBOX_TABLE}.{name} has incompatible type")
        if bind.dialect.name == "postgresql" and not bool(value.timezone):
            raise RuntimeError(f"{_OUTBOX_TABLE}.{name} must preserve timezone information")

    nullable_columns = {
        "lease_token",
        "lease_expires_at",
        "acked_at",
        "last_http_status",
        "last_error_code",
    }
    actual_nullable = {name for name, column in columns.items() if bool(column["nullable"])}
    if actual_nullable != nullable_columns:
        raise RuntimeError(f"{_OUTBOX_TABLE} has incompatible nullability: actual={sorted(actual_nullable)}")

    expected_defaults: dict[str, set[str]] = {
        "schema_version": {"1"},
        "state": {"'pending'"},
        "delivery_attempt_count": {"0"},
        "next_attempt_at": {"now", "current_timestamp"},
        "created_at": {"now", "current_timestamp"},
        "updated_at": {"now", "current_timestamp"},
    }
    for name, column in columns.items():
        actual_default = _normalize_default(column.get("default"))
        allowed = expected_defaults.get(name)
        if allowed is None:
            if actual_default is not None:
                raise RuntimeError(f"{_OUTBOX_TABLE}.{name} has an unexpected server default")
        elif actual_default not in allowed:
            raise RuntimeError(f"{_OUTBOX_TABLE}.{name} has an incompatible server default")


def _validate_outbox_constraints(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    primary_key = inspector.get_pk_constraint(_OUTBOX_TABLE)
    primary_key_columns = tuple(str(value) for value in primary_key.get("constrained_columns", ()))
    if primary_key_columns != ("mission_id", "deepsearch_job_id") or primary_key.get("name") != _OUTBOX_PK:
        raise RuntimeError(f"{_OUTBOX_TABLE} has an incompatible primary key")

    uniques = inspector.get_unique_constraints(_OUTBOX_TABLE)
    if uniques:
        raise RuntimeError(f"{_OUTBOX_TABLE} has unexpected unique constraints: {uniques}")

    checks = {
        str(item["name"]): _normalize_check(str(item.get("sqltext") or ""))
        for item in inspector.get_check_constraints(_OUTBOX_TABLE)
        if item.get("name")
    }
    expected_checks = {name: _normalize_check(sql) for name, sql in _OUTBOX_CHECK_SQL.items()}
    if checks != expected_checks:
        raise RuntimeError(f"{_OUTBOX_TABLE} has incompatible check constraints: {checks}")

    foreign_keys = inspector.get_foreign_keys(_OUTBOX_TABLE)
    if len(foreign_keys) != 1:
        raise RuntimeError(f"{_OUTBOX_TABLE} has incompatible foreign keys")
    foreign_key = foreign_keys[0]
    if (
        foreign_key.get("name") != _OUTBOX_MISSION_FK
        or foreign_key.get("constrained_columns") != ["mission_id"]
        or foreign_key.get("referred_table") != "missions"
        or foreign_key.get("referred_columns") != ["id"]
        or str((foreign_key.get("options") or {}).get("ondelete") or "").upper() != "CASCADE"
    ):
        raise RuntimeError(f"{_OUTBOX_TABLE} has incompatible mission foreign key")


def _ensure_outbox_index(bind: sa.engine.Connection) -> None:
    indexes = {
        str(item["name"]): item
        for item in sa.inspect(bind).get_indexes(_OUTBOX_TABLE)
        if item.get("name") and not item.get("duplicates_constraint")
    }
    current = indexes.get(_OUTBOX_INDEX)
    if current is None:
        op.create_index(
            _OUTBOX_INDEX,
            _OUTBOX_TABLE,
            ["state", "next_attempt_at", "created_at"],
            unique=False,
        )
        return
    _validate_plain_index(current, ("state", "next_attempt_at", "created_at"))
    if set(indexes) != {_OUTBOX_INDEX}:
        raise RuntimeError(f"{_OUTBOX_TABLE} has unexpected indexes: {sorted(indexes)}")


def _ensure_outbox_table(bind: sa.engine.Connection) -> None:
    if sa.inspect(bind).has_table(_OUTBOX_TABLE):
        raise RuntimeError(f"{_OUTBOX_TABLE} already exists; migration 043 must own its DDL")
    op.create_table(
        _OUTBOX_TABLE,
        sa.Column("mission_id", _uuid_type(bind), nullable=False),
        sa.Column(
            "deepsearch_job_id",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column("deepsearch_result_key", sa.Text(), nullable=False),
        sa.Column("mission_attempt_count", sa.Integer(), nullable=False),
        sa.Column("terminal_status", sa.String(length=32), nullable=False),
        sa.Column(
            "schema_version",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "delivery_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lease_token", _uuid_type(bind), nullable=True),
        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "acked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_http_status", sa.SmallInteger(), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        *(sa.CheckConstraint(sql, name=name) for name, sql in _OUTBOX_CHECK_SQL.items()),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["missions.id"],
            name=_OUTBOX_MISSION_FK,
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "mission_id",
            "deepsearch_job_id",
            name=_OUTBOX_PK,
        ),
    )
    _validate_outbox_columns(bind)
    _validate_outbox_constraints(bind)
    _ensure_outbox_index(bind)


def _entry_batch_foreign_keys(bind: sa.engine.Connection) -> list[dict]:
    return [
        item
        for item in sa.inspect(bind).get_foreign_keys("ledger_entries")
        if "deepsearch_batch_id" in item.get("constrained_columns", ())
    ]


def _ensure_entry_batch_link(bind: sa.engine.Connection) -> None:
    columns = _column_map(bind, "ledger_entries")
    has_column = "deepsearch_batch_id" in columns
    foreign_keys = _entry_batch_foreign_keys(bind) if has_column else []

    if bind.dialect.name == "sqlite" and (not has_column or not foreign_keys):
        with op.batch_alter_table("ledger_entries") as batch_op:
            if not has_column:
                batch_op.add_column(
                    sa.Column(
                        "deepsearch_batch_id",
                        _uuid_type(bind),
                        nullable=True,
                    )
                )
            if not foreign_keys:
                batch_op.create_foreign_key(
                    _ENTRY_BATCH_FK,
                    _BATCH_TABLE,
                    ["deepsearch_batch_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
    else:
        if not has_column:
            op.add_column(
                "ledger_entries",
                sa.Column(
                    "deepsearch_batch_id",
                    _uuid_type(bind),
                    nullable=True,
                ),
            )
        if not foreign_keys:
            op.create_foreign_key(
                _ENTRY_BATCH_FK,
                "ledger_entries",
                _BATCH_TABLE,
                ["deepsearch_batch_id"],
                ["id"],
                ondelete="SET NULL",
            )

    columns = _column_map(bind, "ledger_entries")
    column = columns.get("deepsearch_batch_id")
    if column is None or not bool(column["nullable"]):
        raise RuntimeError("ledger_entries.deepsearch_batch_id must be nullable")
    if not _is_uuid_type(bind, column["type"]):
        raise RuntimeError("ledger_entries.deepsearch_batch_id has incompatible type")

    foreign_keys = _entry_batch_foreign_keys(bind)
    if len(foreign_keys) != 1:
        raise RuntimeError("ledger_entries.deepsearch_batch_id has incompatible foreign keys")
    foreign_key = foreign_keys[0]
    if (
        foreign_key.get("name") != _ENTRY_BATCH_FK
        or foreign_key.get("constrained_columns") != ["deepsearch_batch_id"]
        or foreign_key.get("referred_table") != _BATCH_TABLE
        or foreign_key.get("referred_columns") != ["id"]
        or str((foreign_key.get("options") or {}).get("ondelete") or "").upper() != "SET NULL"
    ):
        raise RuntimeError("ledger_entries.deepsearch_batch_id foreign key is incompatible")

    indexes = {
        str(item["name"]): item
        for item in sa.inspect(bind).get_indexes("ledger_entries")
        if item.get("name") and not item.get("duplicates_constraint")
    }
    current = indexes.get(_ENTRY_BATCH_INDEX)
    if current is None:
        op.create_index(
            _ENTRY_BATCH_INDEX,
            "ledger_entries",
            ["deepsearch_batch_id", "created_at"],
            unique=False,
        )
    else:
        _validate_plain_index(
            current,
            ("deepsearch_batch_id", "created_at"),
        )


def _refuse_populated_downgrade(bind: sa.engine.Connection) -> None:
    populated: dict[str, int] = {}
    inspector = sa.inspect(bind)
    for table_name in (_OUTBOX_TABLE, _BATCH_TABLE):
        if not inspector.has_table(table_name):
            continue
        count = int(bind.execute(sa.select(sa.func.count()).select_from(sa.table(table_name))).scalar_one())
        if count:
            populated[table_name] = count
    if populated:
        detail = ", ".join(f"{table_name}={count}" for table_name, count in populated.items())
        raise RuntimeError(f"Refusing to downgrade DeepSearch evidence ownership with durable rows present: {detail}")


def _preflight_upgrade(bind: sa.engine.Connection) -> None:
    """Reject known incompatible state before SQLite can commit any DDL."""
    inspector = sa.inspect(bind)
    if inspector.has_table(_OUTBOX_TABLE):
        raise RuntimeError(f"{_OUTBOX_TABLE} already exists; migration 043 must own its DDL")

    if inspector.has_table(_BATCH_TABLE):
        _validate_batch_columns(bind)
        _validate_batch_constraints(bind)
        indexes = {
            str(item["name"]): item
            for item in sa.inspect(bind).get_indexes(_BATCH_TABLE)
            if item.get("name") and not item.get("duplicates_constraint")
        }
        if set(indexes) - {_BATCH_INDEX}:
            raise RuntimeError(f"{_BATCH_TABLE} has unexpected indexes: {sorted(indexes)}")
        current = indexes.get(_BATCH_INDEX)
        if current is not None:
            _validate_plain_index(current, ("mission_id", "created_at"))

    if not inspector.has_table("ledger_entries"):
        raise RuntimeError("ledger_entries is missing before migration 043")
    columns = _column_map(bind, "ledger_entries")
    column = columns.get("deepsearch_batch_id")
    if column is None:
        return
    if not bool(column["nullable"]):
        raise RuntimeError("ledger_entries.deepsearch_batch_id must be nullable")
    if not _is_uuid_type(bind, column["type"]):
        raise RuntimeError("ledger_entries.deepsearch_batch_id has incompatible type")
    foreign_keys = _entry_batch_foreign_keys(bind)
    if len(foreign_keys) > 1:
        raise RuntimeError("ledger_entries.deepsearch_batch_id has incompatible foreign keys")
    if foreign_keys:
        foreign_key = foreign_keys[0]
        if (
            foreign_key.get("name") != _ENTRY_BATCH_FK
            or foreign_key.get("constrained_columns") != ["deepsearch_batch_id"]
            or foreign_key.get("referred_table") != _BATCH_TABLE
            or foreign_key.get("referred_columns") != ["id"]
            or str((foreign_key.get("options") or {}).get("ondelete") or "").upper() != "SET NULL"
        ):
            raise RuntimeError("ledger_entries.deepsearch_batch_id foreign key is incompatible")
    indexes = {
        str(item["name"]): item
        for item in sa.inspect(bind).get_indexes("ledger_entries")
        if item.get("name") and not item.get("duplicates_constraint")
    }
    current = indexes.get(_ENTRY_BATCH_INDEX)
    if current is not None:
        _validate_plain_index(
            current,
            ("deepsearch_batch_id", "created_at"),
        )


def upgrade() -> None:
    bind = op.get_bind()
    _preflight_upgrade(bind)
    _ensure_batch_table(bind)
    _ensure_outbox_table(bind)
    _ensure_entry_batch_link(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _refuse_populated_downgrade(bind)
    if sa.inspect(bind).has_table(_OUTBOX_TABLE):
        op.drop_table(_OUTBOX_TABLE)
    if sa.inspect(bind).has_table("ledger_entries"):
        columns = _column_map(bind, "ledger_entries")
        if "deepsearch_batch_id" in columns:
            if bind.dialect.name == "sqlite":
                foreign_keys = _entry_batch_foreign_keys(bind)
                foreign_key_name = (
                    str(foreign_keys[0].get("name"))
                    if foreign_keys and foreign_keys[0].get("name")
                    else "fk_ledger_entries_deepsearch_batch_id_deepsearch_ledger_batches"
                )
                with op.batch_alter_table(
                    "ledger_entries",
                    naming_convention=_SQLITE_FK_NAMING_CONVENTION,
                ) as batch_op:
                    batch_op.drop_index(_ENTRY_BATCH_INDEX)
                    batch_op.drop_constraint(
                        foreign_key_name,
                        type_="foreignkey",
                    )
                    batch_op.drop_column("deepsearch_batch_id")
            else:
                indexes = {item.get("name") for item in sa.inspect(bind).get_indexes("ledger_entries")}
                if _ENTRY_BATCH_INDEX in indexes:
                    op.drop_index(_ENTRY_BATCH_INDEX, table_name="ledger_entries")
                foreign_keys = _entry_batch_foreign_keys(bind)
                if foreign_keys:
                    op.drop_constraint(
                        str(foreign_keys[0].get("name") or _ENTRY_BATCH_FK),
                        "ledger_entries",
                        type_="foreignkey",
                    )
                op.drop_column("ledger_entries", "deepsearch_batch_id")
    if sa.inspect(bind).has_table(_BATCH_TABLE):
        op.drop_table(_BATCH_TABLE)
