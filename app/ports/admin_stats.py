"""Boundaries for system counts and the external worker observation."""

from typing import Protocol

from sqlalchemy.orm import Session

from app.schemas.admin_stats import AdminStatsResponse, WorkerObservation


class AdminStatsRepository(Protocol):
    def snapshot(self, db: Session) -> AdminStatsResponse: ...


class WorkerProbe(Protocol):
    async def observe(self) -> WorkerObservation: ...
