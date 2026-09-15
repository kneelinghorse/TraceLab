"""Per-user inbox watermark: a timestamp only, so revocation leaks nothing.

Revision ID: 048_user_inbox_state
Revises: 047_user_saved_views
"""

import sqlalchemy as sa

from alembic import op
from app.models.types import GUID

revision = "048_user_inbox_state"
down_revision = "047_user_saved_views"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_inbox_state",
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("seen_through", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # Inbox sections filter completions and failures by status and order them by
    # completed_at; the production round trip already exceeds the 150 ms budget
    # from any client, and caching would delay revocation (learning #167).
    op.create_index("ix_missions_status_completed_at", "missions", ["status", "completed_at"])


def downgrade():
    op.drop_index("ix_missions_status_completed_at", table_name="missions")
    op.drop_table("user_inbox_state")
