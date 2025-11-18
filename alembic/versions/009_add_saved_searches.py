"""Add saved searches table for reusable query bookmarks.

Revision ID: 009_add_saved_searches
Revises: 008_add_search_history
Create Date: 2025-11-16 04:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "009_add_saved_searches"
down_revision = "008_add_search_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_exists = inspector.has_table("saved_searches")

    if not table_exists:
        op.create_table(
            "saved_searches",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("query_text", sa.Text(), nullable=False),
            sa.Column("search_mode", sa.String(length=32), nullable=False, server_default="semantic"),
            sa.Column("filters", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("top_k", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("owner", sa.String(length=128), nullable=False),
            sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("owner", "name", name="uq_saved_search_owner_name"),
        )
        existing_indexes: set[str] = set()
    else:
        existing_indexes = {index["name"] for index in inspector.get_indexes("saved_searches")}

    if "ix_saved_searches_owner_created_at" not in existing_indexes:
        op.create_index(
            "ix_saved_searches_owner_created_at",
            "saved_searches",
            ["owner", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("saved_searches"):
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("saved_searches")}
    if "ix_saved_searches_owner_created_at" in existing_indexes:
        op.drop_index("ix_saved_searches_owner_created_at", table_name="saved_searches")
    op.drop_table("saved_searches")
