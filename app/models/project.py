"""Project model."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text

from app.core.database import Base
from app.models.mixins import SoftDeleteMixin
from app.models.types import GUID


class Project(Base, SoftDeleteMixin):
    """Project entity representing a research project.

    Supports soft delete via SoftDeleteMixin - records are not permanently
    deleted but marked with deleted_at timestamp. Use project.soft_delete()
    and project.restore() methods.
    """

    __tablename__ = "projects"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text)
    user_id = Column(GUID())  # Placeholder for auth
    mission_protocol_id = Column(GUID())  # References missions table

    # Ownership + tenancy (Sprint 43 RBAC foundation; additive, nullable, unread until Sprint C)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    workspace_id = Column(GUID(), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)

    # Metadata
    research_type = Column(
        String
    )  # 'strategic' | 'tactical' | 'generative' | 'evaluative'
    methodology = Column(String)  # 'qualitative' | 'quantitative' | 'mixed'
    status = Column(String, default="active")  # 'active' | 'archived' | 'completed'

    # Quality tracking
    quality_score = Column(Integer)  # 0-100
    last_quality_check = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "research_type IS NULL OR research_type IN ('strategic', 'tactical', 'generative', 'evaluative')",
            name="valid_research_type",
        ),
        Index("ix_projects_workspace_owner_created_at", "workspace_id", "owner_id", "created_at"),
    )
