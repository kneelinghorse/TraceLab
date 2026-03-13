"""Report and ReportSource models for persisted synthesis outputs."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.types import GUID


class Report(Base):
    """A persisted synthesis output - the knowledge artifacts TraceLab generates."""

    __tablename__ = "reports"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        GUID(), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    title = Column(String(255), nullable=False)
    report_type = Column(String(50), nullable=False, default="summary")
    prompt = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    parent_id = Column(
        GUID(), ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )
    status = Column(String(20), nullable=False, default="draft")
    tokens_used = Column(Integer, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by = Column(
        String(100), nullable=True, comment="Agent or user who created this report"
    )

    # Relationships
    project = relationship("Project", lazy="joined")
    parent = relationship("Report", remote_side=[id], lazy="select")
    sources = relationship(
        "ReportSource",
        back_populates="report",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_reports_project_id", "project_id"),
        Index("ix_reports_status", "status"),
        Index("ix_reports_created_at", "created_at"),
        {"extend_existing": True},
    )


class ReportSource(Base):
    """Tracks the sources (collections or chunks) used to generate a report."""

    __tablename__ = "report_sources"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    report_id = Column(
        GUID(), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    source_type = Column(String(20), nullable=False)  # 'collection' or 'chunk'
    source_id = Column(GUID(), nullable=False)
    added_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    report = relationship("Report", back_populates="sources")

    __table_args__ = (
        Index("ix_report_sources_report_id", "report_id"),
        Index("ix_report_sources_source_type_source_id", "source_type", "source_id"),
        {"extend_existing": True},
    )
