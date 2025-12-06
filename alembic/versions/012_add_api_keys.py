"""Add api_keys table for API key authentication.

Revision ID: 012_add_api_keys
Revises: 011_add_collections
Create Date: 2025-12-06 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "012_add_api_keys"
down_revision = "011_add_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Create api_keys table
    if not inspector.has_table("api_keys"):
        op.create_table(
            "api_keys",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("user_id", sa.String(length=255), nullable=False, server_default="default"),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("key_hash", sa.String(length=255), nullable=False),
            sa.Column("key_prefix", sa.String(length=12), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
        op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("api_keys"):
        op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
        op.drop_index("ix_api_keys_user_id", table_name="api_keys")
        op.drop_table("api_keys")
