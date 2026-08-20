"""Project-scoped evidence ledger models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)

from app.core.database import Base
from app.models.types import GUID, CrossDBJSON


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

    __table_args__ = (
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
