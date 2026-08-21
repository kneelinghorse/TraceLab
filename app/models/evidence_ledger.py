"""Project-scoped evidence ledger models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
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


class DeepSearchLedgerBatch(Base):
    """One atomically claimed DeepSearch-to-ledger projection batch."""

    __tablename__ = "deepsearch_ledger_batches"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    mission_id = Column(
        GUID(),
        ForeignKey(
            "missions.id",
            name="fk_deepsearch_ledger_batches_mission",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    deepsearch_job_id = Column(String(100), nullable=False)
    session_key = Column(String(255), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    entry_count = Column(Integer, nullable=False)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    entries = relationship("LedgerEntry", back_populates="deepsearch_batch")

    __table_args__ = (
        CheckConstraint(
            "length(trim(deepsearch_job_id)) > 0",
            name="ck_deepsearch_ledger_batches_nonempty_job",
        ),
        CheckConstraint(
            "length(trim(session_key)) > 0",
            name="ck_deepsearch_ledger_batches_nonempty_session",
        ),
        CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_deepsearch_ledger_batches_hash_length",
        ),
        CheckConstraint(
            "entry_count > 0 AND entry_count <= 1000",
            name="ck_deepsearch_ledger_batches_entry_count",
        ),
        UniqueConstraint(
            "mission_id",
            "deepsearch_job_id",
            name="uq_deepsearch_ledger_batches_mission_job",
        ),
        Index(
            "ix_deepsearch_ledger_batches_mission_created",
            "mission_id",
            "created_at",
        ),
    )


class DeepSearchEvidenceOutbox(Base):
    """Durable terminal-result delivery state owned by DeepSearch."""

    __tablename__ = "deepsearch_evidence_outbox"

    mission_id = Column(
        GUID(),
        ForeignKey(
            "missions.id",
            name="fk_deepsearch_evidence_outbox_mission",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    deepsearch_job_id = Column(String(100), primary_key=True)
    deepsearch_result_key = Column(Text, nullable=False)
    mission_attempt_count = Column(Integer, nullable=False)
    terminal_status = Column(String(32), nullable=False)
    schema_version = Column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    state = Column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    delivery_attempt_count = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    next_attempt_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    lease_token = Column(GUID(), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    acked_at = Column(DateTime(timezone=True), nullable=True)
    last_http_status = Column(SmallInteger, nullable=True)
    last_error_code = Column(String(100), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "mission_id",
            "deepsearch_job_id",
            name="pk_deepsearch_evidence_outbox",
        ),
        CheckConstraint(
            "length(trim(deepsearch_job_id)) > 0",
            name="ck_deepsearch_evidence_outbox_nonempty_job",
        ),
        CheckConstraint(
            "length(trim(deepsearch_result_key)) > 0",
            name="ck_deepsearch_evidence_outbox_nonempty_result_key",
        ),
        CheckConstraint(
            "mission_attempt_count > 0",
            name="ck_deepsearch_evidence_outbox_positive_attempt",
        ),
        CheckConstraint(
            "terminal_status IN ('completed', 'validation_failed')",
            name="ck_deepsearch_evidence_outbox_terminal_status",
        ),
        CheckConstraint(
            "schema_version = 1",
            name="ck_deepsearch_evidence_outbox_schema_version",
        ),
        CheckConstraint(
            "state IN ('pending', 'leased', 'acked', 'dead_letter')",
            name="ck_deepsearch_evidence_outbox_state",
        ),
        CheckConstraint(
            "delivery_attempt_count >= 0",
            name="ck_deepsearch_evidence_outbox_delivery_attempts",
        ),
        CheckConstraint(
            "last_http_status IS NULL OR (last_http_status >= 100 AND last_http_status <= 599)",
            name="ck_deepsearch_evidence_outbox_http_status",
        ),
        CheckConstraint(
            "(state = 'leased' AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL "
            "AND next_attempt_at = lease_expires_at AND acked_at IS NULL) OR "
            "(state = 'acked' AND lease_token IS NULL "
            "AND lease_expires_at IS NULL AND acked_at IS NOT NULL) OR "
            "(state IN ('pending', 'dead_letter') AND lease_token IS NULL "
            "AND lease_expires_at IS NULL AND acked_at IS NULL)",
            name="ck_deepsearch_evidence_outbox_state_coherence",
        ),
        Index(
            "ix_deepsearch_evidence_outbox_delivery",
            "state",
            "next_attempt_at",
            "created_at",
        ),
    )


class LedgerEntry(Base):
    """A source-backed claim captured during a research session."""

    __tablename__ = "ledger_entries"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    mission_id = Column(GUID(), ForeignKey("missions.id", ondelete="SET NULL"), nullable=True)
    deepsearch_batch_id = Column(
        GUID(),
        ForeignKey(
            "deepsearch_ledger_batches.id",
            name="fk_ledger_entries_deepsearch_batch",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
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
    deepsearch_batch = relationship(
        "DeepSearchLedgerBatch",
        back_populates="entries",
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
        Index(
            "ix_ledger_entries_deepsearch_batch_created",
            "deepsearch_batch_id",
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
