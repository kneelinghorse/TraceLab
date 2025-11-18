"""Add search history table for query logging + replay.

Revision ID: 008_add_search_history
Revises: 007_add_faceted_filter_indexes
Create Date: 2025-11-16 03:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "008_add_search_history"
down_revision = "007_add_faceted_filter_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_exists = inspector.has_table("search_history")

    if not table_exists:
        op.create_table(
            "search_history",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("query_text", sa.Text(), nullable=False),
            sa.Column("search_mode", sa.String(length=32), nullable=False, server_default="semantic"),
            sa.Column("filters", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("top_k", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("user_label", sa.String(length=255)),
            sa.Column("metadata_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("top_chunks", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        existing_indexes: set[str] = set()
    else:
        existing_indexes = {index["name"] for index in inspector.get_indexes("search_history")}

    if "ix_search_history_created_at" not in existing_indexes:
        op.create_index("ix_search_history_created_at", "search_history", ["created_at"])
    if "ix_search_history_query_mode" not in existing_indexes:
        op.create_index("ix_search_history_query_mode", "search_history", ["search_mode"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("search_history"):
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("search_history")}
    if "ix_search_history_query_mode" in existing_indexes:
        op.drop_index("ix_search_history_query_mode", table_name="search_history")
    if "ix_search_history_created_at" in existing_indexes:
        op.drop_index("ix_search_history_created_at", table_name="search_history")
    op.drop_table("search_history")
