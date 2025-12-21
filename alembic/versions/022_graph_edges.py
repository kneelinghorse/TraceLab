"""Add graph_edges table for PEDR L6 layer.

Stores materialized edges from Semantic Protocol v3.3.0 manifests
and FK-derived relationships. Supports graph traversal for search.

Sprint 24: PEDR Graph Foundation

Revision ID: 022_graph_edges
Revises: 021_add_research_depth
Create Date: 2025-12-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

revision = "022_graph_edges"
down_revision = "021_add_research_depth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create graph_edges table with indexes."""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Check if table already exists (idempotent)
    existing_tables = inspector.get_table_names()
    if "graph_edges" in existing_tables:
        return

    # Create the graph_edges table
    op.create_table(
        "graph_edges",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "from_urn",
            sa.String(512),
            nullable=False,
            comment="Source entity URN",
        ),
        sa.Column(
            "to_urn",
            sa.String(512),
            nullable=False,
            comment="Target entity URN",
        ),
        sa.Column(
            "edge_type",
            sa.String(50),
            nullable=False,
            comment="Relationship type (belongs_to, references, derived_from, etc.)",
        ),
        sa.Column(
            "direction",
            sa.String(20),
            nullable=False,
            server_default="out",
            comment="Edge direction (out, in, bidirectional)",
        ),
        sa.Column(
            "weight",
            sa.Float(),
            nullable=False,
            server_default="1.0",
            comment="Edge weight for scoring (0.0-1.0)",
        ),
        sa.Column(
            "reason",
            sa.Text(),
            nullable=True,
            comment="Human-readable reason for the relationship",
        ),
        sa.Column(
            "via",
            sa.String(50),
            nullable=True,
            comment="Binding category (api, ui, data, etc.)",
        ),
        sa.Column(
            "evidence",
            JSONB(),
            nullable=True,
            comment="Additional evidence/metadata",
        ),
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
    )

    # Create indexes for efficient traversal
    op.create_index(
        "idx_graph_edges_from_urn",
        "graph_edges",
        ["from_urn"],
    )
    op.create_index(
        "idx_graph_edges_to_urn",
        "graph_edges",
        ["to_urn"],
    )
    op.create_index(
        "idx_graph_edges_edge_type",
        "graph_edges",
        ["edge_type"],
    )

    # Composite indexes for common traversal patterns
    op.create_index(
        "idx_graph_edges_from_type",
        "graph_edges",
        ["from_urn", "edge_type"],
    )
    op.create_index(
        "idx_graph_edges_to_type",
        "graph_edges",
        ["to_urn", "edge_type"],
    )

    # Unique constraint for deduplication
    op.create_unique_constraint(
        "uq_graph_edges_from_to_type_direction",
        "graph_edges",
        ["from_urn", "to_urn", "edge_type", "direction"],
    )


def downgrade() -> None:
    """Drop graph_edges table and all related objects."""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Check if table exists before dropping
    existing_tables = inspector.get_table_names()
    if "graph_edges" not in existing_tables:
        return

    # Drop unique constraint
    op.drop_constraint(
        "uq_graph_edges_from_to_type_direction",
        "graph_edges",
        type_="unique",
    )

    # Drop indexes
    op.drop_index("idx_graph_edges_to_type", table_name="graph_edges")
    op.drop_index("idx_graph_edges_from_type", table_name="graph_edges")
    op.drop_index("idx_graph_edges_edge_type", table_name="graph_edges")
    op.drop_index("idx_graph_edges_to_urn", table_name="graph_edges")
    op.drop_index("idx_graph_edges_from_urn", table_name="graph_edges")

    # Drop table
    op.drop_table("graph_edges")
