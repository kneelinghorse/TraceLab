"""SQLAlchemy model for API idempotency records."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, JSON, Text

from app.core.database import Base


class IdempotencyRecord(Base):
    """Persist cached responses for idempotent API operations."""

    __tablename__ = "idempotency_records"

    key = Column(String(255), primary_key=True)
    method = Column(String(16), nullable=False)
    path = Column(String(255), nullable=False)
    request_hash = Column(String(128), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_data = Column(JSON, nullable=False)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
