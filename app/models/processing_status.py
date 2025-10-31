"""Document processing status audit model."""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.types import GUID


class DocumentProcessingStatus(Base):
    """Audit trail entry for document ingestion stages."""

    __tablename__ = "document_processing_statuses"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    stage = Column(String, nullable=False)  # uploaded | extracted | redacted | chunked | pipeline
    status = Column(String, nullable=False)  # in_progress | succeeded | failed
    message = Column(Text)
    details = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="processing_events")

    __table_args__ = (
        {},
    )
