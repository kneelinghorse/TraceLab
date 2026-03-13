"""Fix reports table schema - add missing columns.

Revision ID: 017_fix_reports_schema
Revises: 016_repair_missions
Create Date: 2025-12-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "017_fix_reports_schema"
down_revision = "016_repair_missions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Check if reports table needs fixing
    if inspector.has_table("reports"):
        existing_columns = {col["name"] for col in inspector.get_columns("reports")}

        # Add missing columns
        if "report_type" not in existing_columns:
            op.add_column(
                "reports",
                sa.Column(
                    "report_type",
                    sa.String(50),
                    nullable=False,
                    server_default="summary",
                ),
            )

        if "prompt" not in existing_columns:
            op.add_column("reports", sa.Column("prompt", sa.Text(), nullable=True))

        if "content_hash" not in existing_columns:
            op.add_column(
                "reports", sa.Column("content_hash", sa.String(64), nullable=True)
            )

        if "version" not in existing_columns:
            op.add_column(
                "reports",
                sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            )

        if "parent_id" not in existing_columns:
            op.add_column(
                "reports",
                sa.Column(
                    "parent_id",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("reports.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )

        if "tokens_used" not in existing_columns:
            op.add_column(
                "reports",
                sa.Column(
                    "tokens_used", sa.Integer(), nullable=False, server_default="0"
                ),
            )

        if "chunk_count" not in existing_columns:
            op.add_column(
                "reports",
                sa.Column(
                    "chunk_count", sa.Integer(), nullable=False, server_default="0"
                ),
            )

        # Make content NOT NULL if it was nullable
        # First update any NULL values
        op.execute("UPDATE reports SET content = '' WHERE content IS NULL")

    # Create report_sources table if missing
    if not inspector.has_table("report_sources"):
        print("Creating missing report_sources table...")
        op.create_table(
            "report_sources",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "report_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("reports.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("source_type", sa.String(20), nullable=False),
            sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "added_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index("ix_report_sources_report_id", "report_sources", ["report_id"])
        op.create_index(
            "ix_report_sources_source_type_source_id",
            "report_sources",
            ["source_type", "source_id"],
        )

    print("Reports schema fix complete!")


def downgrade() -> None:
    pass
