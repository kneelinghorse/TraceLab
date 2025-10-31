"""Mission model for Mission Protocol integration."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from app.core.database import Base
from app.models.types import GUID


class Mission(Base):
    """Mission entity storing Mission Protocol YAML structures."""
    __tablename__ = "missions"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID(), ForeignKey("projects.id", ondelete="CASCADE"))
    
    # Mission Protocol fields (stored as JSONB for flexibility)
    mission_data = Column(JSON, nullable=False)  # Full Mission Protocol YAML structure
    
    # Quality gates tracking
    quality_gates = Column(JSON)  # {
    #   "research_statement": {"status": "complete", "validated": true},
    #   "evidence_links": {"status": "complete", "validated": false},
    #   "contradictions_resolved": {"status": "pending"}
    # }
    
    # Progress tracking
    status = Column(String, default='draft')  # 'draft' | 'in_progress' | 'review' | 'complete'
    completion_percentage = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
