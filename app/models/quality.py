"""Quality check model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Index, JSON
from app.core.database import Base
from app.models.types import GUID


class QualityCheck(Base):
    """Quality audit trail entity."""
    __tablename__ = "quality_checks"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False)  # 'document' | 'insight' | 'mission' | 'project'
    entity_id = Column(GUID(), nullable=False)
    
    check_type = Column(String, nullable=False)  # 'bias_detection' | 'traceability' | 'rigor' | 'synthesis_quality'
    status = Column(String, nullable=False)  # 'passed' | 'failed' | 'warning'
    
    details = Column(JSON)  # Check-specific data
    recommendations = Column(JSON)  # List of improvement suggestions
    
    performed_by = Column(String)  # User ID or 'system'
    performed_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_quality_checks_entity', 'entity_type', 'entity_id'),
    )
