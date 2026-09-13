"""Combine persisted system counts with explicitly scoped runtime observations."""

from sqlalchemy.orm import Session

from app.ports.admin_stats import AdminStatsRepository, WorkerProbe
from app.schemas.admin_stats import AdminStatsResponse
from app.services.correction_queue import get_correction_queue
from app.services.reconciler_scheduler import reconciler_health


class AdminStatsService:
    def __init__(self, repository: AdminStatsRepository, worker: WorkerProbe):
        self.repository = repository
        self.worker = worker

    async def snapshot(self, db: Session) -> AdminStatsResponse:
        result = self.repository.snapshot(db)
        result.reconciler = reconciler_health()
        try:
            result.corrections = get_correction_queue().get_status(limit=0).stats.model_dump()
        except Exception:
            # The persisted counts remain useful when a runtime dependency fails.
            result.corrections_error = "The correction queue is unavailable in this API process."
        result.worker = await self.worker.observe()
        return result
