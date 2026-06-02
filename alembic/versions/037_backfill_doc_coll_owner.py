"""Backfill document/collection ownership minted NULL since 031 (Sprint 48 T48.4).

Migration 031 backfilled every existing row, but until T48.4 the document create
sites (upload, DeepSearch auto-ingest, report promotion, onboarding) and
POST /collections minted rows with NULL owner_id/workspace_id. Those create paths
now attribute owner/Space, but rows created in the gap are still NULL and would be
invisible to non-admins the instant rbac_enabled flips. This idempotently backfills
the two affected tables to the bootstrap owner + the seeded Default Workspace,
exactly as migration 031 did for the original rows.

ZERO behavioral effect while rbac_enabled is OFF.

NOTE: the revision id is kept <=32 chars because alembic_version.version_num is
VARCHAR(32) — the original long id (042 chars) overflowed it, which would have
failed `alembic upgrade head` on deploy (caught by the T48.4 cleanup, T48.9).

Revision ID: 037_backfill_doc_coll_owner
Revises: 036_drop_metadata_table
Create Date: 2026-06-02
"""

from __future__ import annotations

import os
import uuid

from sqlalchemy import text

from alembic import op

revision = "037_backfill_doc_coll_owner"
down_revision = "036_drop_metadata_table"
branch_labels = None
depends_on = None

# Matches the fixed seed workspace created in migration 030 (and reused by 031).
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

# The owned tables whose CREATE paths T48.4 fixed — a subset of migration 031's 5.
_TABLES = ("documents", "collections")


def _bootstrap_owner_email() -> str:
    # Read AUTH_USERNAME from the environment directly (NOT pydantic settings),
    # mirroring migrations 023/031 so we resolve the same email the seed used.
    username = os.environ.get("AUTH_USERNAME", "tracelab-admin")
    return username if "@" in username else f"{username}@tracelab.local"


def upgrade() -> None:
    bind = op.get_bind()

    # Resolve the bootstrap owner: by unique email, else the earliest-created user.
    owner_id = bind.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {"email": _bootstrap_owner_email()},
    ).scalar()
    if owner_id is None:
        owner_id = bind.execute(
            text("SELECT id FROM users ORDER BY created_at ASC, id ASC LIMIT 1")
        ).scalar()
    if owner_id is None:
        # No users at all: nothing to own. owner_id/workspace_id are nullable
        # (migration 030), so leaving any rows NULL is schema-safe.
        return

    workspace_id = uuid.UUID(DEFAULT_WORKSPACE_ID)
    for table in _TABLES:
        # Table names come from a fixed literal allowlist, not user input.
        bind.execute(
            text(f"UPDATE {table} SET owner_id = :owner_id WHERE owner_id IS NULL"),  # noqa: S608
            {"owner_id": owner_id},
        )
        bind.execute(
            text(f"UPDATE {table} SET workspace_id = :ws WHERE workspace_id IS NULL"),  # noqa: S608
            {"ws": workspace_id},
        )

    # Success criterion: 0 rows with NULL owner_id/workspace_id after backfill.
    for table in _TABLES:
        nulls = bind.execute(
            text(f"SELECT count(*) FROM {table} WHERE owner_id IS NULL OR workspace_id IS NULL")  # noqa: S608
        ).scalar()
        if nulls:
            raise RuntimeError(
                f"Backfill incomplete: {nulls} row(s) in {table} still have NULL "
                "owner_id/workspace_id after migration 037"
            )


def downgrade() -> None:
    # No-op by design: this migration only FILLS rows that were NULL, and there is
    # no marker distinguishing rows it filled from rows that 031 (or a later
    # assignment) set. A blanket NULL would clobber legitimate ownership, so the
    # safe inverse is to leave the data in place — 036 is unrelated to ownership.
    pass
