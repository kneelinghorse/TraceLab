"""Only signed, reviewed source selections and report previews can be accepted."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReportDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_id: UUID
    source_token: str = Field(min_length=1, max_length=200000)
    chunk_ids: list[UUID] = Field(min_length=1, max_length=12)
    reviewed_sources: Literal[True]
    title: str = Field(min_length=1, max_length=255)
    prompt: str = Field(min_length=1, max_length=4000)
    format: Literal["summary", "report", "bullets", "markdown"] = "summary"


class ReportAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID
    proposal_token: str = Field(min_length=1, max_length=200000)


class ReportCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=12000)
