"""Backfill ownership + bootstrap owner (Sprint 43 T43.3).

Populates the additive columns added in migration 030 for all existing rows and
guarantees an owner exists:
- resolve the bootstrap owner (Derek / AUTH_USERNAME) by unique email, falling
  back to the earliest-created user; skip entirely if there are no users;
- backfill owner_id = bootstrap owner and workspace_id = the seeded Default
  Workspace on every existing row (WHERE ... IS NULL — idempotent) of the 5
  owned tables;
- promote the bootstrap user to role='owner';
- assert 0 NULL owner_id/workspace_id remain.

ZERO behavioral effect today (role is unenforced in Sprint 43). The free-text
created_by audit columns are untouched.

Revision ID: 031_backfill_ownership
Revises: 030_add_owner_workspace_columns
Create Date: 2026-05-29
"""

from __future__ import annotations

import os
import uuid

from sqlalchemy import text

from alembic import op

revision = "031_backfill_ownership"
down_revision = "030_add_owner_workspace_columns"
branch_labels = None
depends_on = None

# Matches the fixed seed workspace created in migration 030.
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

# The 5 tables that gained owner_id/workspace_id in migration 030.
_OWNED_TABLES = ("projects", "collections", "missions", "reports", "documents")


def _bootstrap_owner_email() -> str:
    # Read AUTH_USERNAME from the environment directly (NOT pydantic settings),
    # mirroring migration 023's seed, so we compute the same email the seed used.
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
        # Deterministic fallback (id breaks any created_at tie).
        owner_id = bind.execute(text("SELECT id FROM users ORDER BY created_at ASC, id ASC LIMIT 1")).scalar()
    if owner_id is None:
        # No users at all: nothing to own. The 5 owner/workspace columns are
        # nullable (migration 030), so leaving any rows NULL is schema-safe.
        return

    workspace_id = uuid.UUID(DEFAULT_WORKSPACE_ID)
    for table in _OWNED_TABLES:
        # Table names come from a fixed literal allowlist, not user input.
        bind.execute(
            text(f"UPDATE {table} SET owner_id = :owner_id WHERE owner_id IS NULL"),  # noqa: S608
            {"owner_id": owner_id},
        )
        bind.execute(
            text(f"UPDATE {table} SET workspace_id = :ws WHERE workspace_id IS NULL"),  # noqa: S608
            {"ws": workspace_id},
        )

    # Promote the bootstrap user to owner (idempotent).
    bind.execute(
        text("UPDATE users SET role = 'owner' WHERE id = :id AND role <> 'owner'"),
        {"id": owner_id},
    )

    # Success criterion: 0 rows with NULL owner_id/workspace_id after backfill.
    for table in _OWNED_TABLES:
        nulls = bind.execute(
            text(f"SELECT count(*) FROM {table} WHERE owner_id IS NULL OR workspace_id IS NULL")  # noqa: S608
        ).scalar()
        if nulls:
            raise RuntimeError(
                f"Backfill incomplete: {nulls} row(s) in {table} still have NULL "
                "owner_id/workspace_id after migration 031"
            )


def downgrade() -> None:
    bind = op.get_bind()
    # Blanket revert to the post-030 / pre-031 state: null ALL ownership and demote
    # ALL owners back to 'admin'. This is a precise undo on a migrate-up-then-down
    # chain (pre-031 there were zero owners and all ownership was NULL). NOTE: it is
    # intentionally a blanket revert, not a surgical undo of only 031's writes — if
    # later sprints let operators assign additional owners / write ownership before a
    # downgrade, revisit to scope this more tightly.
    for table in _OWNED_TABLES:
        bind.execute(text(f"UPDATE {table} SET owner_id = NULL, workspace_id = NULL"))  # noqa: S608
    bind.execute(text("UPDATE users SET role = 'admin' WHERE role = 'owner'"))
