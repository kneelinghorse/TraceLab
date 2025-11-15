"""Add performance-focused indexes for high-traffic queries.

Revision ID: 005_performance_indexes
Revises: 004_mission_protocol_validation
Create Date: 2025-11-15 06:30:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "005_performance_indexes"
down_revision = "004_mission_protocol_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_documents_project_id", "documents", ["project_id"])
    op.create_index("idx_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("idx_document_chunks_embedding_id", "document_chunks", ["embedding_id"])
    op.create_index("idx_insights_project_id", "insights", ["project_id"])
    op.create_index("idx_insight_sources_chunk_id", "insight_sources", ["chunk_id"])
    op.create_index("idx_missions_project_status", "missions", ["project_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_missions_project_status", table_name="missions")
    op.drop_index("idx_insight_sources_chunk_id", table_name="insight_sources")
    op.drop_index("idx_insights_project_id", table_name="insights")
    op.drop_index("idx_document_chunks_embedding_id", table_name="document_chunks")
    op.drop_index("idx_document_chunks_document_id", table_name="document_chunks")
    op.drop_index("idx_documents_project_id", table_name="documents")
