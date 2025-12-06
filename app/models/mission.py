"""Mission model with DeepSearch-compatible schema.

This model supports Mission Protocol missions with explicit fields for:
- Core mission definition (mission_id, title, objective, success_criteria)
- Optional mission structure (context, deliverables, research_phases, tags)
- Execution tracking (status, timestamps, deepsearch_job_id)
- Results storage (documents, reports, markdown, protocol)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.types import GUID


# Valid mission statuses
MISSION_STATUSES = frozenset({
    "draft",
    "queued",
    "in_progress",
    "completed",
    "blocked",
    "cancelled",
})


class Mission(Base):
    """Mission entity for DeepSearch integration and Mission Protocol workflows.

    A Mission represents a research task that can be executed by DeepSearch
    or tracked manually. It includes:
    - Core definition: what needs to be done and how success is measured
    - Execution state: when it was queued, started, completed
    - Results: document IDs, report links, markdown output
    """

    __tablename__ = "missions"

    # Primary key
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        GUID(),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # DeepSearch Required Fields
    mission_id = Column(
        String(50),
        nullable=False,
        unique=True,
        comment="Human-readable mission identifier (e.g., B16.1)",
    )
    title = Column(
        String(255),
        nullable=False,
        comment="Mission title (3-255 characters)",
    )
    objective = Column(
        Text,
        nullable=False,
        comment="What this mission aims to achieve",
    )
    success_criteria = Column(
        JSON,
        nullable=False,
        comment="Array of measurable success conditions",
    )

    # DeepSearch Optional Fields
    context = Column(
        JSON,
        default=dict,
        comment="Additional context object for the mission",
    )
    deliverables = Column(
        JSON,
        default=list,
        comment="Array of expected deliverables",
    )
    research_phases = Column(
        JSON,
        default=dict,
        comment="Research phase configuration",
    )
    tags = Column(
        JSON,
        default=list,
        comment="Array of tags for categorization",
    )
    mission_metadata = Column(
        JSON,
        default=dict,
        comment="Arbitrary metadata object",
    )

    # Execution Tracking
    status = Column(
        String(20),
        default="draft",
        nullable=False,
        index=True,
        comment="Mission lifecycle status",
    )
    queued_at = Column(
        DateTime,
        nullable=True,
        comment="When the mission was queued for execution",
    )
    started_at = Column(
        DateTime,
        nullable=True,
        comment="When execution began",
    )
    completed_at = Column(
        DateTime,
        nullable=True,
        comment="When execution finished",
    )
    deepsearch_job_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="DeepSearch job ID for tracking async execution",
    )

    # Results
    execution_metadata = Column(
        JSON,
        default=dict,
        comment="Execution metrics and debugging info",
    )
    result_document_ids = Column(
        JSON,
        default=list,
        comment="Array of document UUIDs produced by this mission",
    )
    result_report_id = Column(
        GUID(),
        ForeignKey("reports.id", ondelete="SET NULL"),
        nullable=True,
        comment="Primary report generated from mission results",
    )
    result_markdown = Column(
        Text,
        nullable=True,
        comment="Raw markdown output from mission execution",
    )
    result_protocol = Column(
        JSON,
        nullable=True,
        comment="Mission Protocol compliant result object",
    )
    error_message = Column(
        Text,
        nullable=True,
        comment="Error details if mission failed",
    )

    # Housekeeping
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    created_by = Column(
        String(100),
        nullable=True,
        comment="Agent or user who created this mission",
    )

    # Relationships
    project = relationship("Project", backref="missions")
    result_report = relationship("Report", lazy="joined")

    __table_args__ = (
        # Ensure success_criteria is a non-empty array
        # PostgreSQL: Check JSONB array length
        # SQLite: Check JSON array via json_array_length
        CheckConstraint(
            """
            (
                CASE
                    WHEN json_type(success_criteria) = 'array'
                    THEN json_array_length(success_criteria) > 0
                    ELSE jsonb_array_length(success_criteria) > 0
                END
            )
            """,
            name="success_criteria_not_empty",
        ),
        # Title length constraint
        CheckConstraint(
            "length(title) >= 3 AND length(title) <= 255",
            name="title_length",
        ),
        # Valid status values
        CheckConstraint(
            "status IN ('draft', 'queued', 'in_progress', 'completed', 'blocked', 'cancelled')",
            name="valid_mission_status",
        ),
        # Composite index for project + status queries
        Index("idx_missions_project_status", "project_id", "status"),
        # Index for mission_id lookups
        Index("idx_missions_mission_id", "mission_id"),
        {"extend_existing": True},
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert mission to dictionary representation."""
        return {
            "id": str(self.id) if self.id else None,
            "project_id": str(self.project_id) if self.project_id else None,
            "mission_id": self.mission_id,
            "title": self.title,
            "objective": self.objective,
            "success_criteria": self.success_criteria or [],
            "context": self.context or {},
            "deliverables": self.deliverables or [],
            "research_phases": self.research_phases or {},
            "tags": self.tags or [],
            "metadata": self.mission_metadata or {},
            "status": self.status,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "deepsearch_job_id": self.deepsearch_job_id,
            "execution_metadata": self.execution_metadata or {},
            "result_document_ids": self.result_document_ids or [],
            "result_report_id": str(self.result_report_id) if self.result_report_id else None,
            "result_markdown": self.result_markdown,
            "result_protocol": self.result_protocol,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
        }

    def to_mission_protocol(self) -> Dict[str, Any]:
        """Convert to Mission Protocol format for DeepSearch submission."""
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "objective": self.objective,
            "success_criteria": self.success_criteria or [],
            "context": self.context or {},
            "deliverables": self.deliverables or [],
            "research_phases": self.research_phases or {},
            "tags": self.tags or [],
            "metadata": self.mission_metadata or {},
        }

    @classmethod
    def from_mission_protocol(
        cls,
        protocol: Dict[str, Any],
        project_id: Optional[uuid.UUID] = None,
        created_by: Optional[str] = None,
    ) -> "Mission":
        """Create a Mission from a Mission Protocol definition."""
        return cls(
            project_id=project_id,
            mission_id=protocol["mission_id"],
            title=protocol["title"],
            objective=protocol["objective"],
            success_criteria=protocol["success_criteria"],
            context=protocol.get("context", {}),
            deliverables=protocol.get("deliverables", []),
            research_phases=protocol.get("research_phases", {}),
            tags=protocol.get("tags", []),
            mission_metadata=protocol.get("metadata", {}),
            created_by=created_by,
        )
