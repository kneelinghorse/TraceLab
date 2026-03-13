"""API schemas for automated quality checks."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.schemas.quality import QualityCheckRead


class QualityAutomationRunRequest(BaseModel):
    """Request payload for triggering automated quality checks."""

    mission_id: UUID
    performed_by: str | None = None


class QualityAutomationRunResponse(BaseModel):
    """Response payload containing the newly-created audit trail entries."""

    mission_id: UUID
    checks: list[QualityCheckRead]


class QualityAutomationHistoryResponse(BaseModel):
    """Historical quality automation runs for a mission."""

    mission_id: UUID
    history: list[QualityCheckRead]
