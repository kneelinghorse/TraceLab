"""SpaceMember model: the access grant linking a user to a Space (workspace).

Sprint 44 (T44.1). Additive and dormant — nothing reads space_members yet. The
membership lookup (authorization._has_space_membership) lands in T44.3 and stays
behind rbac_enabled=OFF until Sprint C, so day-one behavior is byte-identical.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.types import GUID


class SpaceMember(Base):
    """Membership grant: a user belongs to a Space (workspace).

    The access-grant unit for the RBAC system (architecture locked 2026-05-28,
    decision #196). Membership *presence* is what grants access via downward
    inheritance (project_id -> space_id, implemented in T44.3); the ``role`` column
    reserves a per-space grant tier for later phases and is NOT consulted by the
    Sprint B/C membership check. Reuses the global role vocabulary
    (owner/admin/member/viewer) rather than a separate enum, mirroring users.role.
    """

    __tablename__ = "space_members"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        GUID(), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(50), nullable=False, default="member")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Forward-only relationships (no back_populates -> no edits to Workspace/User,
    # mirroring CollectionItem.chunk). Nothing depends on reverse navigation yet.
    workspace = relationship("Workspace")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id", name="uq_space_members_workspace_user"
        ),
        Index("ix_space_members_user_id", "user_id"),
        {"extend_existing": True},
    )
