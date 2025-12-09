"""Add provenance columns to documents table for report promotion.

Revision ID: 019_document_provenance
Revises: 018_soft_delete
Create Date: 2025-12-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from app.models.types import GUID

revision = "019_document_provenance"
down_revision = "018_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add source_report_id, source_mission_id, source_origin columns to documents."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("documents"):
        print("documents table not found, skipping")
        return

    existing_columns = {col["name"] for col in inspector.get_columns("documents")}

    # Add source_report_id - references reports table
    if "source_report_id" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column("source_report_id", GUID(), nullable=True),
        )
        # Add foreign key constraint
        op.create_foreign_key(
            "fk_documents_source_report_id",
            "documents",
            "reports",
            ["source_report_id"],
            ["id"],
            ondelete="SET NULL",
        )
        print("Added source_report_id column to documents table")

    # Add source_mission_id - references missions table
    if "source_mission_id" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column("source_mission_id", GUID(), nullable=True),
        )
        # Add foreign key constraint
        op.create_foreign_key(
            "fk_documents_source_mission_id",
            "documents",
            "missions",
            ["source_mission_id"],
            ["id"],
            ondelete="SET NULL",
        )
        print("Added source_mission_id column to documents table")

    # Add source_origin - 'upload' | 'synthesized' | 'imported'
    if "source_origin" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column(
                "source_origin",
                sa.String(20),
                nullable=True,
                server_default="upload",
            ),
        )
        print("Added source_origin column to documents table")

    # Create indexes for efficient querying
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("documents")}

    if "idx_documents_source_origin" not in existing_indexes:
        op.create_index(
            "idx_documents_source_origin",
            "documents",
            ["source_origin"],
        )
        print("Created index idx_documents_source_origin")

    if "idx_documents_source_report_id" not in existing_indexes:
        op.create_index(
            "idx_documents_source_report_id",
            "documents",
            ["source_report_id"],
            postgresql_where=sa.text("source_report_id IS NOT NULL"),
        )
        print("Created partial index idx_documents_source_report_id")

    print("Document provenance migration complete!")


def downgrade() -> None:
    """Remove provenance columns from documents table."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("documents"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("documents")}
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("documents")}

    # Drop indexes first
    if "idx_documents_source_report_id" in existing_indexes:
        op.drop_index("idx_documents_source_report_id", table_name="documents")

    if "idx_documents_source_origin" in existing_indexes:
        op.drop_index("idx_documents_source_origin", table_name="documents")

    # Drop foreign keys and columns
    if "source_mission_id" in existing_columns:
        op.drop_constraint(
            "fk_documents_source_mission_id",
            "documents",
            type_="foreignkey",
        )
        op.drop_column("documents", "source_mission_id")

    if "source_report_id" in existing_columns:
        op.drop_constraint(
            "fk_documents_source_report_id",
            "documents",
            type_="foreignkey",
        )
        op.drop_column("documents", "source_report_id")

    if "source_origin" in existing_columns:
        op.drop_column("documents", "source_origin")

    print("Document provenance downgrade complete!")
