"""Mission model for Mission Protocol integration."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, CheckConstraint, Index
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings
from app.models.types import GUID
from app.services.mission_protocol_validation import build_mission_data_check_constraint


def _mission_constraint_sql() -> str:
    """Return the backend-specific constraint SQL for mission_data."""
    db_url = settings.database_url.lower()
    backend = "sqlite" if db_url.startswith("sqlite") else "postgresql"
    return build_mission_data_check_constraint(backend=backend)


class Mission(Base):
    """Mission entity storing Mission Protocol YAML structures."""
    __tablename__ = "missions"
    __table_args__ = (
        CheckConstraint(
            _mission_constraint_sql(),
            name="missions_mission_data_check",
        ),
        Index("idx_missions_project_status", "project_id", "status"),
    )
    
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
    evidence_linking_metadata = Column(JSON, nullable=True)
    
    # Progress tracking
    status = Column(String, default='draft')  # 'draft' | 'in_progress' | 'review' | 'complete'
    completion_percentage = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project", backref="missions")
