"""Async correction queue for failed evidence auto-linking retries."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.mission_protocol import MissionProtocolComplete
from app.schemas.corrections import (
    CorrectionErrorType,
    CorrectionItem,
    CorrectionQueueStats,
    CorrectionStatus,
    CorrectionStatusResponse,
    CorrectionTriggerResponse,
)
from app.services.evidence_auto_linking import (
    EvidenceAutoLinkingResult,
    EvidenceAutoLinkingService,
)
from app.services.webhook_client import (
    WebhookClient,
    create_failure_payload,
    create_success_payload,
)

logger = logging.getLogger(__name__)


# Retry backoff schedule (seconds): 5s, 30s per integration contract
BACKOFF_SCHEDULE = [5, 30]
MAX_RETRIES = 2


@dataclass
class CorrectionQueueItem:
    """Internal queue item representation."""

    correction_id: UUID
    mission_uuid: UUID
    mission_id: str
    evidence_id: str
    project_id: UUID | None
    status: CorrectionStatus
    error_type: CorrectionErrorType
    retry_count: int
    max_retries: int
    best_similarity: float | None
    similarity_threshold: float
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    next_retry_at: datetime | None
    callback_url: str | None
    evidence_summary: str


class CorrectionQueueService:
    """Manages async retry queue for failed evidence auto-linking.

    Per integration contract:
    - Max retries: 2
    - Backoff: exponential (5s, 30s)
    - On final failure: mark evidence as unlinked, webhook failure notification
    - On success: update chunk_id, webhook success notification
    """

    def __init__(
        self,
        auto_linker: EvidenceAutoLinkingService | None = None,
        webhook_client: WebhookClient | None = None,
        telemetry_path: Path | None = None,
    ) -> None:
        self._queue: dict[UUID, CorrectionQueueItem] = {}
        self._auto_linker = auto_linker or EvidenceAutoLinkingService()
        self._webhook_client = webhook_client or WebhookClient()
        self._processing = False
        self._stats = CorrectionQueueStats()

        repo_root = Path(__file__).resolve().parents[2]
        default_path = (
            repo_root / "cmos" / "telemetry" / "events" / "sprint-11-corrections.jsonl"
        )
        self.telemetry_path = telemetry_path or default_path

    def queue_failed_items(
        self,
        mission_uuid: UUID,
        mission_id: str,
        project_id: UUID | None,
        result: EvidenceAutoLinkingResult,
        callback_url: str | None = None,
        evidence_summaries: dict[str, str] | None = None,
    ) -> list[UUID]:
        """Queue failed auto-link items from an ingestion result.

        Returns list of correction IDs for the queued items.
        """
        queued_ids = []
        now = datetime.now(UTC)
        summaries = evidence_summaries or {}

        for error in result.errors:
            evidence_id = error.get("evidence_id", "")
            error_type_str = error.get(
                "error_type", CorrectionErrorType.LOW_SIMILARITY.value
            )

            # Skip non-retryable errors
            if error_type_str in (
                CorrectionErrorType.VALIDATION_ERROR.value,
                CorrectionErrorType.EMPTY_CONTENT.value,
            ):
                logger.debug(
                    "Skipping non-retryable error for %s: %s",
                    evidence_id,
                    error_type_str,
                )
                continue

            try:
                error_type = CorrectionErrorType(error_type_str)
            except ValueError:
                error_type = CorrectionErrorType.LOW_SIMILARITY

            correction_id = uuid4()
            item = CorrectionQueueItem(
                correction_id=correction_id,
                mission_uuid=mission_uuid,
                mission_id=mission_id,
                evidence_id=evidence_id,
                project_id=project_id,
                status=CorrectionStatus.PENDING,
                error_type=error_type,
                retry_count=0,
                max_retries=MAX_RETRIES,
                best_similarity=error.get("best_similarity"),
                similarity_threshold=error.get("threshold", result.threshold),
                last_error=error.get("message"),
                created_at=now,
                updated_at=now,
                next_retry_at=now + timedelta(seconds=BACKOFF_SCHEDULE[0]),
                callback_url=callback_url,
                evidence_summary=summaries.get(evidence_id, ""),
            )
            self._queue[correction_id] = item
            queued_ids.append(correction_id)

            self._log_telemetry("correction_queued", item)

        self._update_stats()
        return queued_ids

    async def process_pending(
        self,
        db_factory: Callable[[], Session],
        limit: int = 50,
    ) -> int:
        """Process pending corrections that are ready for retry.

        Returns number of items processed.
        """
        if self._processing:
            logger.warning("Correction queue already processing")
            return 0

        self._processing = True
        processed = 0
        now = datetime.now(UTC)

        try:
            ready_items = [
                item
                for item in self._queue.values()
                if item.status == CorrectionStatus.PENDING
                and item.next_retry_at is not None
                and item.next_retry_at <= now
            ][:limit]

            for item in ready_items:
                item.status = CorrectionStatus.IN_PROGRESS
                item.updated_at = now
                self._update_stats()

                try:
                    success = await self._retry_single(db_factory, item)
                    processed += 1

                    if success:
                        item.status = CorrectionStatus.COMPLETED
                        self._log_telemetry("correction_success", item)
                    else:
                        item.retry_count += 1
                        if item.retry_count >= item.max_retries:
                            item.status = CorrectionStatus.FAILED
                            self._log_telemetry("correction_exhausted", item)
                            await self._send_failure_notification(item)
                        else:
                            item.status = CorrectionStatus.PENDING
                            backoff_idx = min(
                                item.retry_count, len(BACKOFF_SCHEDULE) - 1
                            )
                            item.next_retry_at = now + timedelta(
                                seconds=BACKOFF_SCHEDULE[backoff_idx]
                            )
                            self._log_telemetry("correction_retry_scheduled", item)

                except Exception as e:
                    logger.exception(
                        "Error processing correction %s", item.correction_id
                    )
                    item.status = CorrectionStatus.PENDING
                    item.last_error = str(e)

                item.updated_at = datetime.now(UTC)

            self._update_stats()

        finally:
            self._processing = False

        return processed

    async def _retry_single(
        self,
        db_factory: Callable[[], Session],
        item: CorrectionQueueItem,
    ) -> bool:
        """Attempt to re-link a single evidence item.

        Returns True if successfully linked.
        """
        self._log_telemetry("correction_attempt", item)

        # Create a minimal mission with just this evidence for re-linking
        from app.models.mission_protocol import Evidence

        evidence = Evidence(
            evidence_id=item.evidence_id,
            summary=item.evidence_summary,
            chunk_id=None,
        )

        mock_mission = MissionProtocolComplete(
            mission_id=item.mission_id,
            title="Correction retry",
            version="1.0.0",
            status="active",
            research_statement={
                "topic": "Correction retry",
                "objective": "Re-link evidence",
                "scope": "Single item",
            },
            evidence=[evidence],
        )

        db = db_factory()
        try:
            result = self._auto_linker.link_evidence(
                db,
                mock_mission,
                project_id=item.project_id,
                similarity_threshold=item.similarity_threshold,
            )

            if result.linked > 0 and evidence.chunk_id:
                # Success - send notification
                await self._send_success_notification(
                    item, evidence.chunk_id, evidence.relevance_score or 0.0
                )
                return True

            # Failed - update item with latest error info
            if result.errors:
                error = result.errors[0]
                item.last_error = error.get("message", "Unknown error")
                item.best_similarity = error.get(
                    "best_similarity", item.best_similarity
                )

            return False

        finally:
            db.close()

    async def _send_success_notification(
        self,
        item: CorrectionQueueItem,
        chunk_id: str,
        similarity: float,
    ) -> None:
        """Send success webhook notification."""
        if not item.callback_url:
            return

        payload = create_success_payload(
            mission_uuid=item.mission_uuid,
            mission_id=item.mission_id,
            evidence_id=item.evidence_id,
            chunk_id=chunk_id,
            similarity=similarity,
            retry_count=item.retry_count,
        )
        await self._webhook_client.send_correction_notification(
            item.callback_url, payload
        )

    async def _send_failure_notification(
        self,
        item: CorrectionQueueItem,
    ) -> None:
        """Send failure webhook notification after retries exhausted."""
        if not item.callback_url:
            return

        payload = create_failure_payload(
            mission_uuid=item.mission_uuid,
            mission_id=item.mission_id,
            evidence_id=item.evidence_id,
            error_type=item.error_type.value,
            error_message=item.last_error or "Max retries exceeded",
            retry_count=item.retry_count,
            best_similarity=item.best_similarity,
        )
        await self._webhook_client.send_correction_notification(
            item.callback_url, payload
        )

    def trigger_retry(
        self,
        mission_uuid: UUID | None = None,
        evidence_ids: list[str] | None = None,
        force_retry: bool = False,
        callback_url: str | None = None,
    ) -> CorrectionTriggerResponse:
        """Trigger manual retry of pending corrections.

        Args:
            mission_uuid: Filter by specific mission
            evidence_ids: Filter by specific evidence IDs
            force_retry: Retry even if max attempts exceeded
            callback_url: Override webhook URL

        Returns:
            Response with count of triggered items
        """
        triggered = 0
        skipped = 0
        triggered_ids = []
        now = datetime.now(UTC)

        for item in self._queue.values():
            # Apply filters
            if mission_uuid and item.mission_uuid != mission_uuid:
                continue
            if evidence_ids and item.evidence_id not in evidence_ids:
                continue

            # Check if can retry
            if item.status == CorrectionStatus.COMPLETED:
                skipped += 1
                continue

            if item.status == CorrectionStatus.FAILED and not force_retry:
                skipped += 1
                continue

            # Queue for immediate retry
            if force_retry and item.retry_count >= item.max_retries:
                item.retry_count = 0  # Reset retry count

            item.status = CorrectionStatus.PENDING
            item.next_retry_at = now
            item.updated_at = now
            if callback_url:
                item.callback_url = callback_url

            triggered += 1
            triggered_ids.append(item.correction_id)

        self._update_stats()

        return CorrectionTriggerResponse(
            triggered=triggered,
            skipped=skipped,
            correction_ids=triggered_ids,
            message=f"Queued {triggered} items for retry, skipped {skipped}",
        )

    def get_status(self, limit: int = 20) -> CorrectionStatusResponse:
        """Get current queue status and statistics."""
        self._update_stats()

        # Calculate error distribution
        error_dist: dict[str, int] = {}
        for item in self._queue.values():
            if item.status in (CorrectionStatus.PENDING, CorrectionStatus.FAILED):
                key = item.error_type.value
                error_dist[key] = error_dist.get(key, 0) + 1

        # Get recent items
        recent = sorted(
            self._queue.values(),
            key=lambda x: x.updated_at,
            reverse=True,
        )[:limit]

        recent_items = [
            CorrectionItem(
                correction_id=item.correction_id,
                mission_uuid=item.mission_uuid,
                evidence_id=item.evidence_id,
                status=item.status,
                error_type=item.error_type,
                retry_count=item.retry_count,
                max_retries=item.max_retries,
                last_error=item.last_error,
                best_similarity=item.best_similarity,
                similarity_threshold=item.similarity_threshold,
                created_at=item.created_at,
                updated_at=item.updated_at,
                next_retry_at=item.next_retry_at,
                callback_url=item.callback_url,
            )
            for item in recent
        ]

        return CorrectionStatusResponse(
            stats=self._stats,
            error_distribution=error_dist,
            recent_items=recent_items,
            last_updated=datetime.now(UTC),
        )

    def _update_stats(self) -> None:
        """Recalculate queue statistics."""
        stats = CorrectionQueueStats()
        for item in self._queue.values():
            if item.status == CorrectionStatus.PENDING:
                stats.pending += 1
            elif item.status == CorrectionStatus.IN_PROGRESS:
                stats.in_progress += 1
            elif item.status == CorrectionStatus.COMPLETED:
                stats.completed += 1
            elif item.status == CorrectionStatus.FAILED:
                stats.failed += 1
            elif item.status == CorrectionStatus.SKIPPED:
                stats.skipped += 1
        stats.total = len(self._queue)
        self._stats = stats

    def _log_telemetry(self, event: str, item: CorrectionQueueItem) -> None:
        """Write telemetry record for Grafana dashboards."""
        record = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "event": event,
            "mission_id": item.mission_id,
            "evidence_id": item.evidence_id,
            "error_type": item.error_type.value,
            "retry_count": item.retry_count,
            "similarity": item.best_similarity,
            "threshold": item.similarity_threshold,
            "status": item.status.value,
            "success": item.status == CorrectionStatus.COMPLETED,
        }
        try:
            self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
            with self.telemetry_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Failed to write correction telemetry: %s", e)

    def get_telemetry_summary(self) -> dict[str, Any]:
        """Generate Grafana-ready telemetry summary."""
        self._update_stats()
        return {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "event": "correction_summary",
            "pending": self._stats.pending,
            "in_progress": self._stats.in_progress,
            "completed": self._stats.completed,
            "failed": self._stats.failed,
            "skipped": self._stats.skipped,
            "total": self._stats.total,
            "success_rate": self._stats.success_rate,
            "webhook_stats": self._webhook_client.get_stats(),
        }

    def clear_completed(self) -> int:
        """Remove completed items from queue. Returns count removed."""
        to_remove = [
            cid
            for cid, item in self._queue.items()
            if item.status in (CorrectionStatus.COMPLETED, CorrectionStatus.SKIPPED)
        ]
        for cid in to_remove:
            del self._queue[cid]
        self._update_stats()
        return len(to_remove)


# Global singleton for the correction queue
_correction_queue: CorrectionQueueService | None = None


def get_correction_queue() -> CorrectionQueueService:
    """Get or create the global correction queue instance."""
    global _correction_queue
    if _correction_queue is None:
        _correction_queue = CorrectionQueueService()
    return _correction_queue
