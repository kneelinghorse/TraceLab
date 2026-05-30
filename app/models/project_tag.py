"""ProjectTag model: many-to-many junction for cross-cutting project themes.

Sprint 44 (T44.2). Links a project to an existing tag (reusing the tags table,
category='theme') so themes can span projects without project nesting
(architecture locked 2026-05-28, decision #196). Mirrors DocumentTag. Additive
and dormant — nothing reads it yet.
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.types import GUID


class ProjectTag(Base):
    """Junction table for projects and tags (cross-cutting themes)."""

    __tablename__ = "project_tags"

    project_id = Column(
        GUID(), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id = Column(GUID(), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    # project<->Project.tags is bidirectional (mission requires Project.tags);
    # the tag side is forward-only (no Tag.project_tags) to avoid editing Tag,
    # mirroring CollectionItem.chunk and SpaceMember (decision #229).
    project = relationship("Project", back_populates="tags")
    tag = relationship("Tag")

    __table_args__ = (Index("ix_project_tags_tag_id", "tag_id"),)
