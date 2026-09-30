"""Add user credential revisions and a bounded, hashed password recovery slot."""

import sqlalchemy as sa

from alembic import op
from app.models.types import GUID

revision = "056_password_recovery"
down_revision = "055_collection_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("credential_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "password_recoveries",
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("delivery_status", sa.String(24), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("password_recoveries")
    op.drop_column("users", "credential_version")
