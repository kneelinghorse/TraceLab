"""Revamp missions table with DeepSearch-compatible schema.

This migration transforms the existing missions table from a JSON blob storage
to explicit fields supporting:
- Core mission definition (mission_id, title, objective, success_criteria)
- Optional mission structure (context, deliverables, research_phases, tags)
- Execution tracking (status, timestamps, deepsearch_job_id)
- Results storage (documents, reports, markdown, protocol)

Revision ID: 014_missions_revamp
Revises: 013_add_reports
Create Date: 2025-12-06 23:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "014_missions_revamp"
down_revision = "013_add_reports"
branch_labels = None
depends_on = None


def is_postgresql(bind) -> bool:
    """Check if we're running against PostgreSQL."""
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    is_pg = is_postgresql(bind)

    # Check if the old missions table exists
    if inspector.has_table("missions"):
        # Get existing columns to check what needs to be added/modified
        existing_columns = {col["name"] for col in inspector.get_columns("missions")}

        # Check if this is the old schema (has mission_data column)
        has_old_schema = "mission_data" in existing_columns

        if has_old_schema:
            # We need to drop old columns and add new ones
            # First, drop old constraints
            try:
                op.drop_constraint(
                    "missions_mission_data_check", "missions", type_="check"
                )
            except Exception:
                pass  # Constraint might not exist

            try:
                op.drop_index("idx_missions_project_status", table_name="missions")
            except Exception:
                pass

        # Add new columns if they don't exist
        new_columns = {
            "mission_id": sa.Column(
                "mission_id", sa.String(50), nullable=True
            ),  # Will add constraint after backfill
            "title": sa.Column("title", sa.String(255), nullable=True),
            "objective": sa.Column("objective", sa.Text(), nullable=True),
            "success_criteria": sa.Column(
                "success_criteria",
                postgresql.JSONB() if is_pg else sa.JSON(),
                nullable=True,
            ),
            "context": sa.Column(
                "context",
                postgresql.JSONB() if is_pg else sa.JSON(),
                server_default="{}",
            ),
            "deliverables": sa.Column(
                "deliverables",
                postgresql.JSONB() if is_pg else sa.JSON(),
                server_default="[]",
            ),
            "research_phases": sa.Column(
                "research_phases",
                postgresql.JSONB() if is_pg else sa.JSON(),
                server_default="{}",
            ),
            "tags": sa.Column(
                "tags",
                postgresql.JSONB() if is_pg else sa.JSON(),
                server_default="[]",
            ),
            "mission_metadata": sa.Column(
                "mission_metadata",
                postgresql.JSONB() if is_pg else sa.JSON(),
                server_default="{}",
            ),
            "queued_at": sa.Column("queued_at", sa.DateTime(), nullable=True),
            "started_at": sa.Column("started_at", sa.DateTime(), nullable=True),
            "completed_at": sa.Column("completed_at", sa.DateTime(), nullable=True),
            "deepsearch_job_id": sa.Column(
                "deepsearch_job_id", sa.String(100), nullable=True
            ),
            "execution_metadata": sa.Column(
                "execution_metadata",
                postgresql.JSONB() if is_pg else sa.JSON(),
                server_default="{}",
            ),
            "result_document_ids": sa.Column(
                "result_document_ids",
                postgresql.JSONB() if is_pg else sa.JSON(),
                server_default="[]",
            ),
            "result_report_id": sa.Column(
                "result_report_id",
                postgresql.UUID(as_uuid=True) if is_pg else sa.String(36),
                sa.ForeignKey("reports.id", ondelete="SET NULL"),
                nullable=True,
            ),
            "result_markdown": sa.Column("result_markdown", sa.Text(), nullable=True),
            "result_protocol": sa.Column(
                "result_protocol",
                postgresql.JSONB() if is_pg else sa.JSON(),
                nullable=True,
            ),
            "error_message": sa.Column("error_message", sa.Text(), nullable=True),
            "created_by": sa.Column("created_by", sa.String(100), nullable=True),
        }

        # Get current columns to avoid duplicates
        current_columns = {col["name"] for col in inspector.get_columns("missions")}

        for col_name, col_def in new_columns.items():
            if col_name not in current_columns:
                op.add_column("missions", col_def)

        # Migrate data from old mission_data column to new columns
        if has_old_schema and is_pg:
            # Extract data from mission_data JSON blob
            # Note: Cast mission_data to jsonb first to ensure consistent types in COALESCE
            op.execute("""
                UPDATE missions SET
                    mission_id = COALESCE(
                        mission_data->>'mission_id',
                        'MIGRATED-' || LEFT(id::text, 8)
                    ),
                    title = COALESCE(
                        mission_data->>'title',
                        'Migrated Mission'
                    ),
                    objective = COALESCE(
                        mission_data->'research_statement'->>'objective',
                        mission_data->>'objective',
                        'Objective to be defined'
                    ),
                    success_criteria = COALESCE(
                        (mission_data::jsonb)->'success_criteria',
                        '["TBD"]'::jsonb
                    )
                WHERE mission_data IS NOT NULL
            """)
            # Set defaults for rows without mission_data
            op.execute("""
                UPDATE missions SET
                    mission_id = 'MIGRATED-' || LEFT(id::text, 8),
                    title = 'Migrated Mission',
                    objective = 'Objective to be defined',
                    success_criteria = '["TBD"]'::jsonb
                WHERE mission_id IS NULL
            """)

        # Drop old columns AFTER data migration
        if has_old_schema:
            for old_col in [
                "mission_data",
                "quality_gates",
                "evidence_linking_metadata",
                "completion_percentage",
            ]:
                if old_col in existing_columns:
                    op.drop_column("missions", old_col)

        # Deduplicate mission_ids by appending row number for duplicates
        if is_pg:
            op.execute("""
                WITH duplicates AS (
                    SELECT id, mission_id,
                           ROW_NUMBER() OVER (PARTITION BY mission_id ORDER BY created_at) as rn
                    FROM missions
                    WHERE mission_id IS NOT NULL
                )
                UPDATE missions m
                SET mission_id = d.mission_id || '-DUP' || d.rn
                FROM duplicates d
                WHERE m.id = d.id AND d.rn > 1
            """)

        # Make required columns NOT NULL after data migration
        if is_pg:
            op.alter_column("missions", "mission_id", nullable=False)
            op.alter_column("missions", "title", nullable=False)
            op.alter_column("missions", "objective", nullable=False)
            op.alter_column("missions", "success_criteria", nullable=False)

        # Add unique constraint on mission_id
        try:
            op.create_unique_constraint(
                "uq_missions_mission_id", "missions", ["mission_id"]
            )
        except Exception:
            pass

        # Add indexes
        try:
            op.create_index("idx_missions_mission_id", "missions", ["mission_id"])
        except Exception:
            pass
        try:
            op.create_index("idx_missions_status", "missions", ["status"])
        except Exception:
            pass
        try:
            op.create_index(
                "idx_missions_deepsearch_job_id", "missions", ["deepsearch_job_id"]
            )
        except Exception:
            pass
        try:
            op.create_index(
                "idx_missions_project_status", "missions", ["project_id", "status"]
            )
        except Exception:
            pass

    else:
        # Create the table from scratch
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

        # Add indexes
        op.create_index("idx_missions_project_id", "missions", ["project_id"])
        op.create_index("idx_missions_mission_id", "missions", ["mission_id"])
        op.create_index("idx_missions_status", "missions", ["status"])
        op.create_index(
            "idx_missions_deepsearch_job_id", "missions", ["deepsearch_job_id"]
        )
        op.create_index(
            "idx_missions_project_status", "missions", ["project_id", "status"]
        )

    # Migrate existing status values to new schema before adding constraints
    # Old schema: 'draft', 'in_progress', 'review', 'complete'
    # New schema: 'draft', 'queued', 'in_progress', 'completed', 'blocked', 'cancelled'
    op.execute("""
        UPDATE missions SET status = 'completed' WHERE status = 'complete'
    """)
    op.execute("""
        UPDATE missions SET status = 'in_progress' WHERE status = 'review'
    """)
    # Set any other unexpected values to 'draft'
    op.execute("""
        UPDATE missions SET status = 'draft'
        WHERE status IS NULL
           OR status NOT IN ('draft', 'queued', 'in_progress', 'completed', 'blocked', 'cancelled')
    """)

    # Add constraints (PostgreSQL only for now due to JSON function differences)
    if is_pg:
        # Success criteria must be non-empty array - only if success_criteria column has data
        # Skip this constraint if there are rows with NULL or empty success_criteria
        op.execute("""
            UPDATE missions SET success_criteria = '["TBD"]'::jsonb
            WHERE success_criteria IS NULL
               OR jsonb_typeof(success_criteria) != 'array'
               OR jsonb_array_length(success_criteria) = 0
        """)
        op.execute("""
            ALTER TABLE missions
            ADD CONSTRAINT success_criteria_not_empty
            CHECK (jsonb_array_length(success_criteria) > 0)
        """)

        # Title length constraint - ensure titles meet requirements
        op.execute("""
            UPDATE missions SET title = CONCAT(COALESCE(title, ''), ' (migrated)')
            WHERE title IS NULL OR char_length(title) < 3
        """)
        op.execute("""
            ALTER TABLE missions
            ADD CONSTRAINT title_length
            CHECK (char_length(title) >= 3 AND char_length(title) <= 255)
        """)

        # Valid status values
        op.execute("""
            ALTER TABLE missions
            ADD CONSTRAINT valid_mission_status
            CHECK (status IN ('draft', 'queued', 'in_progress', 'completed', 'blocked', 'cancelled'))
        """)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    is_pg = is_postgresql(bind)

    if inspector.has_table("missions"):
        # Drop constraints
        if is_pg:
            try:
                op.drop_constraint(
                    "success_criteria_not_empty", "missions", type_="check"
                )
            except Exception:
                pass
            try:
                op.drop_constraint("title_length", "missions", type_="check")
            except Exception:
                pass
            try:
                op.drop_constraint("valid_mission_status", "missions", type_="check")
            except Exception:
                pass

        # Drop unique constraint
        try:
            op.drop_constraint("uq_missions_mission_id", "missions", type_="unique")
        except Exception:
            pass

        # Drop new indexes
        for idx in [
            "idx_missions_mission_id",
            "idx_missions_status",
            "idx_missions_deepsearch_job_id",
            "idx_missions_project_status",
            "idx_missions_project_id",
        ]:
            try:
                op.drop_index(idx, table_name="missions")
            except Exception:
                pass

        # Drop new columns
        new_cols = [
            "mission_id",
            "title",
            "objective",
            "success_criteria",
            "context",
            "deliverables",
            "research_phases",
            "tags",
            "mission_metadata",
            "queued_at",
            "started_at",
            "completed_at",
            "deepsearch_job_id",
            "execution_metadata",
            "result_document_ids",
            "result_report_id",
            "result_markdown",
            "result_protocol",
            "error_message",
            "created_by",
        ]
        existing_columns = {col["name"] for col in inspector.get_columns("missions")}
        for col in new_cols:
            if col in existing_columns:
                op.drop_column("missions", col)

        # Re-add old columns for backward compatibility
        op.add_column(
            "missions",
            sa.Column(
                "mission_data",
                postgresql.JSONB() if is_pg else sa.JSON(),
                nullable=False,
                server_default="{}",
            ),
        )
        op.add_column(
            "missions",
            sa.Column(
                "quality_gates",
                postgresql.JSONB() if is_pg else sa.JSON(),
                nullable=True,
            ),
        )
        op.add_column(
            "missions",
            sa.Column(
                "evidence_linking_metadata",
                postgresql.JSONB() if is_pg else sa.JSON(),
                nullable=True,
            ),
        )
        op.add_column(
            "missions",
            sa.Column("completion_percentage", sa.Integer(), server_default="0"),
        )

        # Re-add old index
        op.create_index(
            "idx_missions_project_status", "missions", ["project_id", "status"]
        )
