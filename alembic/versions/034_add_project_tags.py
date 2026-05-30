"""Create project_tags junction: cross-cutting themes link projects to tags.

T44.2 (sprint-44, Sprint B) — cross-cutting themes are modeled as a many-to-many
between projects and the existing tags table (category='theme'), NOT as project
nesting (architecture locked 2026-05-28, decision #196). Mirrors document_tags.
Reuses the tags table as-is: tag scoping stays user-scoped (uq_user_tag on
tags); this junction only links projects to existing tag rows and does not alter
tag scoping. Additive, reversible, dormant — nothing reads it yet.

Revision ID: 034_add_project_tags
Revises: 033_add_space_members
Create Date: 2026-05-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "034_add_project_tags"
down_revision = "033_add_space_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_tags",
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey(
                "projects.id",
                name="fk_project_tags_project_id",
                ondelete="CASCADE",
            ),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.UUID(),
            sa.ForeignKey(
                "tags.id",
                name="fk_project_tags_tag_id",
                ondelete="CASCADE",
            ),
            primary_key=True,
        ),
    )
    # Composite PK indexes (project_id, tag_id) — covers "tags of a project".
    # Add tag_id alone for the reverse "projects with this theme" lookup,
    # mirroring ix_document_tags_tag_id.
    op.create_index("ix_project_tags_tag_id", "project_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_index("ix_project_tags_tag_id", table_name="project_tags")
    op.drop_table("project_tags")
