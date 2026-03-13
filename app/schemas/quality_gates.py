"""API schemas for quality gate status endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class QualityGateStatus(BaseModel):
    gate: str
    status: str
    blocking: bool = True
    details: str | None = None
    evaluated_at: datetime
    metadata: dict[str, Any] | None = None


class QualityGateReportResponse(BaseModel):
    mission_id: UUID
    protocol_mission_id: str
    evaluated_at: datetime
    all_passed: bool
    failing_gates: list[str]
    gates: dict[str, QualityGateStatus]
