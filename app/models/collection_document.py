"""Explicit collection context for documents that need not have chunks yet."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey

from app.core.database import Base
from app.models.types import GUID


class CollectionDocument(Base):
    __tablename__ = "collection_documents"

    collection_id = Column(GUID(), ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    added_at = Column(DateTime, nullable=False, default=datetime.utcnow)
