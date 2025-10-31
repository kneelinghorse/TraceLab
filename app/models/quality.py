"""Quality check model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, ARRAY, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class QualityCheck(Base):
    """Quality audit trail entity."""
    __tablename__ = "quality_checks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False)  # 'document' | 'insight' | 'mission' | 'project'
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    
    check_type = Column(String, nullable=False)  # 'bias_detection' | 'traceability' | 'rigor' | 'synthesis_quality'
    status = Column(String, nullable=False)  # 'passed' | 'failed' | 'warning'
    
    details = Column(JSONB)  # Check-specific data
    recommendations = Column(ARRAY(String))  # Array of improvement suggestions
    
    performed_by = Column(String)  # User ID or 'system'
    performed_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_quality_checks_entity', 'entity_type', 'entity_id'),
    )

