"""Corrections status and trigger endpoints for DeepSearch integration."""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.corrections import (
    CorrectionStatusResponse,
    CorrectionTriggerRequest,
    CorrectionTriggerResponse,
)
from app.services.correction_queue import get_correction_queue

router = APIRouter()


@router.get(
    "/corrections",
    response_model=CorrectionStatusResponse,
    summary="Get correction queue status",
    description="Returns correction queue statistics, error distribution, and recent items.",
)
def get_correction_status(
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of recent items to return",
    ),
) -> CorrectionStatusResponse:
    """Get current correction queue status and statistics.

    Returns:
        - stats: Counts of pending, in_progress, completed, failed items
        - error_distribution: Breakdown by error type
        - recent_items: Most recently updated correction items
    """
    queue = get_correction_queue()
    return queue.get_status(limit=limit)


@router.post(
    "/corrections",
    response_model=CorrectionTriggerResponse,
    summary="Trigger correction retries",
    description="Queue pending corrections for immediate retry.",
)
def trigger_corrections(
    request: CorrectionTriggerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CorrectionTriggerResponse:
    """Trigger manual retry of pending corrections.

    Args:
        request: Filter and configuration options

    Returns:
        Count of items triggered for retry
    """
    queue = get_correction_queue()
    response = queue.trigger_retry(
        mission_uuid=request.mission_uuid,
        evidence_ids=request.evidence_ids,
        force_retry=request.force_retry,
        callback_url=request.callback_url,
    )

    # Schedule async processing in background
    if response.triggered > 0:
        background_tasks.add_task(_process_corrections_background, db)

    return response


@router.get(
    "/corrections/telemetry",
    response_model=Dict[str, Any],
    summary="Get correction telemetry summary",
    description="Returns Grafana-ready telemetry summary for dashboards.",
)
def get_correction_telemetry() -> Dict[str, Any]:
    """Get Grafana-ready telemetry summary.

    Returns aggregated metrics suitable for dashboard visualization:
    - Queue counts by status
    - Success rate
    - Webhook delivery stats
    """
    queue = get_correction_queue()
    return queue.get_telemetry_summary()


@router.post(
    "/corrections/process",
    response_model=Dict[str, Any],
    summary="Process pending corrections",
    description="Manually trigger processing of pending corrections ready for retry.",
)
async def process_corrections(
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of items to process",
    ),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Manually trigger processing of pending corrections.

    This is typically done automatically by background tasks, but can be
    triggered manually for testing or when background processing is disabled.
    """
    queue = get_correction_queue()

    def db_factory() -> Session:
        return db

    processed = await queue.process_pending(db_factory, limit=limit)

    return {
        "processed": processed,
        "message": f"Processed {processed} correction items",
        "stats": queue.get_status().stats.model_dump(),
    }


@router.delete(
    "/corrections/completed",
    response_model=Dict[str, Any],
    summary="Clear completed corrections",
    description="Remove completed and skipped items from the queue.",
)
def clear_completed_corrections() -> Dict[str, Any]:
    """Clear completed and skipped items from the correction queue.

    This is a housekeeping operation to keep the queue manageable.
    """
    queue = get_correction_queue()
    cleared = queue.clear_completed()

    return {
        "cleared": cleared,
        "message": f"Cleared {cleared} completed items from queue",
        "stats": queue.get_status().stats.model_dump(),
    }


@router.get(
    "/corrections/dead-letter",
    response_model=Dict[str, Any],
    summary="Get webhook dead letter queue",
    description="Returns failed webhook deliveries for inspection.",
)
def get_dead_letter_queue(
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of items to return",
    ),
) -> Dict[str, Any]:
    """Get failed webhook deliveries from the dead letter queue.

    These are webhooks that failed to deliver after all retry attempts.
    """
    queue = get_correction_queue()
    dlq = queue._webhook_client.get_dead_letter_queue()

    return {
        "count": len(dlq),
        "items": dlq[:limit],
    }


@router.delete(
    "/corrections/dead-letter",
    response_model=Dict[str, Any],
    summary="Clear dead letter queue",
    description="Remove all items from the webhook dead letter queue.",
)
def clear_dead_letter_queue() -> Dict[str, Any]:
    """Clear the webhook dead letter queue."""
    queue = get_correction_queue()
    cleared = queue._webhook_client.clear_dead_letter_queue()

    return {
        "cleared": cleared,
        "message": f"Cleared {cleared} items from dead letter queue",
    }


def _process_corrections_background(db: Session) -> None:
    """Background task to process triggered corrections."""
    import asyncio

    queue = get_correction_queue()

    def db_factory() -> Session:
        return db

    asyncio.run(queue.process_pending(db_factory, limit=50))
