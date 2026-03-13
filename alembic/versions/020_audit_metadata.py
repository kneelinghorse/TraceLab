"""Add audit metadata fields to documents, reports, tags, and missions.

This migration addresses gaps identified in R17.5 Architecture Health Check:
- documents.updated_at: Track document modifications
- reports.created_by: Audit report creators
- tags.created_at, tags.updated_at: Track tag age
- missions.created_at index: Query performance

Revision ID: 020_audit_metadata
Revises: 019_document_provenance
Create Date: 2025-12-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "020_audit_metadata"
down_revision = "019_document_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add audit metadata fields with idempotent checks."""
    bind = op.get_bind()
    inspector = inspect(bind)

    # =========================================================================
    # 1. DOCUMENTS: Add updated_at with auto-update trigger
    # =========================================================================
    if inspector.has_table("documents"):
        doc_columns = {col["name"] for col in inspector.get_columns("documents")}

        if "updated_at" not in doc_columns:
            op.add_column(
                "documents",
                sa.Column(
                    "updated_at",
                    sa.DateTime(),
                    nullable=True,
                    server_default=sa.func.now(),
                ),
            )
            # Backfill: set updated_at = uploaded_at for existing records
            op.execute(
                text(
                    "UPDATE documents SET updated_at = uploaded_at WHERE updated_at IS NULL"
                )
            )
            print("Added documents.updated_at column and backfilled from uploaded_at")

            # Create PostgreSQL trigger function for auto-update
            op.execute(
                text("""
                    CREATE OR REPLACE FUNCTION update_documents_updated_at()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = NOW();
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """)
            )

            # Create trigger on documents table
            op.execute(
                text("""
                    DROP TRIGGER IF EXISTS trigger_documents_updated_at ON documents;
                    CREATE TRIGGER trigger_documents_updated_at
                        BEFORE UPDATE ON documents
                        FOR EACH ROW
                        EXECUTE FUNCTION update_documents_updated_at();
                """)
            )
            print("Created auto-update trigger for documents.updated_at")
        else:
            print("documents.updated_at already exists, skipping")

    # =========================================================================
    # 2. REPORTS: Add created_by
    # =========================================================================
    if inspector.has_table("reports"):
        report_columns = {col["name"] for col in inspector.get_columns("reports")}

        if "created_by" not in report_columns:
            op.add_column(
                "reports",
                sa.Column(
                    "created_by",
                    sa.String(100),
                    nullable=True,
                    comment="Agent or user who created this report",
                ),
            )
            print("Added reports.created_by column")
        else:
            print("reports.created_by already exists, skipping")

    # =========================================================================
    # 3. TAGS: Add created_at and updated_at
    # =========================================================================
    if inspector.has_table("tags"):
        tag_columns = {col["name"] for col in inspector.get_columns("tags")}

        if "created_at" not in tag_columns:
            op.add_column(
                "tags",
                sa.Column(
                    "created_at",
                    sa.DateTime(),
                    nullable=True,
                    server_default=sa.func.now(),
                ),
            )
            # Backfill with current timestamp for existing records
            op.execute(
                text("UPDATE tags SET created_at = NOW() WHERE created_at IS NULL")
            )
            print("Added tags.created_at column")
        else:
            print("tags.created_at already exists, skipping")

        if "updated_at" not in tag_columns:
            op.add_column(
                "tags",
                sa.Column(
                    "updated_at",
                    sa.DateTime(),
                    nullable=True,
                    server_default=sa.func.now(),
                ),
            )
            # Backfill with current timestamp for existing records
            op.execute(
                text("UPDATE tags SET updated_at = NOW() WHERE updated_at IS NULL")
            )
            print("Added tags.updated_at column")

            # Create trigger function for tags auto-update
            op.execute(
                text("""
                    CREATE OR REPLACE FUNCTION update_tags_updated_at()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = NOW();
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """)
            )

            # Create trigger on tags table
            op.execute(
                text("""
                    DROP TRIGGER IF EXISTS trigger_tags_updated_at ON tags;
                    CREATE TRIGGER trigger_tags_updated_at
                        BEFORE UPDATE ON tags
                        FOR EACH ROW
                        EXECUTE FUNCTION update_tags_updated_at();
                """)
            )
            print("Created auto-update trigger for tags.updated_at")
        else:
            print("tags.updated_at already exists, skipping")

    # =========================================================================
    # 4. MISSIONS: Add index on created_at for query performance
    # =========================================================================
    if inspector.has_table("missions"):
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("missions")}

        if "idx_missions_created_at" not in existing_indexes:
            op.create_index(
                "idx_missions_created_at",
                "missions",
                ["created_at"],
            )
            print("Created index idx_missions_created_at on missions table")
        else:
            print("idx_missions_created_at already exists, skipping")

    print("Audit metadata migration complete!")


def downgrade() -> None:
    """Remove audit metadata fields."""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Drop missions index
    if inspector.has_table("missions"):
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("missions")}
        if "idx_missions_created_at" in existing_indexes:
            op.drop_index("idx_missions_created_at", table_name="missions")
            print("Dropped idx_missions_created_at")

    # Drop tags columns and triggers
    if inspector.has_table("tags"):
        op.execute(text("DROP TRIGGER IF EXISTS trigger_tags_updated_at ON tags"))
        op.execute(text("DROP FUNCTION IF EXISTS update_tags_updated_at()"))

        tag_columns = {col["name"] for col in inspector.get_columns("tags")}
        if "updated_at" in tag_columns:
            op.drop_column("tags", "updated_at")
        if "created_at" in tag_columns:
            op.drop_column("tags", "created_at")
        print("Dropped tags timestamp columns and triggers")

    # Drop reports created_by
    if inspector.has_table("reports"):
        report_columns = {col["name"] for col in inspector.get_columns("reports")}
        if "created_by" in report_columns:
            op.drop_column("reports", "created_by")
            print("Dropped reports.created_by")

    # Drop documents updated_at and trigger
    if inspector.has_table("documents"):
        op.execute(
            text("DROP TRIGGER IF EXISTS trigger_documents_updated_at ON documents")
        )
        op.execute(text("DROP FUNCTION IF EXISTS update_documents_updated_at()"))

        doc_columns = {col["name"] for col in inspector.get_columns("documents")}
        if "updated_at" in doc_columns:
            op.drop_column("documents", "updated_at")
            print("Dropped documents.updated_at and trigger")

    print("Audit metadata downgrade complete!")
