"""Per-user opt-out for mission completion and failure emails (NOTIFY-1, decision #455).

Additive, defaulting to enabled, so existing users receive mail until they turn it off.

Revision ID: 050_user_email_notifications
Revises: 049_recent_activity
"""

import sqlalchemy as sa

from alembic import op

revision = "050_user_email_notifications"
down_revision = "049_recent_activity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("email_notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade():
    op.drop_column("users", "email_notifications_enabled")
