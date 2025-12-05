"""Webhook client for DeepSearch callback notifications."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx

from app.schemas.corrections import (
    BatchWebhookPayload,
    WebhookNotificationType,
    WebhookPayload,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WebhookDeliveryResult:
    """Result of a webhook delivery attempt."""

    success: bool
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: int = 0
    attempt: int = 1


@dataclass
class WebhookDeliveryStats:
    """Aggregated webhook delivery statistics."""

    total_sent: int = 0
    successful: int = 0
    failed: int = 0
    retried: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_sent == 0:
            return 0.0
        return round(self.successful / self.total_sent, 3)


class WebhookClient:
    """Async webhook client for DeepSearch callback notifications.

    Supports retry with exponential backoff and dead letter queue.
    """

    DEFAULT_TIMEOUT = 10.0  # seconds
    MAX_RETRIES = 3
    BACKOFF_MULTIPLIER = 2.0
    INITIAL_BACKOFF = 1.0  # seconds

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        telemetry_path: Optional[Path] = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.stats = WebhookDeliveryStats()
        repo_root = Path(__file__).resolve().parents[2]
        default_path = repo_root / "cmos" / "telemetry" / "events" / "sprint-11-corrections.jsonl"
        self.telemetry_path = telemetry_path or default_path
        self._dead_letter_queue: List[Dict[str, Any]] = []

    async def send_correction_notification(
        self,
        callback_url: str,
        payload: WebhookPayload,
    ) -> WebhookDeliveryResult:
        """Send individual correction notification to DeepSearch."""
        return await self._send_with_retry(
            callback_url,
            payload.model_dump(mode="json"),
            context={"mission_uuid": str(payload.mission_uuid), "evidence_id": payload.evidence_id},
        )

    async def send_batch_notification(
        self,
        callback_url: str,
        payload: BatchWebhookPayload,
    ) -> WebhookDeliveryResult:
        """Send batch completion notification to DeepSearch."""
        return await self._send_with_retry(
            callback_url,
            payload.model_dump(mode="json"),
            context={"mission_uuid": str(payload.mission_uuid), "type": "batch"},
        )

    async def _send_with_retry(
        self,
        url: str,
        payload: Dict[str, Any],
        context: Optional[Dict[str, str]] = None,
    ) -> WebhookDeliveryResult:
        """Send webhook with exponential backoff retry."""
        self.stats.total_sent += 1
        backoff = self.INITIAL_BACKOFF
        last_result: Optional[WebhookDeliveryResult] = None

        for attempt in range(1, self.max_retries + 1):
            start = datetime.now(timezone.utc)
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        url,
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "TraceLab-Webhook-Client/1.0",
                            "X-TraceLab-Event": payload.get("notification_type", "unknown"),
                        },
                    )

                duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

                if response.is_success:
                    self.stats.successful += 1
                    result = WebhookDeliveryResult(
                        success=True,
                        status_code=response.status_code,
                        response_body=response.text[:500] if response.text else None,
                        duration_ms=duration_ms,
                        attempt=attempt,
                    )
                    self._log_telemetry("webhook_success", payload, result, context)
                    return result

                # Non-success HTTP status
                last_result = WebhookDeliveryResult(
                    success=False,
                    status_code=response.status_code,
                    response_body=response.text[:500] if response.text else None,
                    error_message=f"HTTP {response.status_code}",
                    duration_ms=duration_ms,
                    attempt=attempt,
                )

            except httpx.TimeoutException as e:
                duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
                last_result = WebhookDeliveryResult(
                    success=False,
                    error_message=f"Timeout: {e}",
                    duration_ms=duration_ms,
                    attempt=attempt,
                )

            except httpx.RequestError as e:
                duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
                last_result = WebhookDeliveryResult(
                    success=False,
                    error_message=f"Request error: {e}",
                    duration_ms=duration_ms,
                    attempt=attempt,
                )

            # Retry logic
            if attempt < self.max_retries:
                self.stats.retried += 1
                logger.warning(
                    "Webhook delivery failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt,
                    self.max_retries,
                    backoff,
                    last_result.error_message if last_result else "Unknown error",
                )
                await asyncio.sleep(backoff)
                backoff *= self.BACKOFF_MULTIPLIER

        # All retries exhausted
        self.stats.failed += 1
        if last_result:
            self._log_telemetry("webhook_failed", payload, last_result, context)
            self._add_to_dead_letter(url, payload, last_result, context)
        return last_result or WebhookDeliveryResult(
            success=False,
            error_message="All retry attempts exhausted",
            attempt=self.max_retries,
        )

    def _add_to_dead_letter(
        self,
        url: str,
        payload: Dict[str, Any],
        result: WebhookDeliveryResult,
        context: Optional[Dict[str, str]],
    ) -> None:
        """Add failed webhook to dead letter queue for later inspection."""
        self._dead_letter_queue.append({
            "url": url,
            "payload": payload,
            "error": result.error_message,
            "status_code": result.status_code,
            "attempts": result.attempt,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": context or {},
        })
        # Keep queue bounded
        if len(self._dead_letter_queue) > 1000:
            self._dead_letter_queue = self._dead_letter_queue[-1000:]

    def get_dead_letter_queue(self) -> List[Dict[str, Any]]:
        """Return failed webhook deliveries for inspection."""
        return list(self._dead_letter_queue)

    def clear_dead_letter_queue(self) -> int:
        """Clear dead letter queue, return count of cleared items."""
        count = len(self._dead_letter_queue)
        self._dead_letter_queue.clear()
        return count

    def _log_telemetry(
        self,
        event: str,
        payload: Dict[str, Any],
        result: WebhookDeliveryResult,
        context: Optional[Dict[str, str]],
    ) -> None:
        """Write telemetry record for Grafana dashboards."""
        record = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event,
            "mission_id": payload.get("mission_id", ""),
            "evidence_id": payload.get("evidence_id"),
            "notification_type": payload.get("notification_type"),
            "success": result.success,
            "status_code": result.status_code,
            "duration_ms": result.duration_ms,
            "attempt": result.attempt,
            "error": result.error_message,
            "context": context or {},
        }
        try:
            self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
            with self.telemetry_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Failed to write webhook telemetry: %s", e)

    def get_stats(self) -> Dict[str, Any]:
        """Return current delivery statistics."""
        return {
            "total_sent": self.stats.total_sent,
            "successful": self.stats.successful,
            "failed": self.stats.failed,
            "retried": self.stats.retried,
            "success_rate": self.stats.success_rate,
            "dead_letter_count": len(self._dead_letter_queue),
        }


# Synchronous wrapper for non-async contexts
def send_webhook_sync(
    callback_url: str,
    payload: WebhookPayload,
    *,
    timeout: float = WebhookClient.DEFAULT_TIMEOUT,
) -> WebhookDeliveryResult:
    """Synchronous wrapper for webhook delivery."""
    client = WebhookClient(timeout=timeout, max_retries=1)
    return asyncio.run(client.send_correction_notification(callback_url, payload))


def create_success_payload(
    mission_uuid: UUID,
    mission_id: str,
    evidence_id: str,
    chunk_id: str,
    similarity: float,
    retry_count: int = 0,
) -> WebhookPayload:
    """Create a success notification payload."""
    return WebhookPayload(
        notification_type=WebhookNotificationType.CORRECTION_SUCCESS,
        mission_uuid=mission_uuid,
        mission_id=mission_id,
        evidence_id=evidence_id,
        timestamp=datetime.now(timezone.utc),
        success=True,
        chunk_id=chunk_id,
        similarity=similarity,
        retry_count=retry_count,
    )


def create_failure_payload(
    mission_uuid: UUID,
    mission_id: str,
    evidence_id: str,
    error_type: str,
    error_message: str,
    retry_count: int = 0,
    best_similarity: Optional[float] = None,
) -> WebhookPayload:
    """Create a failure notification payload."""
    return WebhookPayload(
        notification_type=WebhookNotificationType.CORRECTION_FAILURE,
        mission_uuid=mission_uuid,
        mission_id=mission_id,
        evidence_id=evidence_id,
        timestamp=datetime.now(timezone.utc),
        success=False,
        error_type=error_type,
        error_message=error_message,
        retry_count=retry_count,
        similarity=best_similarity,
    )
