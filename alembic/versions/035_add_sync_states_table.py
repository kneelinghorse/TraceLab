"""Create sync_states table to match the SyncState ORM model.

T45.1 (sprint-45, Infra Hardening) — sync_states is the one ORM model table with
no Alembic migration. It exists in environments only via the dev-gated
``Base.metadata.create_all`` (app/main.py:87), so an alembic-only database (CI /
test / a future fresh prod) never gets it and ``app.services.pedr.delta_sync``
(SyncState read/upsert) would fail. This migration makes the table reproducible
from migrations alone.

IDEMPOTENT BY DESIGN: the create is guarded by ``has_table`` so it is a safe
no-op where the table already exists (e.g. a database where the dev-gated
create_all already provisioned it) and a real create on a fresh DB. Without the
guard this would raise DuplicateTable on such a database — the exact failure
mode that crash-looped prod on the workspaces migration (learning #90), the
incident class this whole sprint exists to close.

Column shape mirrors SyncState (app/models/sync_state.py): the model's GUID id
maps to native ``UUID`` on PostgreSQL (app/models/types.GUID), consistent with
the sa.UUID() id columns in migrations 030/033/034. The model's client-side
defaults (uuid4 id, sync_count=0, utcnow timestamps) are NOT server defaults, so
none are emitted here — matching what create_all produces.

Revision ID: 035_add_sync_states_table
Revises: 034_add_project_tags
Create Date: 2026-05-29
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "035_add_sync_states_table"
down_revision = "034_add_project_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard: skip the create where sync_states already exists (provisioned out of
    # band by the dev-gated create_all). A naive create_table would raise
    # DuplicateTable there — the workspaces incident (learning #90). No-op +
    # version bump is the correct outcome on such a database.
    if sa.inspect(op.get_bind()).has_table("sync_states"):
        return
    op.create_table(
        "sync_states",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("sync_count", sa.Integer(), nullable=True),
        sa.Column("last_entity_id", sa.String(length=255), nullable=True),
        sa.Column("sync_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        # One sync cursor per entity type (mission | document | insight). Name
        # matches the SyncState model's UniqueConstraint exactly.
        sa.UniqueConstraint("entity_type", name="uq_sync_state_entity_type"),
    )


def downgrade() -> None:
    # Guarded drop so downgrade is also a safe no-op where the table is absent.
    if sa.inspect(op.get_bind()).has_table("sync_states"):
        op.drop_table("sync_states")
