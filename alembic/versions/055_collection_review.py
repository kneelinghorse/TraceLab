"""Retain explicitly accepted collection provenance and excerpt order."""

import sqlalchemy as sa

from alembic import op
from app.models.types import CrossDBJSON

revision = "055_collection_review"
down_revision = "054_description_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collections", sa.Column("generation_provenance", CrossDBJSON(), nullable=True))
    op.add_column("collection_items", sa.Column("review_position", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("collection_items", "review_position")
    op.drop_column("collections", "generation_provenance")
