"""Recent activity: per-item viewed marks replace the inbox watermark, mission reviews and saved views.

Revision ID: 049_recent_activity
Revises: 048_user_inbox_state
"""

import sqlalchemy as sa

from alembic import op
from app.models.types import GUID

revision = "049_recent_activity"
down_revision = "048_user_inbox_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_item_views",
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("item_type", sa.String(32), primary_key=True),
        sa.Column("item_id", GUID(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("viewed_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("item_type IN ('mission', 'report', 'evidence')", name="ck_user_item_views_type"),
    )
    op.drop_table("user_inbox_state")
    op.drop_table("user_mission_reviews")
    op.drop_index("ix_user_saved_views_user_updated", table_name="user_saved_views")
    op.drop_table("user_saved_views")
    # ix_missions_status_completed_at (048) stays: the activity stream orders completions by completed_at.


def downgrade():
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
    op.create_table(
        "user_mission_reviews",
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mission_id", GUID(), sa.ForeignKey("missions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mission_updated_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "user_inbox_state",
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("seen_through", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.drop_table("user_item_views")
