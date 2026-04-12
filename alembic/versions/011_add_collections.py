"""Add collections and collection_items tables for chunk grouping.

Revision ID: 011_add_collections
Revises: 010_add_evidence_linking_metadata
Create Date: 2025-12-05 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "011_add_collections"
down_revision = "010_evidence_link_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Create collections table
    if not inspector.has_table("collections"):
        op.create_table(
            "collections",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index("ix_collections_created_at", "collections", ["created_at"])

    # Create collection_items table
    if not inspector.has_table("collection_items"):
        op.create_table(
            "collection_items",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "collection_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("collections.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "chunk_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "added_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
            ),
            sa.UniqueConstraint(
                "collection_id", "chunk_id", name="uq_collection_item_collection_chunk"
            ),
        )
        op.create_index(
            "ix_collection_items_collection_id", "collection_items", ["collection_id"]
        )
        op.create_index(
            "ix_collection_items_chunk_id", "collection_items", ["chunk_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("collection_items"):
        op.drop_index("ix_collection_items_chunk_id", table_name="collection_items")
        op.drop_index(
            "ix_collection_items_collection_id", table_name="collection_items"
        )
        op.drop_table("collection_items")

    if inspector.has_table("collections"):
        op.drop_index("ix_collections_created_at", table_name="collections")
        op.drop_table("collections")
