"""Up/down + guard tests for migration 036_drop_metadata_table (T45.3).

The ``metadata`` table is migration-only cruft from 001 (decision #243). 036
drops it. Three properties matter, each tied to a concrete failure mode:

1. Round-trip — upgrade drops the table, downgrade recreates it with the exact
   001 column shape, re-upgrade drops it again. Proves the drop is reversible at
   the schema level and the revision boundary is repeatable.

2. Drop guard (success criterion) — on a database where ``metadata`` is already
   gone, the upgrade must be a clean no-op, not a "table does not exist" error.
   A bare ``DROP TABLE`` (no IF EXISTS) would raise; this test would fail loudly
   if the has_table guard were ever removed.

3. Recreate guard (symmetric to 035's defensive posture, learning #90) — on a
   database that somehow still has ``metadata``, the downgrade must no-op the
   recreate rather than raise DuplicateTable.

Shared fixtures: conftest.py (alembic_cfg resets the schema per test).
"""

from __future__ import annotations

import pytest
from sqlalchemy import JSON, create_engine, inspect, text

from alembic import command

pytestmark = pytest.mark.integration

REV_035 = "035_add_sync_states_table"
REV_036 = "036_drop_metadata_table"

# The exact column set migration 001 declared for `metadata`.
EXPECTED_COLUMNS = {"key", "value", "updated_at"}

# DDL matching 001's create_table, used to simulate the table existing out of
# band (the onupdate=now() in 001 is a SQLAlchemy-level hook that emits no DDL,
# so the on-disk shape is just a now() server default on updated_at).
_METADATA_DDL = (
    'CREATE TABLE "metadata" ('
    "key VARCHAR PRIMARY KEY, "
    "value JSON NOT NULL, "
    "updated_at TIMESTAMP DEFAULT now()"
    ")"
)


class TestDropMetadataMigration:
    def test_upgrade_drops_then_downgrade_recreates_then_reupgrade(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            # --- upgrade the full chain to 036: metadata must be gone ---
            command.upgrade(alembic_cfg, REV_036)
            assert "metadata" not in set(inspect(engine).get_table_names()), (
                "036 upgrade must drop the orphan metadata table"
            )

            # --- downgrade to 035 must recreate it matching the 001 definition ---
            command.downgrade(alembic_cfg, REV_035)
            insp = inspect(engine)
            assert "metadata" in set(insp.get_table_names()), (
                "036 downgrade must recreate the metadata table"
            )

            cols = {c["name"] for c in insp.get_columns("metadata")}
            assert cols == EXPECTED_COLUMNS

            # `key` is the single-column primary key (001 parity).
            pk = insp.get_pk_constraint("metadata")
            assert pk["constrained_columns"] == ["key"]

            # `value` is NOT NULL (001 parity); `key` (PK) is implicitly NOT NULL.
            not_null = {
                c["name"] for c in insp.get_columns("metadata") if not c["nullable"]
            }
            assert {"key", "value"}.issubset(not_null)

            # 001 parity BEYOND names: the migration docstring promises the EXACT 001
            # shape (value JSON, updated_at with a now() default). Pin both — a name/
            # PK/not-null check alone would pass even if a downgrade edit swapped the
            # type or dropped the server default, silently breaking faithfulness.
            cols_by_name = {c["name"]: c for c in insp.get_columns("metadata")}
            assert isinstance(cols_by_name["value"]["type"], JSON), (
                f"value must reflect as JSON (001 parity), got {cols_by_name['value']['type']!r}"
            )
            updated_default = cols_by_name["updated_at"]["default"]
            assert updated_default is not None and "now" in str(updated_default).lower(), (
                f"updated_at must keep its now() server default (001 parity), got {updated_default!r}"
            )

            # --- re-upgrade proves the chain is repeatable and drops it again ---
            command.upgrade(alembic_cfg, REV_036)
            assert "metadata" not in set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

    def test_upgrade_guard_noops_when_table_absent(self, alembic_cfg, migration_db_url):
        """The drop must be a clean no-op where metadata is already gone.

        Reach rev 035 (where 001 has created metadata), drop the table out of band,
        then upgrade to 036. 036 must NOT raise "table does not exist" — it must
        detect the absence and no-op while still advancing the version to 036.
        """
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_035)
            assert "metadata" in set(inspect(engine).get_table_names())

            with engine.begin() as conn:
                conn.execute(text('DROP TABLE "metadata"'))
            assert "metadata" not in set(inspect(engine).get_table_names())

            # The guarded upgrade must be a clean no-op, not an error.
            command.upgrade(alembic_cfg, REV_036)

            assert "metadata" not in set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                version = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
            assert version == REV_036, (
                "036 must stamp the version even when its drop no-ops on an absent table"
            )
        finally:
            engine.dispose()

    def test_downgrade_guard_noops_when_table_exists(self, alembic_cfg, migration_db_url):
        """The recreate must be a clean no-op where metadata already exists.

        Reach revision 036 (metadata dropped), recreate the table out of band, then
        downgrade to 035. 036's downgrade must NOT raise DuplicateTable — it must
        detect the table and no-op while still moving the version back to 035.
        """
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_036)
            assert "metadata" not in set(inspect(engine).get_table_names())

            with engine.begin() as conn:
                conn.execute(text(_METADATA_DDL))
            assert "metadata" in set(inspect(engine).get_table_names())

            # The guarded downgrade must be a clean no-op, not DuplicateTable.
            command.downgrade(alembic_cfg, REV_035)

            assert "metadata" in set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                version = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
            assert version == REV_035, (
                "036 downgrade must stamp 035 even when its recreate no-ops"
            )
        finally:
            engine.dispose()
