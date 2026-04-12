"""Event-driven sync triggers for PEDR integration.

Emits sync events when entities change status, enabling <30s latency from
mission completion to PEDR availability.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SyncEventType(str, Enum):
    """Types of sync events."""

    MISSION_COMPLETED = "mission.completed"
    MISSION_UPDATED = "mission.updated"
    MISSION_CREATED = "mission.created"
    DOCUMENT_PROCESSED = "document.processed"
    DOCUMENT_UPLOADED = "document.uploaded"
    INSIGHT_CREATED = "insight.created"
    INSIGHT_VALIDATED = "insight.validated"
    BATCH_SYNC_REQUESTED = "batch.sync_requested"


@dataclass
class SyncEvent:
    """Represents a sync event to be processed."""

    event_type: SyncEventType
    entity_id: str
    entity_type: str  # mission | document | insight
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: int = 1  # 1 = normal, 0 = high priority

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type.value,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "priority": self.priority,
        }


# Event handler type
SyncEventHandler = Callable[[SyncEvent], None]
AsyncSyncEventHandler = Callable[[SyncEvent], Any]  # Coroutine


class SyncEventEmitter:
    """Emit and handle sync events for PEDR integration.

    Supports both synchronous and asynchronous event handlers.
    Events are processed in priority order (0 = highest).
    """

    def __init__(
        self,
        *,
        max_queue_size: int = 1000,
        telemetry_path: Path | None = None,
    ) -> None:
        self._handlers: dict[SyncEventType, set[SyncEventHandler]] = {}
        self._async_handlers: dict[SyncEventType, set[AsyncSyncEventHandler]] = {}
        self._event_queue: list[SyncEvent] = []
        self._max_queue_size = max_queue_size
        self._telemetry_path = telemetry_path
        self._processing = False

    def on(
        self,
        event_type: SyncEventType,
        handler: SyncEventHandler,
    ) -> None:
        """Register a synchronous event handler."""
        if event_type not in self._handlers:
            self._handlers[event_type] = set()
        self._handlers[event_type].add(handler)

    def on_async(
        self,
        event_type: SyncEventType,
        handler: AsyncSyncEventHandler,
    ) -> None:
        """Register an asynchronous event handler."""
        if event_type not in self._async_handlers:
            self._async_handlers[event_type] = set()
        self._async_handlers[event_type].add(handler)

    def off(
        self,
        event_type: SyncEventType,
        handler: SyncEventHandler,
    ) -> None:
        """Unregister a synchronous event handler."""
        if event_type in self._handlers:
            self._handlers[event_type].discard(handler)

    def off_async(
        self,
        event_type: SyncEventType,
        handler: AsyncSyncEventHandler,
    ) -> None:
        """Unregister an asynchronous event handler."""
        if event_type in self._async_handlers:
            self._async_handlers[event_type].discard(handler)

    def emit(self, event: SyncEvent) -> None:
        """Emit an event synchronously.

        Calls all registered handlers immediately.
        """
        self._log_event(event)

        # Call synchronous handlers
        handlers = self._handlers.get(event.event_type, set())
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.exception(f"Sync handler error for {event.event_type}: {e}")

    async def emit_async(self, event: SyncEvent) -> None:
        """Emit an event asynchronously.

        Calls all registered async handlers concurrently.
        """
        self._log_event(event)

        # Call synchronous handlers first
        handlers = self._handlers.get(event.event_type, set())
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.exception(f"Sync handler error for {event.event_type}: {e}")

        # Call async handlers concurrently
        async_handlers = self._async_handlers.get(event.event_type, set())
        if async_handlers:
            tasks = []
            for handler in async_handlers:
                tasks.append(asyncio.create_task(self._safe_call_async(handler, event)))
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call_async(
        self,
        handler: AsyncSyncEventHandler,
        event: SyncEvent,
    ) -> None:
        """Safely call an async handler with exception handling."""
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.exception(f"Async handler error for {event.event_type}: {e}")

    def queue(self, event: SyncEvent) -> bool:
        """Queue an event for later processing.

        Returns True if queued successfully, False if queue is full.
        """
        if len(self._event_queue) >= self._max_queue_size:
            logger.warning(f"Event queue full, dropping event: {event.event_type}")
            return False

        self._event_queue.append(event)
        # Keep queue sorted by priority (0 = highest)
        self._event_queue.sort(key=lambda e: e.priority)
        return True

    def process_queue(self, max_events: int | None = None) -> int:
        """Process queued events synchronously.

        Args:
            max_events: Maximum events to process (None = all)

        Returns:
            Number of events processed
        """
        if self._processing:
            return 0

        self._processing = True
        processed = 0

        try:
            while self._event_queue:
                if max_events is not None and processed >= max_events:
                    break

                event = self._event_queue.pop(0)
                self.emit(event)
                processed += 1
        finally:
            self._processing = False

        return processed

    async def process_queue_async(self, max_events: int | None = None) -> int:
        """Process queued events asynchronously."""
        if self._processing:
            return 0

        self._processing = True
        processed = 0

        try:
            while self._event_queue:
                if max_events is not None and processed >= max_events:
                    break

                event = self._event_queue.pop(0)
                await self.emit_async(event)
                processed += 1
        finally:
            self._processing = False

        return processed

    @property
    def queue_size(self) -> int:
        """Current number of queued events."""
        return len(self._event_queue)

    def _log_event(self, event: SyncEvent) -> None:
        """Log event to telemetry."""
        from app.core.telemetry import emit_telemetry

        logger.info(
            f"Sync event: {event.event_type.value} for {event.entity_type}:{event.entity_id}"
        )

        if not self._telemetry_path:
            return

        emit_telemetry(
            path=self._telemetry_path,
            event_type=f"sync.{event.event_type.value}",
            source="tracelab",
            payload={
                "entity_id": event.entity_id,
                "entity_type": event.entity_type,
                "timestamp": event.timestamp.isoformat(),
                "metadata": event.metadata,
                "priority": event.priority,
            },
        )


# Convenience functions for common events


def emit_mission_completed(
    emitter: SyncEventEmitter,
    mission_id: str,
    *,
    project_id: str | None = None,
    status: str = "complete",
) -> None:
    """Emit a mission completed event."""
    event = SyncEvent(
        event_type=SyncEventType.MISSION_COMPLETED,
        entity_id=mission_id,
        entity_type="mission",
        metadata={
            "project_id": project_id,
            "status": status,
        },
        priority=0,  # High priority for completions
    )
    emitter.emit(event)


def emit_mission_updated(
    emitter: SyncEventEmitter,
    mission_id: str,
    *,
    project_id: str | None = None,
    changes: dict[str, Any] | None = None,
) -> None:
    """Emit a mission updated event."""
    event = SyncEvent(
        event_type=SyncEventType.MISSION_UPDATED,
        entity_id=mission_id,
        entity_type="mission",
        metadata={
            "project_id": project_id,
            "changes": changes or {},
        },
    )
    emitter.emit(event)


def emit_document_processed(
    emitter: SyncEventEmitter,
    document_id: str,
    *,
    project_id: str | None = None,
    chunk_count: int = 0,
) -> None:
    """Emit a document processed event."""
    event = SyncEvent(
        event_type=SyncEventType.DOCUMENT_PROCESSED,
        entity_id=document_id,
        entity_type="document",
        metadata={
            "project_id": project_id,
            "chunk_count": chunk_count,
        },
    )
    emitter.emit(event)


def emit_batch_sync_requested(
    emitter: SyncEventEmitter,
    *,
    entity_types: list[str] | None = None,
    mode: str = "delta",
) -> None:
    """Emit a batch sync request event."""
    event = SyncEvent(
        event_type=SyncEventType.BATCH_SYNC_REQUESTED,
        entity_id="batch",
        entity_type="system",
        metadata={
            "entity_types": entity_types or ["mission", "document"],
            "mode": mode,
        },
    )
    emitter.emit(event)


# Singleton instance
_sync_event_emitter: SyncEventEmitter | None = None


def get_sync_event_emitter(
    telemetry_path: Path | None = None,
) -> SyncEventEmitter:
    """Return singleton sync event emitter."""
    global _sync_event_emitter
    if _sync_event_emitter is None:
        _sync_event_emitter = SyncEventEmitter(
            telemetry_path=telemetry_path
            or Path("cmos/telemetry/events/sprint-11-pedr-sync.jsonl"),
        )
    return _sync_event_emitter


__all__ = [
    "SyncEventType",
    "SyncEvent",
    "SyncEventHandler",
    "AsyncSyncEventHandler",
    "SyncEventEmitter",
    "emit_mission_completed",
    "emit_mission_updated",
    "emit_document_processed",
    "emit_batch_sync_requested",
    "get_sync_event_emitter",
]
