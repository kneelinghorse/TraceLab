"""Workspace model — dormant multi-tenant seam (Sprint 43 RBAC foundation).

A Workspace is the top-level ownership/tenancy container introduced additively
in Sprint 43. The ``workspace_id`` FK columns on projects/collections/missions/
reports/documents reference this table. In Sprint 43 it holds a single seeded
"Default Workspace" row and nothing reads it yet; it becomes the access-grant
unit / multi-tenant seam in later sprints (architecture locked 2026-05-28).
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.core.database import Base
from app.models.types import GUID

# The seeded "Default Workspace" row (created by migration 030; existing rows were
# backfilled to it by migration 031). Child resources and background creates
# default to this Space; a human's new project goes to their personal Space
# instead (PERSONAL-1, see ``app.services.ownership.default_workspace_id``). Kept
# in sync by hand with the same literal in migrations 030/031 (migrations are
# intentionally self-contained and must not import app code).
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


class Workspace(Base):
    """Top-level ownership/tenancy container (additive, dormant in Sprint 43)."""

    __tablename__ = "workspaces"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # PERSONAL-1 (migration 052, decision #530): set means this is that user's
    # personal Space; there is no separate kind column. One per user (unique), and
    # it goes with the user (CASCADE), so a hard-deleted account leaves no orphan.
    personal_owner_id = Column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, unique=True
    )
