"""In-memory mission event bus with SSE support.

Provides a publish/subscribe event system for real-time mission progress.
SSE consumers subscribe via async generators; backend code emits events
at key execution points (status changes, PEDR layer progress, etc.).

Recent events are kept in a ring buffer so new SSE connections get
immediate context without waiting for the next event.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import AsyncGenerator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MissionEventType(str, Enum):
    """Event types emitted during mission lifecycle."""

    # Mission lifecycle
    MISSION_QUEUED = "mission.queued"
    MISSION_STARTED = "mission.started"
    MISSION_COMPLETED = "mission.completed"
    MISSION_FAILED = "mission.failed"
    MISSION_STATUS_CHANGED = "mission.status_changed"

    # PEDR search progress
    PEDR_SEARCH_STARTED = "pedr.search_started"
    PEDR_LAYER_STARTED = "pedr.layer_started"
    PEDR_LAYER_COMPLETED = "pedr.layer_completed"
    PEDR_LAYER_FAILED = "pedr.layer_failed"
    PEDR_FUSION_COMPLETED = "pedr.fusion_completed"
    PEDR_SEARCH_COMPLETED = "pedr.search_completed"

    # Quality & governance
    QUALITY_GATES_EVALUATED = "quality.gates_evaluated"

    # CMOS bridge
    CMOS_MISSION_STARTED = "cmos.mission.started"
    CMOS_MISSION_COMPLETED = "cmos.mission.completed"
    CMOS_MISSION_BLOCKED = "cmos.mission.blocked"
    CMOS_MISSION_UNBLOCKED = "cmos.mission.unblocked"
    CMOS_MISSION_STATUS_CHANGED = "cmos.mission.status_changed"

    # System
    HEARTBEAT = "system.heartbeat"


@dataclass
class MissionEvent:
    """A single mission progress event."""

    event_type: str
    timestamp: str
    mission_id: str | None = None
    mission_title: str | None = None
    layer: str | None = None
    duration_ms: float | None = None
    result_count: int | None = None
    status: str | None = None
    previous_status: str | None = None
    error: str | None = None
    details: dict[str, Any] | None = None

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return f"event: {self.event_type}\ndata: {json.dumps(data)}\n\n"


class MissionEventBus:
    """Pub/sub event bus for mission progress with SSE support.

    Thread-safe for emit (called from sync FastAPI endpoints).
    Async-safe for subscribe (called from SSE streaming responses).
    """

    def __init__(self, max_history: int = 100) -> None:
        self._history: deque[MissionEvent] = deque(maxlen=max_history)
        self._subscribers: list[asyncio.Queue[MissionEvent]] = []
        self._lock = asyncio.Lock()

    def emit(self, event: MissionEvent) -> None:
        """Publish an event to all subscribers and history buffer."""
        self._history.append(event)
        # Fan out to all subscriber queues (non-blocking)
        stale: list[asyncio.Queue] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(queue)
        # Remove stale subscribers that aren't consuming
        for q in stale:
            if q in self._subscribers:
                self._subscribers.remove(q)
                logger.debug("Removed stale SSE subscriber (queue full)")

    async def subscribe(
        self,
        include_history: bool = True,
        heartbeat_seconds: int = 15,
    ) -> AsyncGenerator[MissionEvent, None]:
        """Subscribe to events as an async generator for SSE streaming.

        Yields recent history first (if include_history=True), then
        live events as they arrive. Sends heartbeat events to keep
        the connection alive.
        """
        queue: asyncio.Queue[MissionEvent] = asyncio.Queue(maxsize=200)
        self._subscribers.append(queue)

        try:
            # Replay recent history
            if include_history:
                for event in self._history:
                    yield event

            # Stream live events with heartbeat
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=heartbeat_seconds
                    )
                    yield event
                except TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield MissionEvent(
                        event_type=MissionEventType.HEARTBEAT.value,
                        timestamp=datetime.now(UTC).isoformat(),
                    )
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def get_recent_events(self, limit: int = 50) -> list[MissionEvent]:
        """Get recent events from history buffer."""
        events = list(self._history)
        return events[-limit:] if len(events) > limit else events

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# ─── Singleton ───────────────────────────────────────────────────────────────

_event_bus: MissionEventBus | None = None


def get_mission_event_bus() -> MissionEventBus:
    """Get or create the singleton event bus."""
    global _event_bus
    if _event_bus is None:
        _event_bus = MissionEventBus()
    return _event_bus


# ─── Convenience emitters ────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(UTC).isoformat()


def emit_mission_status_change(
    mission_id: str,
    title: str,
    new_status: str,
    previous_status: str | None = None,
) -> None:
    """Emit a mission status change event."""
    bus = get_mission_event_bus()

    # Map status to specific event type
    type_map = {
        "queued": MissionEventType.MISSION_QUEUED,
        "in_progress": MissionEventType.MISSION_STARTED,
        "completed": MissionEventType.MISSION_COMPLETED,
        "failed": MissionEventType.MISSION_FAILED,
    }
    event_type = type_map.get(new_status, MissionEventType.MISSION_STATUS_CHANGED)

    bus.emit(
        MissionEvent(
            event_type=event_type.value,
            timestamp=_now(),
            mission_id=mission_id,
            mission_title=title,
            status=new_status,
            previous_status=previous_status,
        )
    )


def emit_pedr_layer_event(
    *,
    event_type: MissionEventType,
    layer: str,
    mission_id: str | None = None,
    duration_ms: float | None = None,
    result_count: int | None = None,
    error: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Emit a PEDR search layer progress event."""
    bus = get_mission_event_bus()
    bus.emit(
        MissionEvent(
            event_type=event_type.value,
            timestamp=_now(),
            mission_id=mission_id,
            layer=layer,
            duration_ms=duration_ms,
            result_count=result_count,
            error=error,
            details=details,
        )
    )


def emit_quality_gates(
    mission_id: str,
    gates_passed: int,
    total_gates: int,
    score: float,
) -> None:
    """Emit quality gate evaluation results."""
    bus = get_mission_event_bus()
    bus.emit(
        MissionEvent(
            event_type=MissionEventType.QUALITY_GATES_EVALUATED.value,
            timestamp=_now(),
            mission_id=mission_id,
            details={
                "gates_passed": gates_passed,
                "total_gates": total_gates,
                "score": round(score, 3),
            },
        )
    )


# ─── CMOS bridge emitter ────────────────────────────────────────────────────

# Maps CMOS transition statuses to event types.
_CMOS_STATUS_MAP: dict[str, MissionEventType] = {
    "in progress": MissionEventType.CMOS_MISSION_STARTED,
    "completed": MissionEventType.CMOS_MISSION_COMPLETED,
    "blocked": MissionEventType.CMOS_MISSION_BLOCKED,
    "unblocked": MissionEventType.CMOS_MISSION_UNBLOCKED,
}


def emit_cmos_mission_event(
    *,
    mission_id: str,
    name: str,
    new_status: str,
    previous_status: str | None = None,
    notes: str | None = None,
    reason: str | None = None,
    sprint_id: str | None = None,
) -> bool:
    """Emit a TraceLab SSE event for a CMOS mission transition.

    Graceful degradation: returns False and logs on failure, never raises.
    """
    try:
        status_key = new_status.strip().lower()
        event_type = _CMOS_STATUS_MAP.get(
            status_key, MissionEventType.CMOS_MISSION_STATUS_CHANGED
        )

        details: dict[str, Any] = {"source": "cmos"}
        if notes:
            details["notes"] = notes
        if reason:
            details["reason"] = reason
        if sprint_id:
            details["sprint_id"] = sprint_id

        bus = get_mission_event_bus()
        bus.emit(
            MissionEvent(
                event_type=event_type.value,
                timestamp=_now(),
                mission_id=mission_id,
                mission_title=name,
                status=status_key,
                previous_status=previous_status.strip().lower()
                if previous_status
                else None,
                details=details,
            )
        )
        logger.info(
            "CMOS bridge: emitted %s for %s (%s → %s)",
            event_type.value,
            mission_id,
            previous_status,
            new_status,
        )
        return True
    except Exception:
        logger.warning(
            "CMOS bridge: failed to emit event for %s (degraded)",
            mission_id,
            exc_info=True,
        )
        return False


__all__ = [
    "MissionEventType",
    "MissionEvent",
    "MissionEventBus",
    "get_mission_event_bus",
    "emit_mission_status_change",
    "emit_pedr_layer_event",
    "emit_quality_gates",
    "emit_cmos_mission_event",
]
