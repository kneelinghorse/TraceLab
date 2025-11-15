"""Document chunk model for RAG."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.types import GUID, TSVector


class DocumentChunk(Base):
    """Document chunk entity for RAG embeddings."""
    __tablename__ = "document_chunks"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    content_tsv = Column(TSVector(), nullable=False)
    
    # RAG metadata
    embedding_id = Column(String)  # Reference to vector DB ID
    token_count = Column(Integer)
    start_char = Column(Integer)
    end_char = Column(Integer)
    
    # Context preservation
    prev_chunk_id = Column(GUID(), ForeignKey("document_chunks.id"))
    next_chunk_id = Column(GUID(), ForeignKey("document_chunks.id"))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    __table_args__ = (
        Index("idx_document_chunks_document_id", "document_id"),
        Index("idx_document_chunks_embedding_id", "embedding_id"),
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
        {'extend_existing': True},
    )
