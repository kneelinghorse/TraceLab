"""Personal Spaces: one per human user, and member projects leave Default (PERSONAL-1).

Decision #530 (the Google Drive shape) with Derek's answers in #531 and the
placement rule in #532. Schema: ``workspaces.personal_owner_id``, nullable and
unique, FK users.id ON DELETE CASCADE. A Space with it set is that user's
personal Space; there is no separate kind column. CASCADE because a personal
Space belongs to one person, so the admin hard-delete leaves no orphan Space;
the projects and children inside it are SET NULL by migration 030's FKs.

Backfill, in order:
1. Derek-Private is designated as its sole member's personal Space (Derek:
   "yes to both") instead of minting a second one. A database without that
   Space, or with it holding other than one human member, skips this step.
2. Every other human user (any role but service, active or not) gets
   "<display_name>'s Space" with one space_members row.
3. Projects owned by non-privileged users (roles other than owner, admin and
   service) that sit in Default Workspace move to their owner's personal Space.
   Their documents, missions and reports that sit in Default follow them.
   Collections have no project, so a member's collections in Default follow
   their owner instead. On 2026-09-22 production this moves one project, the
   guest's d2d6519c, with two documents, two missions and two reports.
   Child rows whose Space already disagreed with their project's are not
   touched here; that drift is a filed next-step, not this migration's.

Downgrade moves every row out of the personal Spaces this feature created
(everything except Derek-Private) back to Default Workspace, deletes those
Spaces (their space_members rows go with them by CASCADE) and drops the column.

Revision ID: 052_personal_spaces
Revises: 051_usage_records
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision = "052_personal_spaces"
down_revision = "051_usage_records"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
# Derek's existing private Space in production, designated as his personal one
# (decision #531). Absent anywhere else, where step 1 is a no-op.
DEREK_PRIVATE_ID = "081a5f9a-7629-45b7-bb53-5448bd050aec"
_CHILD_TABLES = ("documents", "missions", "reports")
_SPACED_TABLES = ("projects", "collections", *_CHILD_TABLES)


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("personal_owner_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_workspaces_personal_owner_id",
        "workspaces",
        "users",
        ["personal_owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_workspaces_personal_owner_id", "workspaces", ["personal_owner_id"]
    )

    bind = op.get_bind()
    default_id = uuid.UUID(DEFAULT_WORKSPACE_ID)

    # 1. Derek-Private becomes its sole human member's personal Space.
    bind.execute(
        text(
            "UPDATE workspaces SET personal_owner_id = ("
            "  SELECT sm.user_id FROM space_members sm JOIN users u ON u.id = sm.user_id"
            "  WHERE sm.workspace_id = :space_id AND u.role <> 'service') "
            "WHERE id = :space_id "
            "AND (SELECT count(*) FROM space_members WHERE workspace_id = :space_id) = 1"
        ),
        {"space_id": uuid.UUID(DEREK_PRIVATE_ID)},
    )

    # 2. A personal Space, with its membership row, for every other human user.
    humans = bind.execute(
        text(
            "SELECT u.id, u.display_name FROM users u "
            "WHERE u.role <> 'service' "
            "AND NOT EXISTS (SELECT 1 FROM workspaces w WHERE w.personal_owner_id = u.id) "
            "ORDER BY u.created_at, u.id"
        )
    ).fetchall()
    now = datetime.utcnow()
    for user_id, display_name in humans:
        space_id = uuid.uuid4()
        bind.execute(
            text(
                "INSERT INTO workspaces (id, name, created_at, personal_owner_id) "
                "VALUES (:id, :name, :created_at, :owner)"
            ),
            {"id": space_id, "name": f"{display_name}'s Space", "created_at": now, "owner": user_id},
        )
        bind.execute(
            text(
                "INSERT INTO space_members (id, workspace_id, user_id, role, created_at) "
                "VALUES (:id, :space_id, :user_id, 'member', :created_at)"
            ),
            {"id": uuid.uuid4(), "space_id": space_id, "user_id": user_id, "created_at": now},
        )

    # 3. Member-owned projects leave Default for their owner's personal Space.
    # Children move first, while their project still sits in Default.
    moves = (
        "SELECT p.id AS project_id, w.id AS space_id FROM projects p "
        "JOIN users u ON u.id = p.owner_id "
        "JOIN workspaces w ON w.personal_owner_id = u.id "
        "WHERE p.workspace_id = :default_id AND u.role NOT IN ('owner', 'admin', 'service')"
    )
    for table in _CHILD_TABLES:
        bind.execute(
            text(
                f"WITH moves AS ({moves}) "  # noqa: S608
                f"UPDATE {table} AS child SET workspace_id = moves.space_id FROM moves "
                "WHERE child.project_id = moves.project_id AND child.workspace_id = :default_id"
            ),
            {"default_id": default_id},
        )
    bind.execute(
        text(
            f"WITH moves AS ({moves}) "  # noqa: S608
            "UPDATE projects AS moved SET workspace_id = moves.space_id FROM moves "
            "WHERE moved.id = moves.project_id"
        ),
        {"default_id": default_id},
    )
    bind.execute(
        text(
            "UPDATE collections AS c SET workspace_id = w.id FROM users u, workspaces w "
            "WHERE c.owner_id = u.id AND w.personal_owner_id = u.id "
            "AND c.workspace_id = :default_id AND u.role NOT IN ('owner', 'admin', 'service')"
        ),
        {"default_id": default_id},
    )


def downgrade() -> None:
    bind = op.get_bind()
    created = (
        "SELECT id FROM workspaces "
        "WHERE personal_owner_id IS NOT NULL AND id <> :derek_private"
    )
    params = {
        "default_id": uuid.UUID(DEFAULT_WORKSPACE_ID),
        "derek_private": uuid.UUID(DEREK_PRIVATE_ID),
    }
    for table in _SPACED_TABLES:
        bind.execute(
            text(
                f"UPDATE {table} SET workspace_id = :default_id "  # noqa: S608
                f"WHERE workspace_id IN ({created})"
            ),
            params,
        )
    bind.execute(text(f"DELETE FROM workspaces WHERE id IN ({created})"), params)  # noqa: S608

    op.drop_constraint("uq_workspaces_personal_owner_id", "workspaces", type_="unique")
    op.drop_constraint("fk_workspaces_personal_owner_id", "workspaces", type_="foreignkey")
    op.drop_column("workspaces", "personal_owner_id")
