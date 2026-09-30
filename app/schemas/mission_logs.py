"""Bounded, versioned log transport; ownership proof never appears in a response."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AliasChoices,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

LOG_CONTRACT_VERSION = 'tracelab-mission-logs-v2'
MAX_LOG_BATCH = 200
MAX_LOG_MESSAGE = 2048
PositiveSequence = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]


class LogEntry(BaseModel):
    """Bounded legacy input during the terminal-only worker migration window."""
    model_config = ConfigDict(extra='forbid')
    level: str = Field(default='INFO', max_length=20)
    message: str = Field(min_length=1, max_length=MAX_LOG_MESSAGE)
    source: str | None = Field(default=None, max_length=100, validation_alias=AliasChoices('source', 'phase'))
    logged_at: datetime | None = Field(default=None, validation_alias=AliasChoices('logged_at', 'ts'))


class LogBatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    logs: list[LogEntry] = Field(min_length=1, max_length=MAX_LOG_BATCH, validation_alias=AliasChoices('logs', 'entries'))


class AttemptLogEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: UUID
    sequence: PositiveSequence
    level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    message: str = Field(min_length=1, max_length=MAX_LOG_MESSAGE)
    source: str | None = Field(default=None, max_length=100)
    logged_at: AwareDatetime

    @field_validator('logged_at')
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class AttemptLogBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    contract_version: Literal['tracelab-mission-logs-v2']
    mission_id: UUID
    attempt_count: PositiveSequence
    lease_owner: str = Field(min_length=1, max_length=256)
    lease_token: SecretStr = Field(min_length=1, max_length=512)
    logs: list[AttemptLogEntry] = Field(min_length=1, max_length=MAX_LOG_BATCH)

    @model_validator(mode='after')
    def unique_identities(self) -> 'AttemptLogBatch':
        if len({entry.event_id for entry in self.logs}) != len(self.logs):
            raise ValueError('Duplicate event IDs within batch')
        if len({entry.sequence for entry in self.logs}) != len(self.logs):
            raise ValueError('Duplicate sequences within batch')
        proof = self.lease_token.get_secret_value()
        if any(proof in entry.message or (entry.source and proof in entry.source) for entry in self.logs):
            raise ValueError('Log entries must not contain ownership proof')
        return self


class LogBatchAcknowledgement(BaseModel):
    contract_version: Literal['tracelab-mission-logs-v2'] = LOG_CONTRACT_VERSION
    mission_id: UUID
    attempt_count: int
    accepted: int
    replayed: int
    event_ids: list[UUID]
