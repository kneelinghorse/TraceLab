"""Drop the orphan ``metadata`` table (T45.3, sprint-45 Infra Hardening).

The ``metadata`` table was created in migration 001_initial_schema as a generic
key/value store. No ORM model maps to it: the migration-coverage audit (decision
#243) confirmed it is migration-only, ~2 stale rows of cruft, and nothing in the
app reads or writes it. Dropping it removes dead schema so the migration set
tracks the live ORM surface — the same schema-authority consolidation goal as
035 (sync_states), approached from the other side (remove the orphan rather than
add the missing migration).

Additive-reversible: downgrade recreates the table with the EXACT column shape
from migration 001 (``key`` PK, ``value`` JSON NOT NULL, ``updated_at`` with a
now() default), so the round-trip is lossless at the schema level. The ~2 stale
data rows are intentionally not restored — they carry no application meaning.

GUARDED BOTH WAYS, mirroring 035's defensive posture (learning #90 — the
``workspaces`` DuplicateTable crash-loop this sprint exists to prevent):
- upgrade drops only if the table is present, so it is a safe no-op on a database
  where the orphan was already removed out of band.
- downgrade recreates only if the table is absent, so it never raises
  DuplicateTable on a database that somehow still has it.

Revision ID: 036_drop_metadata_table
Revises: 035_add_sync_states_table
Create Date: 2026-05-30
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "036_drop_metadata_table"
down_revision = "035_add_sync_states_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded drop: safe no-op where the orphan table is already absent.
    if sa.inspect(op.get_bind()).has_table("metadata"):
        op.drop_table("metadata")


def downgrade() -> None:
    # Recreate the table exactly as migration 001 defined it. Guarded so it is a
    # no-op where the table somehow already exists (avoids DuplicateTable).
    if not sa.inspect(op.get_bind()).has_table("metadata"):
        op.create_table(
            "metadata",
            sa.Column("key", sa.String(), primary_key=True),
            sa.Column("value", sa.JSON(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
            ),
        )
