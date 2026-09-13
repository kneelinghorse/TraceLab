"""Add collection instructions and direct document context.

Revision ID: 046_collection_context
Revises: 045_user_favorites
"""

import sqlalchemy as sa

from alembic import op
from app.models.types import GUID

revision = "046_collection_context"
down_revision = "045_user_favorites"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("collections", sa.Column("instructions", sa.Text(), nullable=True))
    op.create_table(
        "collection_documents",
        sa.Column("collection_id", GUID(), sa.ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("document_id", GUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("collection_documents")
    op.drop_column("collections", "instructions")
