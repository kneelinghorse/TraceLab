"""Add document_metadata column to documents table.

Revision ID: 015_add_document_metadata
Revises: 014_missions_revamp
Create Date: 2024-12-06

Adds a JSON column for storing arbitrary metadata like mission_id,
deepsearch_job_id for auto-ingested documents.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "015_add_document_metadata"
down_revision = "014_missions_revamp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "document_metadata",
            sa.JSON(),
            nullable=True,
            comment="Arbitrary metadata object for document provenance",
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "document_metadata")
