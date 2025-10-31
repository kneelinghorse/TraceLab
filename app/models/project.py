"""Project model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class Project(Base):
    """Project entity representing a research project."""
    __tablename__ = "projects"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text)
    user_id = Column(UUID(as_uuid=True))  # Placeholder for auth
    mission_protocol_id = Column(UUID(as_uuid=True))  # References missions table
    
    # Metadata
    research_type = Column(String)  # 'strategic' | 'tactical' | 'generative' | 'evaluative'
    methodology = Column(String)  # 'qualitative' | 'quantitative' | 'mixed'
    status = Column(String, default='active')  # 'active' | 'archived' | 'completed'
    
    # Quality tracking
    quality_score = Column(Integer)  # 0-100
    last_quality_check = Column(DateTime)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint(
            "research_type IS NULL OR research_type IN ('strategic', 'tactical', 'generative', 'evaluative')",
            name='valid_research_type'
        ),
    )

