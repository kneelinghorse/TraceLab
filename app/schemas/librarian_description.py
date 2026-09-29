"""Bounded human-review description requests; provenance is never client supplied."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DescriptionDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_id: UUID
    prompt: str = Field(min_length=1, max_length=4000)


class DescriptionAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_id: UUID
    proposal_token: str = Field(min_length=1, max_length=200000)
    description: str = Field(min_length=1, max_length=6000)


class DescriptionRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID
    proposal_id: UUID
