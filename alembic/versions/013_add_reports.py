"""Add reports, report_sources, and synthesis_cache tables.

Revision ID: 013_add_reports
Revises: 012_add_api_keys
Create Date: 2025-12-06 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "013_add_reports"
down_revision = "012_add_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Create reports table
    if not inspector.has_table("reports"):
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
                sa.ForeignKey("projects.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("report_type", sa.String(length=50), nullable=False, server_default="summary"),
            sa.Column("prompt", sa.Text(), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "parent_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("reports.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_reports_project_id", "reports", ["project_id"])
        op.create_index("ix_reports_status", "reports", ["status"])
        op.create_index("ix_reports_created_at", "reports", ["created_at"])

    # Create report_sources table
    if not inspector.has_table("report_sources"):
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
            sa.Column("source_type", sa.String(length=20), nullable=False),
            sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("added_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_report_sources_report_id", "report_sources", ["report_id"])
        op.create_index(
            "ix_report_sources_source_type_source_id",
            "report_sources",
            ["source_type", "source_id"],
        )

    # Create synthesis_cache table
    if not inspector.has_table("synthesis_cache"):
        op.create_table(
            "synthesis_cache",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("input_hash", sa.String(length=64), nullable=False, unique=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("citations", postgresql.JSONB(), nullable=True),
            sa.Column("model_used", sa.String(length=50), nullable=True),
            sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_hit_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_synthesis_cache_input_hash", "synthesis_cache", ["input_hash"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("synthesis_cache"):
        op.drop_index("ix_synthesis_cache_input_hash", table_name="synthesis_cache")
        op.drop_table("synthesis_cache")

    if inspector.has_table("report_sources"):
        op.drop_index("ix_report_sources_source_type_source_id", table_name="report_sources")
        op.drop_index("ix_report_sources_report_id", table_name="report_sources")
        op.drop_table("report_sources")

    if inspector.has_table("reports"):
        op.drop_index("ix_reports_created_at", table_name="reports")
        op.drop_index("ix_reports_status", table_name="reports")
        op.drop_index("ix_reports_project_id", table_name="reports")
        op.drop_table("reports")
