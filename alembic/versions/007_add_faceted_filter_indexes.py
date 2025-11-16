"""Add indexes to support faceted search filters.

Revision ID: 007_add_faceted_filter_indexes
Revises: 006_add_fulltext_search
Create Date: 2025-11-16 00:02:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "007_add_faceted_filter_indexes"
down_revision = "006_add_fulltext_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_documents_file_type", "documents", ["file_type"])
    op.create_index("ix_documents_source_type", "documents", ["source_type"])
    op.create_index("ix_documents_collection_date", "documents", ["collection_date"])
    op.create_index("ix_document_tags_tag_id", "document_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_index("ix_document_tags_tag_id", table_name="document_tags")
    op.drop_index("ix_documents_collection_date", table_name="documents")
    op.drop_index("ix_documents_source_type", table_name="documents")
    op.drop_index("ix_documents_file_type", table_name="documents")
