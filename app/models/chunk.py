"""Document chunk model for RAG."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class DocumentChunk(Base):
    """Document chunk entity for RAG embeddings."""
    __tablename__ = "document_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    
    # RAG metadata
    embedding_id = Column(String)  # Reference to vector DB ID
    token_count = Column(Integer)
    start_char = Column(Integer)
    end_char = Column(Integer)
    
    # Context preservation
    prev_chunk_id = Column(UUID(as_uuid=True), ForeignKey("document_chunks.id"))
    next_chunk_id = Column(UUID(as_uuid=True), ForeignKey("document_chunks.id"))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    __table_args__ = (
        {'extend_existing': True},
    )

