"""Add research_depth column to missions table.

Supports DeepSearch depth tier system (baseline/deep/alpha) per Sprint 22.
See cmos/planning/research-depth-tiers.md for full specification.

Revision ID: 021_add_research_depth
Revises: 020_audit_metadata
Create Date: 2025-12-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "021_add_research_depth"
down_revision = "020_audit_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add research_depth column with constraint."""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Check if column already exists (idempotent)
    columns = [c["name"] for c in inspector.get_columns("missions")]
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

    # Add check constraint for valid values
    constraints = [c["name"] for c in inspector.get_check_constraints("missions")]
    if "valid_research_depth" not in constraints:
        op.create_check_constraint(
            "valid_research_depth",
            "missions",
            "research_depth IS NULL OR research_depth IN ('baseline', 'deep', 'alpha')",
        )


def downgrade() -> None:
    """Remove research_depth column and constraint."""
    # Remove constraint first
    op.drop_constraint("valid_research_depth", "missions", type_="check")
    # Then remove column
    op.drop_column("missions", "research_depth")
