"""Create space_members table: the access grant linking a user to a Space.

T44.1 (sprint-44, Sprint B) — materializes the Space as the access-grant unit
(architecture locked 2026-05-28, decision #196). A row says "this user is a
member of this Space (workspace)". Additive, reversible, and dormant: nothing
reads space_members yet — the membership lookup
(authorization._has_space_membership) lands in T44.3 and stays behind
rbac_enabled=OFF until Sprint C, so day-one behavior is byte-identical.

Revision ID: 033_add_space_members
Revises: 032_add_user_is_active
Create Date: 2026-05-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "033_add_space_members"
down_revision = "032_add_user_is_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "space_members",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.UUID(),
            sa.ForeignKey(
                "workspaces.id",
                name="fk_space_members_workspace_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey(
                "users.id",
                name="fk_space_members_user_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        # Per-space grant tier, reusing the global role vocabulary
        # (owner/admin/member/viewer). NOT consulted by the Sprint B/C membership
        # check (presence in this table is what grants access); reserved for later
        # per-space tiering. Plain String to mirror users.role.
        sa.Column("role", sa.String(length=50), nullable=False, server_default="member"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        # One membership row per (Space, user) — the access grant is idempotent.
        sa.UniqueConstraint(
            "workspace_id", "user_id", name="uq_space_members_workspace_user"
        ),
    )
    # The UNIQUE constraint indexes (workspace_id, user_id) — good for "is this
    # user in this Space" and "members of a Space". Add user_id alone for the
    # reverse lookup "which Spaces is this user in" (T44.5 admin listing).
    op.create_index("ix_space_members_user_id", "space_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_space_members_user_id", table_name="space_members")
    op.drop_table("space_members")
