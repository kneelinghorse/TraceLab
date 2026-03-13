"""SSE endpoint for real-time mission progress streaming.

GET /api/v1/missions/events/stream
  → Server-Sent Events stream of mission activity

GET /api/v1/missions/events/recent
  → JSON array of recent events (for initial page load)

POST /api/v1/missions/events/cmos
  → Ingest a CMOS mission transition as a TraceLab SSE event
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.mission_events import (
    MissionEvent,
    emit_cmos_mission_event,
    get_mission_event_bus,
)
from app.core.security import (
    AuthenticatedUser,
    require_authenticated_user,
    require_authenticated_user_sse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/events/stream")
async def stream_mission_events(
    limit: int = Query(
        50, ge=1, le=200, description="Number of history events to replay"
    ),
    _user: AuthenticatedUser = Depends(require_authenticated_user_sse),
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


class CmosMissionEventRequest(BaseModel):
    """Payload for the CMOS mission event bridge endpoint."""

    mission_id: str = Field(..., description="CMOS mission ID (e.g. T35.2)")
    name: str = Field(..., description="Mission name/title")
    new_status: str = Field(
        ..., description="Target status (e.g. In Progress, Completed, Blocked)"
    )
    previous_status: Optional[str] = Field(None, description="Previous status")
    notes: Optional[str] = Field(None, description="Transition notes")
    reason: Optional[str] = Field(
        None, description="Block reason (for blocked transitions)"
    )
    sprint_id: Optional[str] = Field(None, description="Sprint ID (e.g. sprint-35)")


@router.post("/events/cmos")
def ingest_cmos_mission_event(
    payload: CmosMissionEventRequest,
    _user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Ingest a CMOS mission transition as a TraceLab SSE event.

    Called by the CMOS MCP server when a mission transitions state.
    Emits the event to the SSE bus so the Mission Operations Center
    dashboard reflects CMOS activity in real-time.

    Gracefully degrades: returns success even if event emission fails.
    """
    emitted = emit_cmos_mission_event(
        mission_id=payload.mission_id,
        name=payload.name,
        new_status=payload.new_status,
        previous_status=payload.previous_status,
        notes=payload.notes,
        reason=payload.reason,
        sprint_id=payload.sprint_id,
    )
    return {
        "ok": True,
        "emitted": emitted,
        "mission_id": payload.mission_id,
        "status": payload.new_status,
    }


@router.get("/events/recent", response_model=List[dict])
def get_recent_events(
    limit: int = Query(50, ge=1, le=200, description="Number of recent events"),
    _user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Get recent mission events as JSON (non-streaming).

    Useful for initial page load before SSE connection is established.
    """
    bus = get_mission_event_bus()
    events = bus.get_recent_events(limit=limit)
    return [
        {k: v for k, v in event.__dict__.items() if v is not None} for event in events
    ]
