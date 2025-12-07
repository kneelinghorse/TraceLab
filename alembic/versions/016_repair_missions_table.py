"""Repair missions table - ensure it exists.

This migration ensures the missions table exists, even if migration 014 failed.
It's idempotent and safe to run multiple times.

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


def is_postgresql(bind) -> bool:
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    is_pg = is_postgresql(bind)

    # Check if missions table exists
    if inspector.has_table("missions"):
        print("missions table already exists, skipping creation")
        return

    print("missions table does not exist, creating it now...")

    # Create the missions table
    op.create_table(
        "missions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True) if is_pg else sa.String(36),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()") if is_pg else None,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True) if is_pg else sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        # DeepSearch Required Fields
        sa.Column("mission_id", sa.String(50), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column(
            "success_criteria",
            postgresql.JSONB() if is_pg else sa.JSON(),
            nullable=False,
        ),
        # DeepSearch Optional Fields
        sa.Column(
            "context",
            postgresql.JSONB() if is_pg else sa.JSON(),
            server_default="{}",
        ),
        sa.Column(
            "deliverables",
            postgresql.JSONB() if is_pg else sa.JSON(),
            server_default="[]",
        ),
        sa.Column(
            "research_phases",
            postgresql.JSONB() if is_pg else sa.JSON(),
            server_default="{}",
        ),
        sa.Column(
            "tags",
            postgresql.JSONB() if is_pg else sa.JSON(),
            server_default="[]",
        ),
        sa.Column(
            "mission_metadata",
            postgresql.JSONB() if is_pg else sa.JSON(),
            server_default="{}",
        ),
        # Execution Tracking
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("deepsearch_job_id", sa.String(100), nullable=True),
        # Results
        sa.Column(
            "execution_metadata",
            postgresql.JSONB() if is_pg else sa.JSON(),
            server_default="{}",
        ),
        sa.Column(
            "result_document_ids",
            postgresql.JSONB() if is_pg else sa.JSON(),
            server_default="[]",
        ),
        sa.Column(
            "result_report_id",
            postgresql.UUID(as_uuid=True) if is_pg else sa.String(36),
            sa.ForeignKey("reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("result_markdown", sa.Text(), nullable=True),
        sa.Column(
            "result_protocol",
            postgresql.JSONB() if is_pg else sa.JSON(),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        # Housekeeping
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100), nullable=True),
    )

    # Add indexes
    op.create_index("idx_missions_project_id", "missions", ["project_id"])
    op.create_index("idx_missions_mission_id", "missions", ["mission_id"])
    op.create_index("idx_missions_status", "missions", ["status"])
    op.create_index("idx_missions_deepsearch_job_id", "missions", ["deepsearch_job_id"])
    op.create_index("idx_missions_project_status", "missions", ["project_id", "status"])

    # Add constraints (PostgreSQL only)
    if is_pg:
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

    print("missions table created successfully")


def downgrade() -> None:
    # Don't drop the table on downgrade - it might have data
    pass
