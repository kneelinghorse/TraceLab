"""Add soft delete columns to projects and documents tables.

Revision ID: 018_soft_delete
Revises: 017_fix_reports_schema
Create Date: 2025-12-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "018_soft_delete"
down_revision = "017_fix_reports_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add deleted_at and deleted_by columns to projects and documents tables."""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Add soft delete columns to projects table
    if inspector.has_table("projects"):
        existing_columns = {col["name"] for col in inspector.get_columns("projects")}

        if "deleted_at" not in existing_columns:
            op.add_column(
                "projects",
                sa.Column("deleted_at", sa.DateTime(), nullable=True),
            )
            # Create partial index for efficient filtering of non-deleted records
            op.create_index(
                "idx_projects_deleted_at",
                "projects",
                ["deleted_at"],
                postgresql_where=sa.text("deleted_at IS NOT NULL"),
            )
            print("Added deleted_at column to projects table")

        if "deleted_by" not in existing_columns:
            op.add_column(
                "projects",
                sa.Column("deleted_by", sa.String(100), nullable=True),
            )
            print("Added deleted_by column to projects table")

    # Add soft delete columns to documents table
    if inspector.has_table("documents"):
        existing_columns = {col["name"] for col in inspector.get_columns("documents")}

        if "deleted_at" not in existing_columns:
            op.add_column(
                "documents",
                sa.Column("deleted_at", sa.DateTime(), nullable=True),
            )
            # Create partial index for efficient filtering of non-deleted records
            op.create_index(
                "idx_documents_deleted_at",
                "documents",
                ["deleted_at"],
                postgresql_where=sa.text("deleted_at IS NOT NULL"),
            )
            print("Added deleted_at column to documents table")

        if "deleted_by" not in existing_columns:
            op.add_column(
                "documents",
                sa.Column("deleted_by", sa.String(100), nullable=True),
            )
            print("Added deleted_by column to documents table")

    print("Soft delete migration complete!")


def downgrade() -> None:
    """Remove soft delete columns."""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Remove from documents
    if inspector.has_table("documents"):
        existing_columns = {col["name"] for col in inspector.get_columns("documents")}
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("documents")}

        if "idx_documents_deleted_at" in existing_indexes:
            op.drop_index("idx_documents_deleted_at", table_name="documents")

        if "deleted_at" in existing_columns:
            op.drop_column("documents", "deleted_at")

        if "deleted_by" in existing_columns:
            op.drop_column("documents", "deleted_by")

    # Remove from projects
    if inspector.has_table("projects"):
        existing_columns = {col["name"] for col in inspector.get_columns("projects")}
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("projects")}

        if "idx_projects_deleted_at" in existing_indexes:
            op.drop_index("idx_projects_deleted_at", table_name="projects")

        if "deleted_at" in existing_columns:
            op.drop_column("projects", "deleted_at")

        if "deleted_by" in existing_columns:
            op.drop_column("projects", "deleted_by")
