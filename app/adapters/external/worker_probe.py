"""Bounded worker health probe; missing telemetry remains unavailable, never zero."""

import math
from datetime import UTC, datetime

import httpx

from app.core.config import settings
from app.schemas.admin_stats import WorkerObservation


class HTTPWorkerProbe:
    async def observe(self) -> WorkerObservation:
        checked_at = datetime.now(UTC)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(settings.deepsearch_worker_health_url)
            if not response.is_success:
                return WorkerObservation(checked_at=checked_at, error=f"Worker returned HTTP {response.status_code}")
            data = response.json()
            if not isinstance(data, dict):
                return WorkerObservation(checked_at=checked_at, error="Worker returned an invalid health response")
            values = {}
            for key in ("missions_processed", "missions_completed", "missions_failed"):
                value = data.get(key)
                values[key] = value if type(value) is int and value >= 0 else None
            uptime = data.get("uptime_seconds")
            if (
                isinstance(uptime, bool)
                or not isinstance(uptime, int | float)
                or not math.isfinite(uptime)
                or uptime < 0
            ):
                uptime = None
            return WorkerObservation(
                checked_at=checked_at,
                status=data["status"] if isinstance(data.get("status"), str) else "unknown",
                uptime_seconds=uptime,
                current_mission_id=data.get("current_mission_id")
                if isinstance(data.get("current_mission_id"), str)
                else None,
                missions_processed=values["missions_processed"],
                missions_completed=values["missions_completed"],
                missions_failed=values["missions_failed"],
            )
        except httpx.TimeoutException:
            return WorkerObservation(checked_at=checked_at, error="Worker health check timed out")
        except (httpx.RequestError, ValueError):
            return WorkerObservation(checked_at=checked_at, error="Worker health could not be read")
