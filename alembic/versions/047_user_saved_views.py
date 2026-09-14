"""Persist personal mission dashboards with user-delete cascade.

Revision ID: 047_user_saved_views
Revises: 046_collection_context
"""

import sqlalchemy as sa

from alembic import op
from app.models.types import GUID

revision = "047_user_saved_views"
down_revision = "046_collection_context"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_saved_views",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("entity_type = 'missions'", name="ck_user_saved_views_missions"),
        sa.UniqueConstraint("user_id", "name", name="uq_user_saved_views_user_name"),
    )
    op.create_index("ix_user_saved_views_user_updated", "user_saved_views", ["user_id", "updated_at"])


def downgrade():
    op.drop_table("user_saved_views")
