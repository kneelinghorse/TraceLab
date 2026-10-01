"""Webhook endpoints for receiving external callbacks.

Handles incoming webhooks from DeepSearch and other services.
These endpoints use signature-based authentication rather than JWT.
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.schemas.webhook import (
    DeepSearchWebhookPayload,
    WebhookErrorResponse,
    WebhookResponse,
)
from app.services import support_inbox
from app.services.mission_service import MissionNotFoundError
from app.services.notifications import NOTIFY_STATUSES, notify_terminal_status
from app.services.webhook_handler import (
    WebhookHandler,
    WebhookProcessingError,
    WebhookValidationError,
    get_webhook_handler,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/deepsearch",
    response_model=WebhookResponse,
    responses={
        400: {"model": WebhookErrorResponse, "description": "Invalid payload"},
        401: {"model": WebhookErrorResponse, "description": "Invalid signature"},
        404: {"model": WebhookErrorResponse, "description": "Mission not found"},
        409: {"model": WebhookErrorResponse, "description": "Attempt mismatch"},
        500: {"model": WebhookErrorResponse, "description": "Processing error"},
    },
    summary="Receive DeepSearch job completion webhook",
    description="""
Receives webhook callbacks from DeepSearch when a job completes.

**Authentication**: Uses HMAC-SHA256 signature verification via X-DeepSearch-Signature header.
TraceLab reads `DEEPSEARCH_TRACELAB_SERVICE_SECRET` (with the legacy
`DEEPSEARCH_WEBHOOK_SECRET` fallback). DeepSearch must sign receipts with the
same value from its `TRACELAB_DEEPSEARCH_SERVICE_SECRET`. Production fails
closed when neither TraceLab variable is configured. Unsigned callbacks are
limited to explicit test environments or local development with `DEBUG=true`.

**Idempotency**: Safe to receive the same webhook multiple times. If the mission
has already been updated with this job_id, the worker payload is not reapplied and
the request receives the idempotent acknowledgement. TraceLab may still reconcile
missing or stale local result artifacts from the authoritative persisted result.

**Payload**: DeepSearch sends job results including:
- job_id: The DeepSearch job identifier
- mission_id: The human-readable mission ID (e.g., "B16.1")
- status: "complete", "failed", or "cancelled"
- execution_metadata: Execution metrics (loops, sources, duration, etc.)
- result_markdown: Raw markdown research output
- result_protocol: Structured Mission Protocol result object
- error: Error message if job failed
""",
)
async def receive_deepsearch_webhook(
    request: Request,
    payload: DeepSearchWebhookPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_deepsearch_signature: str | None = Header(None),
    x_deepsearch_timestamp: str | None = Header(None),
    handler: WebhookHandler = Depends(get_webhook_handler),
) -> WebhookResponse:
    """Process incoming DeepSearch webhook.

    Validates the signature, finds the mission, and updates it based on
    the job completion status.
    """
    # Get raw body for signature validation
    body = await request.body()

    # Validate signature
    try:
        handler.validate_signature(
            payload_body=body,
            signature=x_deepsearch_signature,
            timestamp=x_deepsearch_timestamp,
        )
    except WebhookValidationError as exc:
        logger.warning("Webhook signature validation failed: %s", str(exc))
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    # Process the webhook
    try:
        mission, status_message = handler.process_deepsearch_webhook(db, payload)
        if mission.status in NOTIFY_STATUSES:
            # Runs after the 200 is sent; sends at most once per terminal status.
            background_tasks.add_task(notify_terminal_status, mission.id)

        return WebhookResponse(
            received=True,
            mission_id=mission.mission_id,
            status=mission.status,
            message=f"Mission {status_message}"
            if status_message != "already_processed"
            else "Webhook already processed (idempotent)",
        )

    except MissionNotFoundError as exc:
        logger.warning("Webhook for unknown mission: %s", payload.mission_id)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Mission '{payload.mission_id}' not found",
        ) from exc

    except WebhookValidationError as exc:
        logger.warning("Webhook attempt correlation failed: %s", str(exc))
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except WebhookProcessingError as exc:
        logger.error("Webhook processing error: %s", str(exc))
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Unexpected error processing webhook")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(exc)[:200]}",
        ) from exc


@router.post(
    "/resend-inbound",
    summary="Forward mail for the Stage1 and Aquex support addresses",
    description="""
Resend Inbound calls this for every message received on aquex.ai. Messages to stage1@aquex.ai or hello@aquex.ai
are fetched and re-sent once to SUPPORT_FORWARD_TO; every other event or recipient is acknowledged and ignored.

**Authentication**: Resend's Svix signature (`svix-id`, `svix-timestamp`, `svix-signature`) under
`RESEND_WEBHOOK_SECRET`. The route fails closed (503) until the secret, `RESEND_INBOUND_API_KEY`,
`SUPPORT_FORWARD_TO` and `RESEND_FROM_ADDRESS` are all set. A failed forward answers 502, so Resend retries;
the send's idempotency key makes a retry safe.
""",
)
async def receive_resend_inbound(request: Request) -> dict[str, str]:
    """Verify Resend's signature, then forward mail to the fixed support allowlist."""
    if not (settings.resend_webhook_secret and settings.resend_inbound_api_key and settings.support_forward_to and settings.resend_from_address):
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail="Support forwarding is not configured")
    body = await request.body()
    if not support_inbox.signature_valid(settings.resend_webhook_secret, request.headers, body):
        logger.warning("Resend inbound webhook signature validation failed")
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    event = json.loads(body)
    data = event.get("data") or {}
    if event.get("type") != "email.received":
        return {"status": "ignored"}
    matched_addresses = support_inbox.matched_support_addresses(data)
    if not matched_addresses:
        return {"status": "ignored"}
    email_id = str(data.get("email_id", ""))
    try:
        message_id = await support_inbox.forward(email_id, matched_addresses)
    except httpx.HTTPError as exc:
        # The message id only: the body and addresses stay out of the logs.
        logger.warning("Forwarding received email %s failed: %s", email_id, type(exc).__name__)
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail="Forwarding failed") from exc
    logger.info("Forwarded received email %s as %s", email_id, message_id)
    return {"status": "forwarded"}
