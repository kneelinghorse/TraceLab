"""Persist per-user project favorites.

Revision ID: 045_user_favorites
Revises: 044_home_mission_reviews
"""

import sqlalchemy as sa

from alembic import op
from app.models.types import GUID

revision = "045_user_favorites"
down_revision = "044_home_mission_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_favorites",
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entity_type", sa.String(32), primary_key=True),
        sa.Column("entity_id", GUID(), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("entity_type = 'project'", name="ck_user_favorites_project"),
    )


def downgrade():
    op.drop_table("user_favorites")
