"""In-app scheduler for mission-result reconciliation (OPS-2).

Runs `MissionResultMaterializationService.reconcile_completed` on a fixed
interval inside the API process. The Railway project has no cron facility on
any of its services, so the deployed backend itself is the schedule host; the
run loop lives and dies with the app (started from the FastAPI startup hook,
cancelled on shutdown).

Evidence contract (DeepSearch s92): the single ``reconciler_run`` record and
``GET /health.reconciler`` are aggregate-only evidence surfaces — counts never
mission bodies, URLs, or raw identifiers. Their count shape is ``{scanned,
eligible, repaired, failed, skipped_soft_deleted}``. Private diagnostic records
elsewhere may carry internal identifiers needed for repair, but never secrets or
result bodies. The public health snapshot lets monitors assert freshness unauthenticated.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


@dataclass
class ReconcilerState:
    last_run_at: datetime | None = None
    last_status: str | None = None  # "ok" | "partial" | "error"
    last_counts: dict[str, int] | None = None
    runs: int = 0
    consecutive_errors: int = 0


_state = ReconcilerState()
_task: asyncio.Task[None] | None = None


def reconciler_health() -> dict[str, Any]:
    """Snapshot for the public /health payload (counts-only, no identifiers)."""
    return {
        "enabled": settings.reconciler_enabled,
        "interval_seconds": settings.reconciler_interval_seconds,
        "last_run_at": _state.last_run_at.isoformat() if _state.last_run_at else None,
        "last_status": _state.last_status,
        "last_counts": _state.last_counts,
        "runs": _state.runs,
    }


def run_reconciliation_once() -> dict[str, int]:
    """One bounded reconciliation pass. Sync — callers run it in a worker thread."""
    from app.services.result_materialization import MissionResultMaterializationService

    db = SessionLocal()
    try:
        summary = MissionResultMaterializationService().reconcile_completed(
            db, limit=settings.reconciler_batch_limit
        )
        return {
            "scanned": summary.scanned,
            "eligible": summary.eligible,
            "repaired": summary.repaired,
            "failed": summary.failed,
            "skipped_soft_deleted": summary.skipped_soft_deleted,
        }
    finally:
        db.close()


async def run_tick() -> None:
    """Execute one scheduled run and record its outcome; never raises."""
    try:
        counts = await asyncio.to_thread(run_reconciliation_once)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Mission result reconciliation failed")
        _state.last_run_at = datetime.now(UTC)
        _state.last_status = "error"
        _state.last_counts = None
        _state.runs += 1
        _state.consecutive_errors += 1
        logger.error(
            "reconciler_run status=error consecutive_errors=%s",
            _state.consecutive_errors,
        )
        return

    _state.last_run_at = datetime.now(UTC)
    _state.last_counts = counts
    _state.runs += 1
    _state.consecutive_errors = 0
    _state.last_status = "partial" if counts["failed"] else "ok"
    log = logger.error if counts["failed"] else logger.info
    log(
        "reconciler_run status=%s scanned=%s eligible=%s repaired=%s failed=%s "
        "skipped_soft_deleted=%s",
        _state.last_status,
        counts["scanned"],
        counts["eligible"],
        counts["repaired"],
        counts["failed"],
        counts["skipped_soft_deleted"],
    )


async def _loop() -> None:
    # First pass immediately at startup so a fresh deploy produces evidence
    # without waiting a full interval; then fixed-interval ticks.
    while True:
        await run_tick()
        await asyncio.sleep(settings.reconciler_interval_seconds)


def start_reconciler() -> bool:
    """Start the background loop; returns True if a task was started."""
    global _task
    if not settings.reconciler_enabled or settings.environment == "test":
        return False
    if _task is not None and not _task.done():
        return False
    _task = asyncio.get_running_loop().create_task(_loop())
    logger.info(
        "reconciler_scheduler started interval_seconds=%s batch_limit=%s",
        settings.reconciler_interval_seconds,
        settings.reconciler_batch_limit,
    )
    return True


def stop_reconciler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
