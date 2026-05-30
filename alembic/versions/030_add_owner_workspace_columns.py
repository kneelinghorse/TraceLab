"""Additive ownership + workspace columns (Sprint 43 T43.2).

Adds the ownership backbone as a purely additive, reversible migration:
- a new ``workspaces`` table seeded with one "Default Workspace" row;
- nullable ``owner_id`` (FK -> users.id) and ``workspace_id`` (FK -> workspaces.id)
  columns on projects, collections, missions, reports, documents;
- composite indexes leading (workspace_id, owner_id, <created_at|uploaded_at>).

ZERO enforcement / byte-identical day-one behavior: every new column is nullable,
no query reads them, and the free-text ``created_by`` audit columns are untouched.
FKs use ON DELETE SET NULL so deleting a user/workspace never deletes resources.

Revision ID: 030_add_owner_workspace_columns
Revises: 029_device_authorization_grants
Create Date: 2026-05-29
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision = "030_add_owner_workspace_columns"
down_revision = "029_device_authorization_grants"
branch_labels = None
depends_on = None

# Well-known id of the seeded default workspace, so the Sprint 43 backfill (T43.3)
# and any owner-bootstrap can reference it deterministically and idempotently.
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

# (table, timestamp column for the composite index). documents has no created_at;
# its creation-time column is uploaded_at.
_OWNED_TABLES = (
    ("projects", "created_at"),
    ("collections", "created_at"),
    ("missions", "created_at"),
    ("reports", "created_at"),
    ("documents", "uploaded_at"),
)


def upgrade() -> None:
    # 1. workspaces table (dormant tenancy seam) + a single seed row.
    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    bind = op.get_bind()
    bind.execute(
        text("INSERT INTO workspaces (id, name, created_at) VALUES (:id, :name, :created_at)"),
        {
            "id": uuid.UUID(DEFAULT_WORKSPACE_ID),
            "name": "Default Workspace",
            "created_at": datetime.utcnow(),
        },
    )

    # 2. additive nullable owner_id + workspace_id FKs + composite index per table.
    for table, ts_col in _OWNED_TABLES:
        op.add_column(table, sa.Column("owner_id", sa.UUID(), nullable=True))
        op.add_column(table, sa.Column("workspace_id", sa.UUID(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_owner_id",
            table,
            "users",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            f"fk_{table}_workspace_id",
            table,
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            f"ix_{table}_workspace_owner_{ts_col}",
            table,
            ["workspace_id", "owner_id", ts_col],
        )


def downgrade() -> None:
    for table, ts_col in _OWNED_TABLES:
        op.drop_index(f"ix_{table}_workspace_owner_{ts_col}", table_name=table)
        op.drop_constraint(f"fk_{table}_workspace_id", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_owner_id", table, type_="foreignkey")
        op.drop_column(table, "workspace_id")
        op.drop_column(table, "owner_id")
    op.drop_table("workspaces")
