"""Tag and taxonomy models."""
import uuid
from sqlalchemy import Column, String, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.types import GUID


class Tag(Base):
    """Tag entity for categorizing documents."""
    __tablename__ = "tags"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    user_id = Column(GUID())  # Placeholder for auth
    category = Column(String)  # 'method' | 'theme' | 'persona' | 'custom'
    color = Column(String)  # Hex color for UI
    parent_id = Column(GUID(), ForeignKey("tags.id"))
    
    # Relationships
    parent = relationship("Tag", remote_side=[id], backref="children")
    document_tags = relationship("DocumentTag", back_populates="tag")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_user_tag'),
    )


class DocumentTag(Base):
    """Junction table for documents and tags."""
    __tablename__ = "document_tags"

    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(GUID(), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    
    # Relationships
    document = relationship("Document", back_populates="tags")
    tag = relationship("Tag", back_populates="document_tags")

    __table_args__ = (
        Index("ix_document_tags_tag_id", "tag_id"),
    )
