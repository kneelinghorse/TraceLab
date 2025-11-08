"""API schemas for quality gate status endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class QualityGateStatus(BaseModel):
    gate: str
    status: str
    blocking: bool = True
    details: Optional[str] = None
    evaluated_at: datetime
    metadata: Optional[Dict[str, Any]] = None


class QualityGateReportResponse(BaseModel):
    mission_id: UUID
    protocol_mission_id: str
    evaluated_at: datetime
    all_passed: bool
    failing_gates: List[str]
    gates: Dict[str, QualityGateStatus]
