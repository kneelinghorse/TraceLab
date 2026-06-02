"""Schemas for the Space management API (Sprint 44 T44.5).

Request/response models for the owner/admin-only backend that manages Spaces
(workspaces), their memberships, project<->Space assignment, and project tags.
No UI (deferred 2026-05-29). These only shape management/grouping data; no
authorize() enforcement is wired here (Sprint C).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.security import ROLE_MEMBER


class SpaceCreate(BaseModel):
    """Payload for creating a Space."""

    name: str = Field(..., min_length=1, max_length=255)


class SpaceResponse(BaseModel):
    """A Space (workspace) record."""

    id: UUID
    name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SpaceMemberCreate(BaseModel):
    """Payload for granting a user membership of a Space.

    ``role`` reuses the global owner/admin/member/viewer vocabulary (it is the
    per-space grant tier reserved for later; the Sprint B/C membership check only
    cares about row presence — decision #227).
    """

    user_id: UUID
    role: str = Field(default=ROLE_MEMBER, max_length=50)


class SpaceMemberResponse(BaseModel):
    """A space_members grant record."""

    id: UUID
    workspace_id: UUID
    user_id: UUID
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SpaceMemberDetail(BaseModel):
    """A Space member joined to the user's identity (T48.3 roster).

    SpaceMemberResponse carries only ids; the admin Spaces UI needs the member's
    email/display_name to render a roster, and is_active to flag (or exclude)
    disabled accounts. Built by joining space_members → users in the route.
    """

    user_id: UUID
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime


class ProjectSpaceUpdate(BaseModel):
    """Assign a project to a Space. ``space_id`` None un-assigns (space-less)."""

    space_id: UUID | None = None


class ProjectSpaceResponse(BaseModel):
    """The project's Space assignment after an update."""

    project_id: UUID
    space_id: UUID | None


class ProjectTagResponse(BaseModel):
    """A project_tags link record."""

    project_id: UUID
    tag_id: UUID

    model_config = ConfigDict(from_attributes=True)
