"""Persist validated citation identity without inventing mappings for legacy reports."""

import sqlalchemy as sa

from alembic import op
from app.models.types import CrossDBJSON

revision = "053_report_citations"
down_revision = "052_personal_spaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("citation_manifest", CrossDBJSON(), nullable=True))
    op.add_column("reports", sa.Column("generation_provenance", CrossDBJSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("reports", "generation_provenance")
    op.drop_column("reports", "citation_manifest")
