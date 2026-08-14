"""Webhook handler service for processing DeepSearch callbacks.

Handles incoming webhook payloads from DeepSearch and updates mission records.
Includes signature validation, idempotent processing, and auto-ingestion of results.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.mission import Mission
from app.schemas.mission import MissionUpdate
from app.schemas.webhook import DeepSearchWebhookPayload, DeepSearchWebhookStatus
from app.services.auto_ingest import AutoIngestService
from app.services.auto_report import AutoReportService
from app.services.mission_service import MissionNotFoundError, MissionService
from app.services.result_materialization import MissionResultMaterializationService

logger = logging.getLogger(__name__)


class WebhookValidationError(RuntimeError):
    """Raised when webhook authentication or attempt correlation fails."""


class WebhookProcessingError(RuntimeError):
    """Raised when webhook processing fails."""


class WebhookHandler:
    """Handles DeepSearch webhook callbacks with validation and idempotency."""

    def __init__(
        self,
        mission_service: MissionService | None = None,
        auto_ingest_service: AutoIngestService | None = None,
        auto_report_service: AutoReportService | None = None,
    ):
        self._mission_service = mission_service or MissionService()
        self._auto_ingest_service = auto_ingest_service
        self._auto_report_service = auto_report_service
        self._materialization_service: MissionResultMaterializationService | None = None

    def validate_signature(
        self,
        payload_body: bytes,
        signature: str | None,
        timestamp: str | None = None,
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
        # T40.4: prefer the renamed shared secret; fall back to the legacy
        # deepsearch_webhook_secret for back-compat during the transition.
        secret = settings.effective_deepsearch_service_secret

        # Local development may run without DeepSearch, but deployed callbacks
        # must never become unsigned because ENVIRONMENT or a secret was missed.
        if not secret:
            environment = settings.environment.strip().lower()
            unsigned_local_mode = environment in {
                "development",
                "dev",
                "local",
            } and bool(settings.debug)
            unsigned_test_mode = environment in {"test", "testing"}
            if not (unsigned_local_mode or unsigned_test_mode):
                raise WebhookValidationError(
                    "DeepSearch service secret is not configured"
                )
            logger.warning(
                "Webhook signature validation skipped in development - "
                "no secret configured"
            )
            return True

        if not signature:
            raise WebhookValidationError("Missing X-DeepSearch-Signature header")

        # Parse signature format: sha256=<hex>
        if not signature.startswith("sha256="):
            raise WebhookValidationError(
                "Invalid signature format - expected sha256=<hex>"
            )

        provided_signature = signature[7:]  # Remove 'sha256=' prefix

        # Build message to sign (include timestamp if provided for replay protection)
        decoded_body = payload_body.decode("utf-8")
        message = f"{timestamp}.{decoded_body}" if timestamp else decoded_body

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
    ) -> tuple[Mission, str]:
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
            mission = self._mission_service.get_mission_by_mission_id(
                db, payload.mission_id
            )
        except MissionNotFoundError:
            logger.error("Mission not found for webhook: %s", payload.mission_id)
            raise

        # Lease-v2 terminal writes persist the generated job ID with the fenced
        # result key. HMAC authenticates DeepSearch as a service; this comparison
        # authenticates the specific attempt. Legacy rows with no stored job ID
        # retain the one-run fallback until they are backfilled or replayed.
        if (
            mission.deepsearch_job_id is not None
            and payload.job_id != mission.deepsearch_job_id
        ):
            raise WebhookValidationError(
                "Webhook job_id does not match the persisted mission attempt"
            )

        # DeepSearch's fenced writer commits terminal state before sending the
        # receipt. That row is authoritative. Because terminal missions cannot
        # be resubmitted in place, the legacy NULL-job fallback cannot target a
        # later attempt on the same mission row.
        if mission.status in ("completed", "validation_failed", "cancelled"):
            if (
                mission.status in ("completed", "validation_failed")
                and payload.status == DeepSearchWebhookStatus.COMPLETE
            ):
                outcome = self._get_materialization_service().materialize(db, mission)
                if outcome.errors:
                    raise WebhookProcessingError(
                        "Mission completed but result materialization is incomplete: "
                        + "; ".join(outcome.errors)
                    )
                if outcome.changed:
                    logger.info(
                        "Reconciled persisted results for completed mission %s",
                        payload.mission_id,
                    )
                    return mission, "reconciled"
            logger.info(
                "Webhook acknowledged against authoritative terminal row: mission=%s, job=%s",
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

    def _get_auto_ingest_service(self) -> AutoIngestService:
        """Lazily initialize auto-ingest service."""
        if self._auto_ingest_service is None:
            self._auto_ingest_service = AutoIngestService()
        return self._auto_ingest_service

    def _get_auto_report_service(self) -> AutoReportService:
        """Lazily initialize auto-report service."""
        if self._auto_report_service is None:
            self._auto_report_service = AutoReportService()
        return self._auto_report_service

    def _get_materialization_service(self) -> MissionResultMaterializationService:
        """Lazily compose the shared webhook/reconciliation materializer."""
        if self._materialization_service is None:
            self._materialization_service = MissionResultMaterializationService(
                auto_ingest_service=self._get_auto_ingest_service(),
                auto_report_service=self._get_auto_report_service(),
            )
        return self._materialization_service

    def _handle_success(
        self,
        db: Session,
        mission: Mission,
        payload: DeepSearchWebhookPayload,
    ) -> tuple[Mission, str]:
        """Handle successful job completion.

        Updates mission with results, marks as completed, and auto-ingests
        result_markdown as a document if available.
        """
        # DeepSearch's direct writer may already have persisted the result. A
        # minimal completion receipt intentionally omits those large fields, so
        # only non-None payload values may replace stored data.
        update_fields: dict[str, object] = {
            "status": "completed",
            "deepsearch_job_id": payload.job_id,
            "error_message": None,
        }
        if payload.execution_metadata is not None:
            update_fields["execution_metadata"] = (
                payload.execution_metadata.model_dump()
            )
        if payload.result_markdown is not None:
            update_fields["result_markdown"] = payload.result_markdown
        if payload.result_protocol is not None:
            update_fields["result_protocol"] = payload.result_protocol
        update_data = MissionUpdate(**update_fields)

        updated_mission = self._mission_service.update_mission(
            db, mission.id, update_data
        )

        logger.info(
            "Mission completed via webhook: %s (job: %s)",
            payload.mission_id,
            payload.job_id,
        )

        outcome = self._get_materialization_service().materialize(db, updated_mission)
        if outcome.errors:
            raise WebhookProcessingError(
                "Mission completed but result materialization is incomplete: "
                + "; ".join(outcome.errors)
            )

        return updated_mission, "completed"

    def _handle_failure(
        self,
        db: Session,
        mission: Mission,
        payload: DeepSearchWebhookPayload,
    ) -> tuple[Mission, str]:
        """Handle job failure.

        Updates mission with error and marks as blocked.
        """
        update_data = MissionUpdate(
            status="blocked",
            deepsearch_job_id=payload.job_id,
            execution_metadata=payload.execution_metadata.model_dump()
            if payload.execution_metadata
            else {},
            error_message=payload.error
            or "DeepSearch job failed without error message",
        )

        updated_mission = self._mission_service.update_mission(
            db, mission.id, update_data
        )

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
    ) -> tuple[Mission, str]:
        """Handle job cancellation.

        Updates mission status to cancelled.
        """
        update_data = MissionUpdate(
            status="cancelled",
            deepsearch_job_id=payload.job_id,
            execution_metadata=payload.execution_metadata.model_dump()
            if payload.execution_metadata
            else {},
            error_message=payload.error or "Job was cancelled",
        )

        updated_mission = self._mission_service.update_mission(
            db, mission.id, update_data
        )

        logger.info(
            "Mission cancelled via webhook: %s (job: %s)",
            payload.mission_id,
            payload.job_id,
        )

        return updated_mission, "cancelled"


# Module-level singleton for convenience
_handler: WebhookHandler | None = None


def get_webhook_handler() -> WebhookHandler:
    """Get or create the webhook handler instance."""
    global _handler
    if _handler is None:
        _handler = WebhookHandler()
    return _handler
