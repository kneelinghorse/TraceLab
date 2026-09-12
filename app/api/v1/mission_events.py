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
from contextlib import aclosing
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.authorization import (
    accessible_filter,
    authorize,
    authorize_service_or_403,
)
from app.core.database import SessionLocal, get_db
from app.core.mission_events import (
    MissionEvent,
    emit_cmos_mission_event,
    get_mission_event_bus,
)
from app.core.security import (
    AuthenticatedUser,
    require_authenticated_principal,
    require_authenticated_user,
    require_authenticated_user_sse,
)
from app.models.mission import Mission

logger = logging.getLogger(__name__)

router = APIRouter()
stream_router = APIRouter()
service_router = APIRouter()


@stream_router.get("/events/stream")
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
        # A fresh session per batch/event avoids holding a DB connection for the
        # lifetime of the stream and rechecks revoked grants before delivery.
        def filter_history(events):
            with SessionLocal() as db:
                return _visible_events(events, _user, db)[-limit:]

        async with aclosing(
            bus.subscribe(
                include_history=True,
                heartbeat_seconds=15,
                history_filter=filter_history,
            )
        ) as events:
            async for event in events:
                with SessionLocal() as db:
                    visible = _visible_events([event], _user, db)
                if visible:
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
    previous_status: str | None = Field(None, description="Previous status")
    notes: str | None = Field(None, description="Transition notes")
    reason: str | None = Field(
        None, description="Block reason (for blocked transitions)"
    )
    sprint_id: str | None = Field(None, description="Sprint ID (e.g. sprint-35)")


@service_router.post("/events/cmos")
def ingest_cmos_mission_event(
    payload: CmosMissionEventRequest,
    _user: AuthenticatedUser = Depends(require_authenticated_principal),
):
    """Ingest a CMOS mission transition as a TraceLab SSE event.

    Called by the CMOS MCP server when a mission transitions state.
    Emits the event to the SSE bus so the Mission Operations Center
    dashboard reflects CMOS activity in real-time.

    Gracefully degrades: returns success even if event emission fails.
    """
    authorize_service_or_403(_user)
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


@router.get("/events/recent", response_model=list[dict])
def get_recent_events(
    limit: int = Query(50, ge=1, le=200, description="Number of recent events"),
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """Get recent mission events as JSON (non-streaming).

    Useful for initial page load before SSE connection is established.
    """
    bus = get_mission_event_bus()
    events = _visible_events(bus.get_recent_events(limit=200), _user, db)[-limit:]
    return [
        {k: v for k, v in event.__dict__.items() if v is not None} for event in events
    ]


def _visible_events(
    events: list[MissionEvent], user: AuthenticatedUser, db: Session
) -> list[MissionEvent]:
    """Scope mission events; global CMOS/PEDR activity has no tenant grants."""
    if authorize(user, "read", None, db):
        return events
    mission_ids = set()
    mission_names = set()
    for event in events:
        if event.event_type.startswith("cmos.") or not event.mission_id:
            continue
        try:
            mission_ids.add(UUID(event.mission_id))
        except ValueError:
            # MissionService emits the canonical human mission_id; some other
            # producers use the row UUID. Resolve both, never CMOS bridge IDs.
            mission_names.add(event.mission_id)
    readable = set()
    if mission_ids or mission_names:
        query = db.query(Mission.id, Mission.mission_id).filter(
            or_(Mission.id.in_(mission_ids), Mission.mission_id.in_(mission_names))
        )
        scope = accessible_filter(user, Mission, db)
        if scope is not None:
            query = query.filter(scope)
        for row_id, name in query.all():
            # UUID-shaped refs resolve only as row IDs. A tenant must not claim
            # another mission's UUID as a human name to expose its events.
            if row_id in mission_ids:
                readable.add(str(row_id))
            if name in mission_names:
                readable.add(name)
    return [
        event
        for event in events
        if event.event_type == "system.heartbeat"
        or (not event.event_type.startswith("cmos.") and event.mission_id in readable)
    ]
