"""SSE endpoint for real-time mission progress streaming.

GET /api/v1/missions/events/stream
  → Server-Sent Events stream of mission activity

GET /api/v1/missions/events/recent
  → JSON array of recent events (for initial page load)
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.mission_events import (
    MissionEvent,
    get_mission_event_bus,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/events/stream")
async def stream_mission_events(
    limit: int = Query(50, ge=1, le=200, description="Number of history events to replay"),
):
    """Stream mission progress events via Server-Sent Events.

    Opens a persistent connection that streams:
    - Recent event history (replay on connect)
    - Live events as they occur (status changes, PEDR layer progress, etc.)
    - Heartbeat events every 15s to keep connection alive

    **Auth**: Pass JWT token via query param `token` for EventSource compatibility,
    or use standard Authorization header.

    Event format:
    ```
    event: mission.started
    data: {"event_type": "mission.started", "mission_id": "...", ...}
    ```
    """
    bus = get_mission_event_bus()

    async def event_generator():
        async for event in bus.subscribe(
            include_history=True,
            heartbeat_seconds=15,
        ):
            yield event.to_sse()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/events/recent", response_model=List[dict])
def get_recent_events(
    limit: int = Query(50, ge=1, le=200, description="Number of recent events"),
):
    """Get recent mission events as JSON (non-streaming).

    Useful for initial page load before SSE connection is established.
    """
    bus = get_mission_event_bus()
    events = bus.get_recent_events(limit=limit)
    return [
        {k: v for k, v in event.__dict__.items() if v is not None}
        for event in events
    ]
