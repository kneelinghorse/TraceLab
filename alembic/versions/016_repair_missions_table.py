"""Repair database schema - create all missing tables.

This migration creates any missing core tables, fixing a corrupt database state
where alembic_version is at head but tables don't exist.

Revision ID: 016_repair_missions
Revises: 015_add_document_metadata
Create Date: 2025-12-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "016_repair_missions"
down_revision = "015_add_document_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Ensure pgcrypto extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Create projects table if missing
    if not inspector.has_table("projects"):
        print("Creating missing projects table...")
        op.create_table(
            "projects",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("user_id", postgresql.UUID(as_uuid=True)),
            sa.Column("mission_protocol_id", postgresql.UUID(as_uuid=True)),
            sa.Column("research_type", sa.String()),
            sa.Column("methodology", sa.String()),
            sa.Column("status", sa.String(), server_default="active"),
            sa.Column("quality_score", sa.Integer()),
            sa.Column("last_quality_check", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )

    # Create documents table if missing
    if not inspector.has_table("documents"):
        print("Creating missing documents table...")
        op.create_table(
            "documents",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("file_path", sa.String()),
            sa.Column("file_type", sa.String()),
            sa.Column("file_size", sa.Integer()),
            sa.Column("mime_type", sa.String()),
            sa.Column("source_type", sa.String()),
            sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("processed", sa.Boolean(), server_default="false"),
            sa.Column("chunked", sa.Boolean(), server_default="false"),
            sa.Column("embedded", sa.Boolean(), server_default="false"),
            sa.Column("validation_status", sa.String()),
            sa.Column("document_metadata", postgresql.JSONB(), server_default="{}"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("idx_documents_project_id", "documents", ["project_id"])

    # Create document_chunks table if missing
    if not inspector.has_table("document_chunks"):
        print("Creating missing document_chunks table...")
        op.create_table(
            "document_chunks",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "document_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("documents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("embedding_id", sa.String()),
            sa.Column("token_count", sa.Integer()),
            sa.Column("start_char", sa.Integer()),
            sa.Column("end_char", sa.Integer()),
            sa.Column("prev_chunk_id", postgresql.UUID(as_uuid=True)),
            sa.Column("next_chunk_id", postgresql.UUID(as_uuid=True)),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("idx_chunks_document_id", "document_chunks", ["document_id"])

    # Create reports table if missing
    if not inspector.has_table("reports"):
        print("Creating missing reports table...")
        op.create_table(
            "reports",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
            ),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column(
                "format", sa.String(50), nullable=False, server_default="markdown"
            ),
            sa.Column("content", sa.Text()),
            sa.Column("status", sa.String(20), server_default="draft"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )

    # Create missions table if missing
    if not inspector.has_table("missions"):
        print("Creating missing missions table...")
        op.create_table(
            "missions",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "project_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("mission_id", sa.String(50), nullable=False, unique=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("objective", sa.Text(), nullable=False),
            sa.Column("success_criteria", postgresql.JSONB(), nullable=False),
            sa.Column("context", postgresql.JSONB(), server_default="{}"),
            sa.Column("deliverables", postgresql.JSONB(), server_default="[]"),
            sa.Column("research_phases", postgresql.JSONB(), server_default="{}"),
            sa.Column("tags", postgresql.JSONB(), server_default="[]"),
            sa.Column("mission_metadata", postgresql.JSONB(), server_default="{}"),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("queued_at", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("deepsearch_job_id", sa.String(100), nullable=True),
            sa.Column("execution_metadata", postgresql.JSONB(), server_default="{}"),
            sa.Column("result_document_ids", postgresql.JSONB(), server_default="[]"),
            sa.Column(
                "result_report_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("reports.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("result_markdown", sa.Text(), nullable=True),
            sa.Column("result_protocol", postgresql.JSONB(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("created_by", sa.String(100), nullable=True),
        )
        op.create_index("idx_missions_project_id", "missions", ["project_id"])
        op.create_index("idx_missions_mission_id", "missions", ["mission_id"])
        op.create_index("idx_missions_status", "missions", ["status"])
        op.create_index(
            "idx_missions_deepsearch_job_id", "missions", ["deepsearch_job_id"]
        )
        op.create_index(
            "idx_missions_project_status", "missions", ["project_id", "status"]
        )

        # Add constraints
        op.execute("""
            ALTER TABLE missions
            ADD CONSTRAINT success_criteria_not_empty
            CHECK (jsonb_array_length(success_criteria) > 0)
        """)
        op.execute("""
            ALTER TABLE missions
            ADD CONSTRAINT title_length
            CHECK (char_length(title) >= 3 AND char_length(title) <= 255)
        """)
        op.execute("""
            ALTER TABLE missions
            ADD CONSTRAINT valid_mission_status
            CHECK (status IN ('draft', 'queued', 'in_progress', 'completed', 'blocked', 'cancelled'))
        """)

    print("Database repair complete!")


def downgrade() -> None:
    pass
