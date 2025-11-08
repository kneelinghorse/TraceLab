"""API schemas for automated quality checks."""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.schemas.quality import QualityCheckRead


class QualityAutomationRunRequest(BaseModel):
    """Request payload for triggering automated quality checks."""

    mission_id: UUID
    performed_by: Optional[str] = None


class QualityAutomationRunResponse(BaseModel):
    """Response payload containing the newly-created audit trail entries."""

    mission_id: UUID
    checks: List[QualityCheckRead]


class QualityAutomationHistoryResponse(BaseModel):
    """Historical quality automation runs for a mission."""

    mission_id: UUID
    history: List[QualityCheckRead]
