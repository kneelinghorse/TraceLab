"""Explicit read-only duplicate review requests; no remediation writes are accepted."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DuplicateScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID


class DuplicateCompareRequest(DuplicateScanRequest):
    document_ids: list[UUID] = Field(min_length=2, max_length=2)
    candidate_id: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("document_ids")
    @classmethod
    def distinct_documents(cls, value: list[UUID]) -> list[UUID]:
        if value[0] == value[1]:
            raise ValueError("Choose two different documents.")
        return value
