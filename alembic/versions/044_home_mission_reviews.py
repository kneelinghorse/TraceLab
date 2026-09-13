"""Track explicit per-user review of a mission result.

Revision ID: 044_home_mission_reviews
Revises: 043_deepsearch_evidence
"""

import sqlalchemy as sa

from alembic import op
from app.models.types import GUID

revision = "044_home_mission_reviews"
down_revision = "043_deepsearch_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_mission_reviews",
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mission_id", GUID(), sa.ForeignKey("missions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mission_updated_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("user_mission_reviews")
