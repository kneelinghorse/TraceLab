"""Explicit bounded collection proposals; ownership and provenance stay server-side."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class CollectionDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_id: UUID
    prompt: str = Field(min_length=1, max_length=4000)


class CollectionAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_id: UUID
    proposal_token: str = Field(min_length=1, max_length=200000)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(max_length=2000)
    member_ids: list[UUID] = Field(min_length=1, max_length=100)


class SuggestedGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=2000)
    members: list[StrictInt] = Field(min_length=1, max_length=20)


class SuggestedGroups(BaseModel):
    model_config = ConfigDict(extra="forbid")
    groups: list[SuggestedGroup] = Field(min_length=1, max_length=4)
