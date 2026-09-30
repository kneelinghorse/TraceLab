"""Retain secret-free admin recovery outcomes after account cleanup."""

import sqlalchemy as sa

from alembic import op
from app.models.types import GUID

revision = "057_password_recovery_audit"
down_revision = "056_password_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_recovery_audits",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("actor_user_id", GUID(), nullable=False),
        sa.Column("target_user_id", GUID(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("outcome", sa.String(24), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("password_recovery_audits")
