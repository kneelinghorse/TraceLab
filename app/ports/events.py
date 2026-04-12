# ABOUTME: Protocol interface for lightweight event publishing.
# ABOUTME: Provides a seam for future event-driven architecture without coupling to a specific bus.

from __future__ import annotations

from typing import Any, Protocol


class EventPublisher(Protocol):
    """Publish domain events for cross-cutting concerns."""

    def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...
