"""Add evidence_linking_metadata column to missions.

Revision ID: 010_evidence_link_meta
Revises: 009_add_saved_searches
Create Date: 2025-11-17 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "010_evidence_link_meta"
down_revision = "009_add_saved_searches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "missions", sa.Column("evidence_linking_metadata", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("missions", "evidence_linking_metadata")
