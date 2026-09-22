"""Per-user usage records for DeepSearch runs and Librarian calls (METER-0, decision #522).

Data only. One row per (mission, kind) for a DeepSearch run, one row per
Librarian model call. Nothing reads it to limit, block or bill.

Revision ID: 051_usage_records
Revises: 050_user_email_notifications
"""

import sqlalchemy as sa

from alembic import op
from app.models.types import GUID, CrossDBJSON

revision = "051_usage_records"
down_revision = "050_user_email_notifications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usage_records",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("project_id", GUID(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mission_id", GUID(), sa.ForeignKey("missions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attribution", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("requests", sa.Integer(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("tool_calls", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("usage_complete", sa.Boolean(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("details", CrossDBJSON, nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("mission_id", "kind", name="uq_usage_records_mission_kind"),
    )
    op.create_index("ix_usage_records_user_recorded", "usage_records", ["user_id", "recorded_at"])
    op.create_index("ix_usage_records_recorded_at", "usage_records", ["recorded_at"])


def downgrade():
    op.drop_index("ix_usage_records_recorded_at", table_name="usage_records")
    op.drop_index("ix_usage_records_user_recorded", table_name="usage_records")
    op.drop_table("usage_records")
