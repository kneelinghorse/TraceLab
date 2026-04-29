"""Drop research_depth column from missions table.

Removes the depth-tier authoring slot (baseline/deep/alpha) along with its
``valid_research_depth`` check constraint. The MCP layer stopped exposing
``research_depth`` in commit 362940f (T42.2 — sprint-42); this migration
finishes the data-layer removal so the column is gone end-to-end.

No backfill: the column was nullable, the live DeepSearch worker SELECT no
longer references it (DS poller.py:133 + :249-254 are removed in lockstep),
and TraceLab's preview path now defaults to ``"baseline"`` inline. Column
contents are decorative noise on the worker side per DS audit.

Revision ID: 028_drop_research_depth
Revises: 027_add_mission_authoring_fields
Create Date: 2026-04-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "028_drop_research_depth"
down_revision = "027_add_mission_authoring_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop valid_research_depth check constraint then research_depth column."""
    bind = op.get_bind()
    inspector = inspect(bind)

    constraints = {c["name"] for c in inspector.get_check_constraints("missions")}
    if "valid_research_depth" in constraints:
        op.drop_constraint("valid_research_depth", "missions", type_="check")

    columns = {c["name"] for c in inspector.get_columns("missions")}
    if "research_depth" in columns:
        op.drop_column("missions", "research_depth")


def downgrade() -> None:
    """Re-add the column and its check constraint with the original shape."""
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = {c["name"] for c in inspector.get_columns("missions")}
    if "research_depth" not in columns:
        op.add_column(
            "missions",
            sa.Column(
                "research_depth",
                sa.String(20),
                nullable=True,
                server_default="baseline",
                comment="Research depth tier: baseline, deep, or alpha",
            ),
        )

    constraints = {c["name"] for c in inspector.get_check_constraints("missions")}
    if "valid_research_depth" not in constraints:
        op.create_check_constraint(
            "valid_research_depth",
            "missions",
            "research_depth IS NULL OR research_depth IN ('baseline', 'deep', 'alpha')",
        )
