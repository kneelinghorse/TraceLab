"""Add document processing status audit trail.

Revision ID: 002_processing_status
Revises: 001_initial
Create Date: 2025-11-01 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "002_processing_status"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_processing_statuses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_processing_status_document",
        "document_processing_statuses",
        ["document_id", "created_at"],
    )
    op.create_index(
        "idx_processing_status_stage",
        "document_processing_statuses",
        ["stage", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_processing_status_stage", table_name="document_processing_statuses")
    op.drop_index("idx_processing_status_document", table_name="document_processing_statuses")
    op.drop_table("document_processing_statuses")
