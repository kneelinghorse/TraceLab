"""Add users.is_active for admin soft-disable (Sprint 43 T43.5).

Additive nullable=False boolean with server_default true, so every existing user
is active. Set by the admin user-management API (enable/disable); login-enforcement
of disabled users is deferred to Sprint C (this is a zero-enforcement sprint).
Reversible.

Revision ID: 032_add_user_is_active
Revises: 031_backfill_ownership
Create Date: 2026-05-29
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "032_add_user_is_active"
down_revision = "031_backfill_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
