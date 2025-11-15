"""Insight and insight-source models."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.types import GUID


class Insight(Base):
    """Insight entity for synthesized findings."""
    __tablename__ = "insights"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    insight_type = Column(String)  # 'finding' | 'contradiction' | 'surprising' | 'recommendation'
    
    # Traceability
    created_by = Column(String, default='human')  # 'human' | 'ai' | 'human_validated_ai'
    validated = Column(Boolean, default=False)
    validation_date = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sources = relationship("InsightSource", back_populates="insight", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_insights_project_id", "project_id"),
    )


class InsightSource(Base):
    """Junction table for insights and source chunks."""
    __tablename__ = "insight_sources"
    
    insight_id = Column(GUID(), ForeignKey("insights.id", ondelete="CASCADE"), primary_key=True)
    chunk_id = Column(GUID(), ForeignKey("document_chunks.id", ondelete="CASCADE"), primary_key=True)
    relevance_score = Column(Numeric(3, 2))  # How relevant this chunk is to the insight
    
    # Relationships
    insight = relationship("Insight", back_populates="sources")

    __table_args__ = (
        Index("idx_insight_sources_chunk_id", "chunk_id"),
    )
