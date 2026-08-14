"""Add the canonical DeepSearch fenced-lease boundary to missions.

DeepSearch's worker already refuses to poll unless these seven columns exist
with the exact PostgreSQL types below. Production may have received equivalent
objects out of band while the repositories drifted, so this migration converges
an already-compatible schema instead of assuming every object is absent. It
never overwrites an active lease or a terminal result key.

The revision id stays below 32 characters because the deployed
``alembic_version.version_num`` is ``VARCHAR(32)``.

Revision ID: 039_deepsearch_lease_v1
Revises: 038_backfill_mission_report
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "039_deepsearch_lease_v1"
down_revision = "038_backfill_mission_report"
branch_labels = None
depends_on = None

_TEXT_COLUMNS = (
    "deepsearch_lease_owner",
    "deepsearch_lease_token",
    "deepsearch_result_key",
)
_TIMESTAMP_COLUMNS = (
    "deepsearch_leased_at",
    "deepsearch_heartbeat_at",
    "deepsearch_lease_expires_at",
)
_INDEXES: tuple[tuple[str, tuple[str, ...], bool, str | None], ...] = (
    (
        "missions_deepsearch_lease_token_active_uq",
        ("deepsearch_lease_token",),
        True,
        "deepsearch_lease_token IS NOT NULL",
    ),
    (
        "missions_deepsearch_result_key_uq",
        ("deepsearch_result_key",),
        True,
        "deepsearch_result_key IS NOT NULL",
    ),
    (
        "missions_deepsearch_claim_scan_idx",
        (
            "status",
            "deepsearch_lease_expires_at",
            "queued_at",
        ),
        False,
        None,
    ),
)


def _columns(bind: sa.engine.Connection) -> dict[str, dict]:
    return {
        str(column["name"]): column
        for column in sa.inspect(bind).get_columns("missions")
    }


def _ensure_text_columns(bind: sa.engine.Connection) -> None:
    columns = _columns(bind)
    for name in _TEXT_COLUMNS:
        existing = columns.get(name)
        if existing is None:
            op.add_column("missions", sa.Column(name, sa.Text(), nullable=True))
            continue
        existing_type = existing["type"]
        if isinstance(existing_type, sa.String):
            # VARCHAR -> TEXT is widening. Nullable is part of the worker
            # contract because terminal writes clear lease proofs to NULL.
            if isinstance(existing_type, sa.Text) and existing.get("nullable", True):
                continue
            op.alter_column(
                "missions",
                name,
                existing_type=existing_type,
                type_=sa.Text(),
                existing_nullable=bool(existing.get("nullable", True)),
                nullable=True,
            )
            continue
        raise RuntimeError(
            f"missions.{name} has incompatible type {existing_type}; expected text"
        )


def _ensure_timestamp_columns(bind: sa.engine.Connection) -> None:
    columns = _columns(bind)
    for name in _TIMESTAMP_COLUMNS:
        existing = columns.get(name)
        if existing is None:
            op.add_column(
                "missions",
                sa.Column(name, sa.DateTime(timezone=True), nullable=True),
            )
            continue
        existing_type = existing["type"]
        if not isinstance(existing_type, sa.DateTime):
            raise RuntimeError(
                f"missions.{name} has incompatible type {existing_type}; "
                "expected timestamp with time zone"
            )
        if not existing_type.timezone or not existing.get("nullable", True):
            # A manually-added naive timestamp is interpreted as UTC during the
            # widening conversion. This is deterministic and keeps fencing
            # comparisons aligned with PostgreSQL NOW().
            alter_kwargs: dict[str, object] = {
                "existing_type": existing_type,
                "type_": sa.DateTime(timezone=True),
                "existing_nullable": bool(existing.get("nullable", True)),
                "nullable": True,
            }
            if not existing_type.timezone:
                alter_kwargs["postgresql_using"] = f"{name} AT TIME ZONE 'UTC'"
            op.alter_column(
                "missions",
                name,
                **alter_kwargs,
            )


def _ensure_attempt_count(bind: sa.engine.Connection) -> None:
    existing = _columns(bind).get("deepsearch_attempt_count")
    if existing is None:
        op.add_column(
            "missions",
            sa.Column(
                "deepsearch_attempt_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
        return

    existing_type = existing["type"]
    if not isinstance(existing_type, sa.Integer):
        raise RuntimeError(
            "missions.deepsearch_attempt_count has incompatible type "
            f"{existing_type}; expected integer"
        )

    # Converge a manually-ahead nullable/default-less column without resetting
    # any real attempt count. PostgreSQL SMALLINT/BIGINT share SQLAlchemy's
    # Integer type affinity, but the worker preflight requires exact `integer`.
    bind.execute(
        sa.text(
            "UPDATE missions SET deepsearch_attempt_count = 0 "
            "WHERE deepsearch_attempt_count IS NULL"
        )
    )
    alter_kwargs: dict[str, object] = {
        "existing_type": existing_type,
        "nullable": False,
        "server_default": sa.text("0"),
    }
    if type(existing_type) not in {sa.Integer, sa.INTEGER}:
        alter_kwargs["type_"] = sa.Integer()
        alter_kwargs["postgresql_using"] = "deepsearch_attempt_count::integer"
    op.alter_column("missions", "deepsearch_attempt_count", **alter_kwargs)


def _ensure_indexes(bind: sa.engine.Connection) -> None:
    def normalize_predicate(value: object | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).strip().lower().split()).replace('"', "")
        while normalized.startswith("(") and normalized.endswith(")"):
            normalized = normalized[1:-1].strip()
        return normalized

    existing = {
        str(index["name"]): index
        for index in sa.inspect(bind).get_indexes("missions")
        if index.get("name")
    }
    for name, columns, unique, predicate in _INDEXES:
        current = existing.get(name)
        if current is not None:
            current_columns = tuple(str(value) for value in current["column_names"])
            if current_columns != columns or bool(current.get("unique")) != unique:
                raise RuntimeError(
                    f"Index {name} exists with an incompatible definition: "
                    f"columns={current_columns}, unique={current.get('unique')}"
                )
            dialect_options = current.get("dialect_options") or {}
            current_predicate = normalize_predicate(
                dialect_options.get("postgresql_where")
            )
            expected_predicate = normalize_predicate(predicate)
            if current_predicate != expected_predicate:
                op.drop_index(name, table_name="missions")
                op.create_index(
                    name,
                    "missions",
                    list(columns),
                    unique=unique,
                    postgresql_where=(
                        sa.text(predicate) if predicate is not None else None
                    ),
                )
            continue
        op.create_index(
            name,
            "missions",
            list(columns),
            unique=unique,
            postgresql_where=sa.text(predicate) if predicate else None,
        )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_text_columns(bind)
    _ensure_timestamp_columns(bind)
    _ensure_attempt_count(bind)
    _ensure_indexes(bind)

    # Pre-lease in-progress rows have no fencing token. Once old workers are
    # drained, making those rows immediately expired lets lease-v2 recover them
    # instead of leaving them stranded forever. Active token-bound leases and
    # every result key are preserved byte-for-byte.
    bind.execute(
        sa.text(
            """
            UPDATE missions
            SET deepsearch_lease_expires_at = CURRENT_TIMESTAMP,
                deepsearch_heartbeat_at = COALESCE(
                    deepsearch_heartbeat_at, CURRENT_TIMESTAMP
                )
            WHERE status = 'in_progress'
              AND deepsearch_lease_token IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind)
    present = [
        name
        for name in (*_TEXT_COLUMNS, *_TIMESTAMP_COLUMNS, "deepsearch_attempt_count")
        if name in columns
    ]
    if not present:
        return

    populated = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM missions
            WHERE deepsearch_lease_owner IS NOT NULL
               OR deepsearch_lease_token IS NOT NULL
               OR deepsearch_leased_at IS NOT NULL
               OR deepsearch_heartbeat_at IS NOT NULL
               OR deepsearch_lease_expires_at IS NOT NULL
               OR deepsearch_attempt_count <> 0
               OR deepsearch_result_key IS NOT NULL
            """
        )
    ).scalar()
    if populated:
        raise RuntimeError(
            "Cannot downgrade 039: missions contain lease or result-key state"
        )

    existing_indexes = {
        str(index["name"])
        for index in sa.inspect(bind).get_indexes("missions")
        if index.get("name")
    }
    for name, _, _, _ in reversed(_INDEXES):
        if name in existing_indexes:
            op.drop_index(name, table_name="missions")
    for name in (
        "deepsearch_result_key",
        "deepsearch_attempt_count",
        "deepsearch_lease_expires_at",
        "deepsearch_heartbeat_at",
        "deepsearch_leased_at",
        "deepsearch_lease_token",
        "deepsearch_lease_owner",
    ):
        if name in columns:
            op.drop_column("missions", name)
