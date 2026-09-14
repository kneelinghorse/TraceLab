"""Allowlisted personal mission view contract; no persisted access or project names."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.mission import MISSION_STATUSES

AttentionReason = Literal["validation_failed", "blocked", "stalled", "unreviewed"]


class MissionViewFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    view: Literal["all", "attention", "queue"] = "all"
    reason: list[AttentionReason] = Field(default_factory=list)
    status: str | None = None
    project_id: UUID | None = None

    @model_validator(mode="after")
    def valid_combination(self):
        if self.reason and self.view != "attention":
            raise ValueError("Reasons require view=attention")
        if self.status is not None and self.status not in MISSION_STATUSES:
            raise ValueError("Invalid mission status")
        return self


class MissionViewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    filters: MissionViewFilters


class MissionViewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    filters: MissionViewFilters | None = None


class MissionViewResponse(BaseModel):
    id: UUID
    name: str
    entity_type: Literal["missions"]
    filters: dict
    created_at: datetime
    updated_at: datetime
    total: int


class MissionViewList(BaseModel):
    items: list[MissionViewResponse]
