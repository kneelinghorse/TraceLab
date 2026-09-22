"""Admin-only usage summary (METER-0). Read side only; nothing here limits or bills."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UsageSummaryRow(BaseModel):
    user_id: UUID | None
    email: str | None = None
    kind: str
    model: str | None
    records: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration_seconds: float
    cost_usd: float | None = Field(default=None, description="Null unless a price was recorded; none is asserted for DeepSeek runs.")


class UsageSummaryResponse(BaseModel):
    since: datetime
    until: datetime
    rows: list[UsageSummaryRow]
