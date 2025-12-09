"""Add document provenance fields for report-to-document promotion.

Adds columns to track where documents originated:
- source_report_id: FK to reports table for promoted reports
- source_mission_id: FK to missions table for mission-sourced documents
- source_origin: Type of document origin ('upload', 'synthesized', 'imported')

Revision ID: 019_document_provenance
Revises: 018_soft_delete
Create Date: 2025-12-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "019_document_provenance"
down_revision = "018_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add provenance columns to documents table."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("documents"):
        print("documents table not found, skipping migration")
        return

    existing_columns = {col["name"] for col in inspector.get_columns("documents")}
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("documents")}

    # Add source_report_id column
    if "source_report_id" not in existing_columns:
        # Use CHAR(36) for SQLite compatibility (stores UUIDs as text)
        op.add_column(
            "documents",
            sa.Column("source_report_id", sa.CHAR(36), nullable=True),
        )
        # Note: SQLite doesn't support foreign keys in ALTER TABLE
        # The FK relationship is defined in the model for ORM use
        print("Added source_report_id column to documents table")

    # Add source_mission_id column
    if "source_mission_id" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column("source_mission_id", sa.CHAR(36), nullable=True),
        )
        print("Added source_mission_id column to documents table")

    # Add source_origin column
    if "source_origin" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column(
                "source_origin",
                sa.String(20),
                nullable=True,
                server_default="upload",
                comment="Document origin: upload | synthesized | imported",
            ),
        )
        print("Added source_origin column to documents table")

    # Create index on source_origin for filtering
    if "idx_documents_source_origin" not in existing_indexes:
        op.create_index(
            "idx_documents_source_origin",
            "documents",
            ["source_origin"],
        )
        print("Created idx_documents_source_origin index")

    # Create partial index on source_report_id (only for non-null values)
    if "idx_documents_source_report" not in existing_indexes:
        op.create_index(
            "idx_documents_source_report",
            "documents",
            ["source_report_id"],
            # Partial index for PostgreSQL - SQLite will create full index
            postgresql_where=sa.text("source_report_id IS NOT NULL"),
        )
        print("Created idx_documents_source_report index")

    # Create index on source_mission_id
    if "idx_documents_source_mission" not in existing_indexes:
        op.create_index(
            "idx_documents_source_mission",
            "documents",
            ["source_mission_id"],
            postgresql_where=sa.text("source_mission_id IS NOT NULL"),
        )
        print("Created idx_documents_source_mission index")

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
    if "idx_documents_source_mission" in existing_indexes:
        op.drop_index("idx_documents_source_mission", table_name="documents")

    if "idx_documents_source_report" in existing_indexes:
        op.drop_index("idx_documents_source_report", table_name="documents")

    if "idx_documents_source_origin" in existing_indexes:
        op.drop_index("idx_documents_source_origin", table_name="documents")

    # Drop columns
    if "source_origin" in existing_columns:
        op.drop_column("documents", "source_origin")

    if "source_mission_id" in existing_columns:
        op.drop_column("documents", "source_mission_id")

    if "source_report_id" in existing_columns:
        op.drop_column("documents", "source_report_id")
