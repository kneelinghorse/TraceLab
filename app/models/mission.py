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
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.types import GUID, CrossDBJSON

# Valid mission statuses
# 'validation_failed' is a terminal fail-closed outcome distinct from 'blocked':
# the mission synthesized output but failed coverage/structural gates. Reviewers
# treat these as reviewable artifacts, not infra failures.
MISSION_STATUSES = frozenset(
    {
        "draft",
        "queued",
        "in_progress",
        "completed",
        "blocked",
        "cancelled",
        "validation_failed",
    }
)


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
        CrossDBJSON,
        nullable=False,
        comment="Array of measurable success conditions",
    )

    # DeepSearch Optional Fields
    context = Column(
        CrossDBJSON,
        default=dict,
        comment="Additional context object for the mission",
    )
    deliverables = Column(
        CrossDBJSON,
        default=list,
        comment="Array of expected deliverables",
    )
    research_phases = Column(
        CrossDBJSON,
        default=dict,
        comment="Research phase configuration",
    )
    tags = Column(
        CrossDBJSON,
        default=list,
        comment="Array of tags for categorization",
    )
    mission_metadata = Column(
        CrossDBJSON,
        default=dict,
        comment="Arbitrary metadata object",
    )
    # Mission-authoring fields consumed by DeepSearch contract compiler (T40.1).
    # All nullable; see alembic/versions/027_add_mission_authoring_fields.py.
    background = Column(
        Text,
        nullable=True,
        comment="Free-form background prose for the mission",
    )
    focus = Column(
        Text,
        nullable=True,
        comment="Narrow framing for the research question",
    )
    references = Column(
        CrossDBJSON,
        nullable=True,
        comment="Array of {title} reference objects",
    )
    required_entities = Column(
        CrossDBJSON,
        nullable=True,
        comment="Array of entity strings that must appear in results",
    )
    excluded_entities = Column(
        CrossDBJSON,
        nullable=True,
        comment="Array of entity strings that must not appear in results",
    )
    expected_output_schema = Column(
        CrossDBJSON,
        nullable=True,
        comment="DeepSearch OutputSchema describing the expected deliverable shape",
    )
    coverage_thresholds = Column(
        CrossDBJSON,
        nullable=True,
        comment="Dict of coverage gate thresholds",
    )
    validation_thresholds = Column(
        CrossDBJSON,
        nullable=True,
        comment="Dict of validation gate thresholds",
    )
    deliverable_format = Column(
        Text,
        nullable=True,
        comment="Output rendering format hint (e.g. 'markdown report', 'comparison table')",
    )
    max_loops = Column(
        Integer,
        nullable=True,
        comment="Upper bound on DeepSearch research loop count",
    )
    min_loops = Column(
        Integer,
        nullable=True,
        comment="Lower bound on DeepSearch research loop count",
    )
    constraints = Column(
        CrossDBJSON,
        nullable=True,
        comment="Array of constraint strings (promoted from context['constraints'])",
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

    # DeepSearch lease boundary (migration 039). These fields are deliberately
    # internal and are not emitted by ``to_dict``/REST/MCP serializers: the
    # opaque token is the worker's fencing proof, not mission metadata.
    deepsearch_lease_owner = Column(
        Text,
        nullable=True,
        comment="Stable worker instance holding the current lease",
    )
    deepsearch_lease_token = Column(
        Text,
        nullable=True,
        comment="Opaque per-attempt lease ownership proof",
    )
    deepsearch_leased_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the current DeepSearch lease was acquired",
    )
    deepsearch_heartbeat_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last accepted heartbeat from the lease holder",
    )
    deepsearch_lease_expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Lease expiry after which the mission is recoverable",
    )
    deepsearch_attempt_count = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Monotonic number of DeepSearch claim attempts",
    )
    deepsearch_result_key = Column(
        Text,
        nullable=True,
        comment="Stable idempotency key for the terminal lease attempt",
    )

    # Results
    execution_metadata = Column(
        CrossDBJSON,
        default=dict,
        comment="Execution metrics and debugging info",
    )
    result_document_ids = Column(
        CrossDBJSON,
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
        CrossDBJSON,
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

    # Ownership + tenancy (Sprint 43 RBAC foundation; additive, nullable, unread until Sprint C)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    workspace_id = Column(GUID(), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    project = relationship("Project", backref="missions")
    result_report = relationship("Report", lazy="joined")

    __table_args__ = (
        # Ensure success_criteria is a non-empty array
        # PostgreSQL uses jsonb_array_length (success_criteria is stored as CrossDBJSON)
        CheckConstraint(
            "jsonb_array_length(success_criteria) > 0",
            name="success_criteria_not_empty",
        ),
        # Title length constraint
        CheckConstraint(
            "length(title) >= 3 AND length(title) <= 255",
            name="title_length",
        ),
        # Valid status values
        CheckConstraint(
            "status IN ('draft', 'queued', 'in_progress', 'completed', "
            "'blocked', 'cancelled', 'validation_failed')",
            name="valid_mission_status",
        ),
        # Composite index for project + status queries
        Index("idx_missions_project_status", "project_id", "status"),
        # Index for mission_id lookups
        Index("idx_missions_mission_id", "mission_id"),
        Index(
            "missions_deepsearch_lease_token_active_uq",
            "deepsearch_lease_token",
            unique=True,
            postgresql_where=sql_text("deepsearch_lease_token IS NOT NULL"),
            sqlite_where=sql_text("deepsearch_lease_token IS NOT NULL"),
        ),
        Index(
            "missions_deepsearch_result_key_uq",
            "deepsearch_result_key",
            unique=True,
            postgresql_where=sql_text("deepsearch_result_key IS NOT NULL"),
            sqlite_where=sql_text("deepsearch_result_key IS NOT NULL"),
        ),
        Index(
            "missions_deepsearch_claim_scan_idx",
            "status",
            "deepsearch_lease_expires_at",
            "queued_at",
        ),
        Index("ix_missions_workspace_owner_created_at", "workspace_id", "owner_id", "created_at"),
        {"extend_existing": True},
    )

    def to_dict(self) -> dict[str, Any]:
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
            "background": self.background,
            "focus": self.focus,
            "references": self.references,
            "required_entities": self.required_entities,
            "excluded_entities": self.excluded_entities,
            "expected_output_schema": self.expected_output_schema,
            "coverage_thresholds": self.coverage_thresholds,
            "validation_thresholds": self.validation_thresholds,
            "deliverable_format": self.deliverable_format,
            "max_loops": self.max_loops,
            "min_loops": self.min_loops,
            "constraints": self._resolved_constraints(),
            "status": self.status,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "deepsearch_job_id": self.deepsearch_job_id,
            "execution_metadata": self.execution_metadata or {},
            "result_document_ids": self.result_document_ids or [],
            "result_report_id": str(self.result_report_id)
            if self.result_report_id
            else None,
            "result_markdown": self.result_markdown,
            "result_protocol": self.result_protocol,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
        }

    def _resolved_constraints(self) -> list[Any] | None:
        """Constraints column with fallback to context['constraints'].

        Old missions stored constraints inside `context`; T40.1 promoted it to a
        first-class column. During the transition the serializer falls back so
        DeepSearch's existing reader keeps seeing constraints regardless of
        which side the author wrote to.
        """
        if self.constraints:
            return self.constraints
        if isinstance(self.context, dict):
            legacy = self.context.get("constraints")
            if legacy:
                return legacy
        return self.constraints

    def to_mission_protocol(self) -> dict[str, Any]:
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
            "background": self.background,
            "focus": self.focus,
            "references": self.references,
            "required_entities": self.required_entities,
            "excluded_entities": self.excluded_entities,
            "expected_output_schema": self.expected_output_schema,
            "coverage_thresholds": self.coverage_thresholds,
            "validation_thresholds": self.validation_thresholds,
            "deliverable_format": self.deliverable_format,
            "max_loops": self.max_loops,
            "min_loops": self.min_loops,
            "constraints": self._resolved_constraints(),
        }

    @classmethod
    def from_mission_protocol(
        cls,
        protocol: dict[str, Any],
        project_id: uuid.UUID | None = None,
        created_by: str | None = None,
    ) -> Mission:
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
            background=protocol.get("background"),
            focus=protocol.get("focus"),
            references=protocol.get("references"),
            required_entities=protocol.get("required_entities"),
            excluded_entities=protocol.get("excluded_entities"),
            expected_output_schema=protocol.get("expected_output_schema"),
            coverage_thresholds=protocol.get("coverage_thresholds"),
            validation_thresholds=protocol.get("validation_thresholds"),
            deliverable_format=protocol.get("deliverable_format"),
            max_loops=protocol.get("max_loops"),
            min_loops=protocol.get("min_loops"),
            constraints=protocol.get("constraints"),
            created_by=created_by,
        )
