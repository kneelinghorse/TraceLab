"""Project-scoped evidence ledger models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.types import GUID, CrossDBJSON


class LedgerSource(Base):
    """A canonical project-local URL cited by one or more ledger entries."""

    __tablename__ = "ledger_sources"

    id: Any = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Any = Column(
        GUID(),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_url = Column(Text, nullable=False)
    source_url_hash = Column(String(64), nullable=False)
    sighting_count = Column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    first_seen_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    last_seen_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    entries = relationship("LedgerEntry", back_populates="source")

    __table_args__ = (
        CheckConstraint(
            "length(trim(source_url)) > 0",
            name="ck_ledger_sources_nonempty_url",
        ),
        CheckConstraint(
            "length(source_url_hash) = 64",
            name="ck_ledger_sources_hash_length",
        ),
        CheckConstraint(
            "sighting_count > 0",
            name="ck_ledger_sources_positive_sightings",
        ),
        UniqueConstraint(
            "project_id",
            "source_url_hash",
            name="uq_ledger_sources_project_url_hash",
        ),
        UniqueConstraint(
            "id",
            "project_id",
            name="uq_ledger_sources_id_project",
        ),
        Index(
            "ix_ledger_sources_project_last_seen",
            "project_id",
            "last_seen_at",
        ),
    )


class LedgerEntry(Base):
    """A source-backed claim captured during a research session."""

    __tablename__ = "ledger_entries"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    mission_id = Column(GUID(), ForeignKey("missions.id", ondelete="SET NULL"), nullable=True)
    session_key = Column(String(255), nullable=False)
    origin = Column(
        String(32),
        nullable=False,
        default="mcp-agent",
        server_default="mcp-agent",
    )
    claim = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    source_url = Column(Text, nullable=False)
    source_id: Any = Column(
        GUID(),
        nullable=False,
    )
    snippet = Column(Text, nullable=True)
    query = Column(Text, nullable=True)
    disposition = Column(String(32), nullable=False)
    tags = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    workspace_id = Column(GUID(), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    source = relationship(
        "LedgerSource",
        back_populates="entries",
        lazy="joined",
    )

    @property
    def source_sighting_count(self) -> int:
        """Return the current project-local sighting count for this source."""
        if self.source is None:
            raise RuntimeError(f"Ledger entry {self.id} has no canonical source")
        return int(self.source.sighting_count)

    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "project_id"],
            ["ledger_sources.id", "ledger_sources.project_id"],
            name="fk_ledger_entries_source_project",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "origin IN ('mcp-agent', 'deepsearch-worker')",
            name="ck_ledger_entries_origin",
        ),
        CheckConstraint(
            "disposition IN ('supporting', 'contradicting', 'rejected', 'background')",
            name="ck_ledger_entries_disposition",
        ),
        CheckConstraint(
            "length(trim(session_key)) > 0",
            name="ck_ledger_entries_nonempty_session",
        ),
        CheckConstraint(
            "length(trim(claim)) > 0",
            name="ck_ledger_entries_nonempty_claim",
        ),
        CheckConstraint(
            "length(trim(source_url)) > 0",
            name="ck_ledger_entries_nonempty_source_url",
        ),
        Index("ix_ledger_entries_project_created", "project_id", "created_at"),
        Index(
            "ix_ledger_entries_project_session_created",
            "project_id",
            "session_key",
            "created_at",
        ),
        Index(
            "ix_ledger_entries_project_mission_created",
            "project_id",
            "mission_id",
            "created_at",
        ),
        Index(
            "ix_ledger_entries_workspace_owner_created",
            "workspace_id",
            "owner_id",
            "created_at",
        ),
        Index(
            "ix_ledger_entries_source_created",
            "source_id",
            "created_at",
        ),
    )


class LedgerNote(Base):
    """A keyed working note captured during a research session."""

    __tablename__ = "ledger_notes"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    mission_id = Column(GUID(), ForeignKey("missions.id", ondelete="SET NULL"), nullable=True)
    session_key = Column(String(255), nullable=False)
    note_key = Column(String(100), nullable=False)
    origin = Column(
        String(32),
        nullable=False,
        default="mcp-agent",
        server_default="mcp-agent",
    )
    content = Column(Text, nullable=False)
    tags = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    workspace_id = Column(GUID(), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "origin IN ('mcp-agent', 'deepsearch-worker')",
            name="ck_ledger_notes_origin",
        ),
        CheckConstraint(
            "length(trim(session_key)) > 0",
            name="ck_ledger_notes_nonempty_session",
        ),
        CheckConstraint(
            "length(trim(note_key)) > 0",
            name="ck_ledger_notes_nonempty_key",
        ),
        CheckConstraint(
            "length(trim(content)) > 0",
            name="ck_ledger_notes_nonempty_content",
        ),
        UniqueConstraint(
            "project_id",
            "session_key",
            "note_key",
            name="uq_ledger_notes_project_session_key",
        ),
        Index(
            "ix_ledger_notes_project_session_updated",
            "project_id",
            "session_key",
            "updated_at",
        ),
        Index(
            "ix_ledger_notes_project_mission_updated",
            "project_id",
            "mission_id",
            "updated_at",
        ),
        Index(
            "ix_ledger_notes_workspace_owner_updated",
            "workspace_id",
            "owner_id",
            "updated_at",
        ),
    )
