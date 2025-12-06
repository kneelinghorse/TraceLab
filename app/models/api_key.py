"""API Key model for service authentication."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Index
from app.core.database import Base
from app.models.types import GUID


class APIKey(Base):
    """API Key entity for authenticating MCP servers and automated scripts."""

    __tablename__ = "api_keys"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, default="default")  # For future multi-user support
    name = Column(String(255), nullable=False)  # Human label like "MCP Server"
    key_hash = Column(String(255), nullable=False)  # bcrypt hash of full key
    key_prefix = Column(String(12), nullable=False)  # First 8 chars after prefix for display (tl_a1b2c3d4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)  # Updated on successful auth
    expires_at = Column(DateTime, nullable=True)  # null = never expires

    __table_args__ = (
        Index("ix_api_keys_user_id", "user_id"),
        Index("ix_api_keys_key_prefix", "key_prefix"),
    )
