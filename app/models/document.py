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
    Numeric,
    ForeignKey,
    LargeBinary,
    Index,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.types import GUID


class Document(Base):
    """Document entity representing uploaded research documents."""
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
    )
