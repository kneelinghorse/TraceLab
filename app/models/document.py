"""Document model."""
import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Boolean,
    BigInteger,
    DateTime,
    Date,
    JSON,
    Numeric,
    ForeignKey,
    LargeBinary,
    Index,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.types import GUID
from app.models.mixins import SoftDeleteMixin


class Document(Base, SoftDeleteMixin):
    """Document entity representing uploaded research documents.

    Supports soft delete via SoftDeleteMixin - records are not permanently
    deleted but marked with deleted_at timestamp. Use document.soft_delete()
    and document.restore() methods.
    """
    __tablename__ = "documents"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    file_path = Column(String)
    file_type = Column(String)  # 'transcript' | 'survey' | 'notes' | 'report' | 'video' | 'audio'
    content = Column(Text)  # Extracted text content
    raw_content = Column(LargeBinary)  # Original file (optional, for binary)
    
    # Metadata
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    file_size = Column(BigInteger)
    mime_type = Column(String)
    
    # Source attribution
    source_type = Column(String)  # 'interview' | 'survey' | 'observation' | 'analysis'
    participant_count = Column(Integer)
    collection_date = Column(Date)
    
    # Processing status
    processed = Column(Boolean, default=False)
    chunked = Column(Boolean, default=False)
    embedded = Column(Boolean, default=False)
    
    # Quality metadata
    transcription_accuracy = Column(Numeric(3, 2))  # If AI-transcribed
    validation_status = Column(String, default='pending')  # 'pending' | 'validated' | 'flagged'

    # Provenance metadata (for auto-ingested documents)
    document_metadata = Column(JSON, default=dict, comment="Arbitrary metadata for document provenance")

    # Report promotion provenance
    source_report_id = Column(
        GUID(),
        ForeignKey("reports.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID of source report if promoted from synthesis",
    )
    source_mission_id = Column(
        GUID(),
        ForeignKey("missions.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID of source mission if promoted from mission report",
    )
    source_origin = Column(
        String(20),
        default="upload",
        comment="Origin type: upload, synthesized, imported",
    )
    
    # Relationships
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    tags = relationship("DocumentTag", back_populates="document", cascade="all, delete-orphan")
    processing_events = relationship(
        "DocumentProcessingStatus",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentProcessingStatus.created_at"
    )

    __table_args__ = (
        Index("idx_documents_project_id", "project_id"),
        Index("ix_documents_file_type", "file_type"),
        Index("ix_documents_source_type", "source_type"),
        Index("ix_documents_collection_date", "collection_date"),
        Index("idx_documents_source_origin", "source_origin"),
    )
