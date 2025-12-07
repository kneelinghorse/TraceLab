"""Webhook handler service for processing DeepSearch callbacks.

Handles incoming webhook payloads from DeepSearch and updates mission records.
Includes signature validation and idempotent processing.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.mission import Mission
from app.schemas.mission import MissionUpdate
from app.schemas.webhook import DeepSearchWebhookPayload, DeepSearchWebhookStatus
from app.services.mission_service import MissionNotFoundError, MissionService

logger = logging.getLogger(__name__)


class WebhookValidationError(RuntimeError):
    """Raised when webhook signature validation fails."""


class WebhookProcessingError(RuntimeError):
    """Raised when webhook processing fails."""


class WebhookHandler:
    """Handles DeepSearch webhook callbacks with validation and idempotency."""

    def __init__(self, mission_service: Optional[MissionService] = None):
        self._mission_service = mission_service or MissionService()

    def validate_signature(
        self,
        payload_body: bytes,
        signature: Optional[str],
        timestamp: Optional[str] = None,
    ) -> bool:
        """Validate webhook signature using HMAC-SHA256.

        The signature should be in format: sha256=<hex_digest>

        Args:
            payload_body: Raw request body bytes
            signature: X-DeepSearch-Signature header value
            timestamp: X-DeepSearch-Timestamp header value (optional, for replay protection)

        Returns:
            True if signature is valid

        Raises:
            WebhookValidationError: If signature is missing or invalid
        """
        secret = settings.deepsearch_webhook_secret

        # If no secret configured, skip validation (development mode)
        if not secret:
            logger.warning("Webhook signature validation skipped - no secret configured")
            return True

        if not signature:
            raise WebhookValidationError("Missing X-DeepSearch-Signature header")

        # Parse signature format: sha256=<hex>
        if not signature.startswith("sha256="):
            raise WebhookValidationError("Invalid signature format - expected sha256=<hex>")

        provided_signature = signature[7:]  # Remove 'sha256=' prefix

        # Build message to sign (include timestamp if provided for replay protection)
        if timestamp:
            message = f"{timestamp}.{payload_body.decode('utf-8')}"
        else:
            message = payload_body.decode("utf-8")

        # Compute expected signature
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise WebhookValidationError("Invalid webhook signature")

        return True

    def process_deepsearch_webhook(
        self,
        db: Session,
        payload: DeepSearchWebhookPayload,
    ) -> Tuple[Mission, str]:
        """Process a DeepSearch webhook callback.

        Updates the mission record based on the webhook payload.
        Designed to be idempotent - safe to process the same webhook twice.

        Args:
            db: Database session
            payload: Validated webhook payload

        Returns:
            Tuple of (updated Mission, status message)

        Raises:
            MissionNotFoundError: If mission_id doesn't exist
            WebhookProcessingError: If processing fails
        """
        logger.info(
            "Processing DeepSearch webhook: job_id=%s, mission_id=%s, status=%s",
            payload.job_id,
            payload.mission_id,
            payload.status.value,
        )

        # Find mission by human-readable mission_id
        try:
            mission = self._mission_service.get_mission_by_mission_id(db, payload.mission_id)
        except MissionNotFoundError:
            logger.error("Mission not found for webhook: %s", payload.mission_id)
            raise

        # Idempotency check: if mission already completed/failed, skip processing
        if mission.status in ("completed", "cancelled"):
            if mission.deepsearch_job_id == payload.job_id:
                logger.info(
                    "Webhook already processed (idempotent): mission=%s, job=%s",
                    payload.mission_id,
                    payload.job_id,
                )
                return mission, "already_processed"

        # Build update based on webhook status
        if payload.status == DeepSearchWebhookStatus.COMPLETE:
            return self._handle_success(db, mission, payload)
        elif payload.status == DeepSearchWebhookStatus.FAILED:
            return self._handle_failure(db, mission, payload)
        elif payload.status == DeepSearchWebhookStatus.CANCELLED:
            return self._handle_cancellation(db, mission, payload)
        else:
            raise WebhookProcessingError(f"Unhandled webhook status: {payload.status}")

    def _handle_success(
        self,
        db: Session,
        mission: Mission,
        payload: DeepSearchWebhookPayload,
    ) -> Tuple[Mission, str]:
        """Handle successful job completion.

        Updates mission with results and marks as completed.
        """
        update_data = MissionUpdate(
            status="completed",
            deepsearch_job_id=payload.job_id,
            execution_metadata=payload.execution_metadata.model_dump() if payload.execution_metadata else {},
            result_markdown=payload.result_markdown,
            result_protocol=payload.result_protocol,
            error_message=None,  # Clear any previous error
        )

        updated_mission = self._mission_service.update_mission(db, mission.id, update_data)

        logger.info(
            "Mission completed via webhook: %s (job: %s)",
            payload.mission_id,
            payload.job_id,
        )

        return updated_mission, "completed"

    def _handle_failure(
        self,
        db: Session,
        mission: Mission,
        payload: DeepSearchWebhookPayload,
    ) -> Tuple[Mission, str]:
        """Handle job failure.

        Updates mission with error and marks as blocked.
        """
        update_data = MissionUpdate(
            status="blocked",
            deepsearch_job_id=payload.job_id,
            execution_metadata=payload.execution_metadata.model_dump() if payload.execution_metadata else {},
            error_message=payload.error or "DeepSearch job failed without error message",
        )

        updated_mission = self._mission_service.update_mission(db, mission.id, update_data)

        logger.warning(
            "Mission failed via webhook: %s (job: %s, error: %s)",
            payload.mission_id,
            payload.job_id,
            payload.error,
        )

        return updated_mission, "failed"

    def _handle_cancellation(
        self,
        db: Session,
        mission: Mission,
        payload: DeepSearchWebhookPayload,
    ) -> Tuple[Mission, str]:
        """Handle job cancellation.

        Updates mission status to cancelled.
        """
        update_data = MissionUpdate(
            status="cancelled",
            deepsearch_job_id=payload.job_id,
            execution_metadata=payload.execution_metadata.model_dump() if payload.execution_metadata else {},
            error_message=payload.error or "Job was cancelled",
        )

        updated_mission = self._mission_service.update_mission(db, mission.id, update_data)

        logger.info(
            "Mission cancelled via webhook: %s (job: %s)",
            payload.mission_id,
            payload.job_id,
        )

        return updated_mission, "cancelled"


# Module-level singleton for convenience
_handler: Optional[WebhookHandler] = None


def get_webhook_handler() -> WebhookHandler:
    """Get or create the webhook handler instance."""
    global _handler
    if _handler is None:
        _handler = WebhookHandler()
    return _handler
