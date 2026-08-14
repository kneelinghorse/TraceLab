"""Backfill mission/report ownership from parent projects (Sprint 48 T48.8).

Mission and automatic-report create paths continued minting NULL ownership after
migration 031. New project children now inherit their parent attribution; this
migration converges gap-era rows without overwriting any explicit owner/Space.

Revision ID: 038_backfill_mission_report
Revises: 037_backfill_doc_coll_owner
Create Date: 2026-08-14
"""

from __future__ import annotations

import os
import uuid

from sqlalchemy import text

from alembic import op

revision = "038_backfill_mission_report"
down_revision = "037_backfill_doc_coll_owner"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_TABLES = ("missions", "reports")


def _bootstrap_owner_email() -> str:
    username = os.environ.get("AUTH_USERNAME", "tracelab-admin")
    return username if "@" in username else f"{username}@tracelab.local"


def upgrade() -> None:
    bind = op.get_bind()
    owner_id = bind.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {"email": _bootstrap_owner_email()},
    ).scalar()
    if owner_id is None:
        owner_id = bind.execute(
            text("SELECT id FROM users ORDER BY created_at ASC, id ASC LIMIT 1")
        ).scalar()
    if owner_id is None:
        # With no user, assigning ownership would invent an invalid principal.
        return

    workspace_id = uuid.UUID(DEFAULT_WORKSPACE_ID)
    for table in _TABLES:
        # Prefer the resource's parent project. COALESCE preserves either half of
        # an existing explicit attribution and makes this safe to run repeatedly.
        bind.execute(
            text(
                f"UPDATE {table} AS resource "  # noqa: S608
                "SET owner_id = COALESCE(resource.owner_id, parent.owner_id), "
                "workspace_id = COALESCE(resource.workspace_id, parent.workspace_id) "
                "FROM projects AS parent "
                "WHERE resource.project_id = parent.id "
                "AND (resource.owner_id IS NULL OR resource.workspace_id IS NULL)"
            )
        )
        # Old project-less rows, or children of a legacy unattributed project,
        # fall back exactly as the 031/037 ownership migrations did.
        bind.execute(
            text(f"UPDATE {table} SET owner_id = :owner_id WHERE owner_id IS NULL"),  # noqa: S608
            {"owner_id": owner_id},
        )
        bind.execute(
            text(
                f"UPDATE {table} SET workspace_id = :workspace_id "  # noqa: S608
                "WHERE workspace_id IS NULL"
            ),
            {"workspace_id": workspace_id},
        )

    for table in _TABLES:
        nulls = bind.execute(
            text(
                f"SELECT count(*) FROM {table} "  # noqa: S608
                "WHERE owner_id IS NULL OR workspace_id IS NULL"
            )
        ).scalar()
        if nulls:
            raise RuntimeError(
                f"Backfill incomplete: {nulls} row(s) in {table} still have NULL "
                "owner_id/workspace_id after migration 038"
            )


def downgrade() -> None:
    # Attribution cannot be distinguished from later legitimate assignments;
    # clearing it on downgrade would be destructive.
    pass
