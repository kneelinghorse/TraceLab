"""GraphEdge model for persisting semantic protocol edges.

This model stores materialized graph edges from the Semantic Protocol v3.3.0
edge schema. Edges connect entities via URNs and support graph traversal
for the PEDR L6 layer.

Sprint 24: PEDR Graph Foundation
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    String,
    Text,
    UniqueConstraint,
)

from app.core.database import Base
from app.models.types import GUID, CrossDBJSON


class GraphEdge(Base):
    """Materialized graph edge for PEDR L6 layer.

    Stores edges from Semantic Protocol manifests and FK-derived relationships.
    Indexes support efficient BFS traversal for graph search.

    Attributes:
        id: Unique edge identifier (UUID)
        from_urn: Source entity URN (e.g., urn:research:mission:B24.1)
        to_urn: Target entity URN (e.g., urn:research:chunk:abc-123)
        edge_type: Relationship type (belongs_to, references, derived_from, etc.)
        direction: Edge direction (out, in, bidirectional)
        weight: Edge weight for scoring (0.0-1.0, default 1.0)
        reason: Human-readable reason for the relationship
        via: Binding category that created this edge (api, ui, data, etc.)
        evidence: Additional evidence/metadata (JSONB)
        created_at: When the edge was created
        updated_at: When the edge was last updated
    """

    __tablename__ = "graph_edges"

    # Primary key
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    # URN endpoints
    from_urn = Column(
        String(512),
        nullable=False,
        index=True,
        comment="Source entity URN",
    )
    to_urn = Column(
        String(512),
        nullable=False,
        index=True,
        comment="Target entity URN",
    )

    # Edge metadata
    edge_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Relationship type (belongs_to, references, derived_from, etc.)",
    )
    direction = Column(
        String(20),
        nullable=False,
        default="out",
        comment="Edge direction (out, in, bidirectional)",
    )
    weight = Column(
        Float,
        nullable=False,
        default=1.0,
        comment="Edge weight for scoring (0.0-1.0)",
    )

    # Optional metadata
    reason = Column(
        Text,
        nullable=True,
        comment="Human-readable reason for the relationship",
    )
    via = Column(
        String(50),
        nullable=True,
        comment="Binding category (api, ui, data, etc.)",
    )
    evidence = Column(
        CrossDBJSON,
        nullable=True,
        comment="Additional evidence/metadata",
    )

    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Composite unique constraint for deduplication
    __table_args__ = (
        UniqueConstraint(
            "from_urn",
            "to_urn",
            "edge_type",
            "direction",
            name="uq_graph_edges_from_to_type_direction",
        ),
        # Composite index for traversal queries
        Index("idx_graph_edges_from_type", "from_urn", "edge_type"),
        Index("idx_graph_edges_to_type", "to_urn", "edge_type"),
    )

    def __repr__(self) -> str:
        return f"<GraphEdge {self.edge_type}: {self.from_urn} -> {self.to_urn}>"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        result = {
            "id": str(self.id),
            "from_urn": self.from_urn,
            "to_urn": self.to_urn,
            "edge_type": self.edge_type,
            "direction": self.direction,
            "weight": self.weight,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if self.reason:
            result["reason"] = self.reason
        if self.via:
            result["via"] = self.via
        if self.evidence:
            result["evidence"] = self.evidence
        return result

    @classmethod
    def from_semantic_edge(
        cls,
        edge_type: str,
        from_urn: str,
        to_urn: str,
        direction: str = "out",
        weight: float = 1.0,
        reason: str | None = None,
        via: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> GraphEdge:
        """Create GraphEdge from Semantic Protocol Edge data.

        Args:
            edge_type: Relationship type
            from_urn: Source URN
            to_urn: Target URN
            direction: Edge direction
            weight: Edge weight
            reason: Optional reason
            via: Optional binding category
            evidence: Optional evidence dict

        Returns:
            GraphEdge instance (not yet persisted)
        """
        return cls(
            from_urn=from_urn,
            to_urn=to_urn,
            edge_type=edge_type,
            direction=direction,
            weight=weight,
            reason=reason,
            via=via,
            evidence=evidence,
        )

    @property
    def normalization_key(self) -> str:
        """Generate key for edge deduplication.

        Matches the Semantic Protocol Edge normalization key.
        """
        return f"{self.edge_type}|{self.from_urn}|{self.to_urn}|{self.direction}"
