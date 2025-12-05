"""Tests for correction loop: retry logic and webhook delivery."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.orm import Session

from app.schemas.corrections import (
    CorrectionErrorType,
    CorrectionStatus,
    WebhookNotificationType,
)
from app.services.correction_queue import (
    BACKOFF_SCHEDULE,
    MAX_RETRIES,
    CorrectionQueueItem,
    CorrectionQueueService,
    get_correction_queue,
)
from app.services.evidence_auto_linking import (
    AutoLinkErrorType,
    EvidenceAutoLinkingResult,
    EvidenceAutoLinkingService,
)
from app.services.webhook_client import (
    WebhookClient,
    WebhookDeliveryResult,
    create_failure_payload,
    create_success_payload,
)


# Fixtures
@pytest.fixture
def temp_telemetry_path(tmp_path: Path) -> Path:
    """Create a temporary telemetry path for testing."""
    return tmp_path / "test-corrections.jsonl"


@pytest.fixture
def webhook_client(temp_telemetry_path: Path) -> WebhookClient:
    """Create a webhook client with temporary telemetry."""
    return WebhookClient(telemetry_path=temp_telemetry_path)


@pytest.fixture
def correction_queue(temp_telemetry_path: Path) -> CorrectionQueueService:
    """Create a correction queue service for testing."""
    return CorrectionQueueService(telemetry_path=temp_telemetry_path)


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Create a mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def sample_auto_link_result() -> EvidenceAutoLinkingResult:
    """Create a sample auto-linking result with failures."""
    result = EvidenceAutoLinkingResult(
        attempted=3,
        linked=1,
        skipped=0,
        failed=2,
        threshold=0.7,
    )
    result.matches = [
        {
            "evidence_id": "EV-001",
            "chunk_id": "chunk-123",
            "similarity": 0.85,
            "success": True,
            "error_type": None,
        },
        {
            "evidence_id": "EV-002",
            "chunk_id": None,
            "similarity": 0.55,
            "success": False,
            "error_type": AutoLinkErrorType.LOW_SIMILARITY.value,
        },
        {
            "evidence_id": "EV-003",
            "chunk_id": None,
            "similarity": 0.0,
            "success": False,
            "error_type": AutoLinkErrorType.NO_CHUNKS.value,
        },
    ]
    result.errors = [
        {
            "evidence_id": "EV-002",
            "error_type": AutoLinkErrorType.LOW_SIMILARITY.value,
            "message": "Best match (0.55) below threshold (0.7)",
            "best_similarity": 0.55,
            "threshold": 0.7,
        },
        {
            "evidence_id": "EV-003",
            "error_type": AutoLinkErrorType.NO_CHUNKS.value,
            "message": "No chunks exist in project for matching",
        },
    ]
    return result


class TestAutoLinkErrorType:
    """Tests for error taxonomy enum."""

    def test_all_error_types_defined(self):
        """Verify all 7 error types are defined."""
        expected = {
            "no_embedding",
            "low_similarity",
            "no_chunks",
            "timeout",
            "validation_error",
            "empty_content",
            "database_error",
        }
        actual = {e.value for e in AutoLinkErrorType}
        assert actual == expected

    def test_error_type_string_values(self):
        """Verify error types have correct string values."""
        assert AutoLinkErrorType.NO_EMBEDDING.value == "no_embedding"
        assert AutoLinkErrorType.LOW_SIMILARITY.value == "low_similarity"
        assert AutoLinkErrorType.TIMEOUT.value == "timeout"


class TestWebhookClient:
    """Tests for webhook delivery client."""

    @pytest.mark.asyncio
    async def test_successful_delivery(self, webhook_client: WebhookClient):
        """Test successful webhook delivery."""
        payload = create_success_payload(
            mission_uuid=uuid4(),
            mission_id="TEST-001",
            evidence_id="EV-001",
            chunk_id="chunk-123",
            similarity=0.85,
        )

        with patch.object(
            httpx.AsyncClient,
            "post",
            new_callable=AsyncMock,
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.is_success = True
            mock_response.text = '{"status": "received"}'
            mock_post.return_value = mock_response

            result = await webhook_client.send_correction_notification(
                "https://deepsearch.example/webhook",
                payload,
            )

            assert result.success is True
            assert result.status_code == 200
            assert webhook_client.stats.successful == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, webhook_client: WebhookClient):
        """Test exponential backoff retry on failure."""
        payload = create_failure_payload(
            mission_uuid=uuid4(),
            mission_id="TEST-001",
            evidence_id="EV-001",
            error_type="low_similarity",
            error_message="Below threshold",
        )

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("Connection timeout")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.is_success = True
            mock_response.text = '{"status": "received"}'
            return mock_response

        with patch.object(
            httpx.AsyncClient,
            "post",
            side_effect=mock_post,
        ):
            result = await webhook_client.send_correction_notification(
                "https://deepsearch.example/webhook",
                payload,
            )

            assert result.success is True
            assert call_count == 3
            assert webhook_client.stats.retried >= 2

    @pytest.mark.asyncio
    async def test_dead_letter_queue(self, webhook_client: WebhookClient):
        """Test failed deliveries go to dead letter queue."""
        payload = create_failure_payload(
            mission_uuid=uuid4(),
            mission_id="TEST-001",
            evidence_id="EV-001",
            error_type="timeout",
            error_message="Service unavailable",
        )

        with patch.object(
            httpx.AsyncClient,
            "post",
            side_effect=httpx.TimeoutException("Timeout"),
        ):
            result = await webhook_client.send_correction_notification(
                "https://deepsearch.example/webhook",
                payload,
            )

            assert result.success is False
            assert len(webhook_client.get_dead_letter_queue()) == 1
            dlq_item = webhook_client.get_dead_letter_queue()[0]
            assert dlq_item["url"] == "https://deepsearch.example/webhook"

    def test_create_success_payload(self):
        """Test success payload creation."""
        mission_uuid = uuid4()
        payload = create_success_payload(
            mission_uuid=mission_uuid,
            mission_id="TEST-001",
            evidence_id="EV-001",
            chunk_id="chunk-123",
            similarity=0.85,
            retry_count=1,
        )

        assert payload.notification_type == WebhookNotificationType.CORRECTION_SUCCESS
        assert payload.mission_uuid == mission_uuid
        assert payload.success is True
        assert payload.chunk_id == "chunk-123"
        assert payload.similarity == 0.85
        assert payload.retry_count == 1

    def test_create_failure_payload(self):
        """Test failure payload creation."""
        mission_uuid = uuid4()
        payload = create_failure_payload(
            mission_uuid=mission_uuid,
            mission_id="TEST-001",
            evidence_id="EV-001",
            error_type="low_similarity",
            error_message="Below threshold",
            best_similarity=0.55,
        )

        assert payload.notification_type == WebhookNotificationType.CORRECTION_FAILURE
        assert payload.success is False
        assert payload.error_type == "low_similarity"
        assert payload.similarity == 0.55


class TestCorrectionQueueService:
    """Tests for correction queue service."""

    def test_queue_failed_items(
        self,
        correction_queue: CorrectionQueueService,
        sample_auto_link_result: EvidenceAutoLinkingResult,
    ):
        """Test queuing failed auto-link items."""
        mission_uuid = uuid4()

        queued_ids = correction_queue.queue_failed_items(
            mission_uuid=mission_uuid,
            mission_id="TEST-001",
            project_id=uuid4(),
            result=sample_auto_link_result,
            callback_url="https://deepsearch.example/webhook",
        )

        # Should queue 2 items (LOW_SIMILARITY and NO_CHUNKS)
        assert len(queued_ids) == 2
        status = correction_queue.get_status()
        assert status.stats.pending == 2
        assert status.stats.total == 2

    def test_skip_non_retryable_errors(
        self,
        correction_queue: CorrectionQueueService,
    ):
        """Test that validation errors are not queued."""
        result = EvidenceAutoLinkingResult(attempted=2, failed=2)
        result.errors = [
            {
                "evidence_id": "EV-001",
                "error_type": AutoLinkErrorType.VALIDATION_ERROR.value,
                "message": "Invalid structure",
            },
            {
                "evidence_id": "EV-002",
                "error_type": AutoLinkErrorType.EMPTY_CONTENT.value,
                "message": "Empty content",
            },
        ]

        queued_ids = correction_queue.queue_failed_items(
            mission_uuid=uuid4(),
            mission_id="TEST-001",
            project_id=uuid4(),
            result=result,
        )

        # Non-retryable errors should not be queued
        assert len(queued_ids) == 0
        assert correction_queue.get_status().stats.total == 0

    def test_trigger_retry(
        self,
        correction_queue: CorrectionQueueService,
        sample_auto_link_result: EvidenceAutoLinkingResult,
    ):
        """Test manual retry trigger."""
        mission_uuid = uuid4()
        correction_queue.queue_failed_items(
            mission_uuid=mission_uuid,
            mission_id="TEST-001",
            project_id=uuid4(),
            result=sample_auto_link_result,
        )

        response = correction_queue.trigger_retry(mission_uuid=mission_uuid)

        assert response.triggered == 2
        assert len(response.correction_ids) == 2

    def test_force_retry_failed_items(
        self,
        correction_queue: CorrectionQueueService,
    ):
        """Test force retry of failed items."""
        # Create a failed item manually
        now = datetime.now(timezone.utc)
        item = CorrectionQueueItem(
            correction_id=uuid4(),
            mission_uuid=uuid4(),
            mission_id="TEST-001",
            evidence_id="EV-001",
            project_id=uuid4(),
            status=CorrectionStatus.FAILED,
            error_type=CorrectionErrorType.LOW_SIMILARITY,
            retry_count=MAX_RETRIES,
            max_retries=MAX_RETRIES,
            best_similarity=0.5,
            similarity_threshold=0.7,
            last_error="Max retries exceeded",
            created_at=now,
            updated_at=now,
            next_retry_at=None,
            callback_url=None,
            evidence_summary="Test evidence",
        )
        correction_queue._queue[item.correction_id] = item

        # Without force_retry, should be skipped
        response = correction_queue.trigger_retry()
        assert response.triggered == 0
        assert response.skipped == 1

        # With force_retry, should be triggered
        response = correction_queue.trigger_retry(force_retry=True)
        assert response.triggered == 1

    def test_error_distribution(
        self,
        correction_queue: CorrectionQueueService,
        sample_auto_link_result: EvidenceAutoLinkingResult,
    ):
        """Test error distribution in status."""
        correction_queue.queue_failed_items(
            mission_uuid=uuid4(),
            mission_id="TEST-001",
            project_id=uuid4(),
            result=sample_auto_link_result,
        )

        status = correction_queue.get_status()

        assert "low_similarity" in status.error_distribution
        assert "no_chunks" in status.error_distribution
        assert status.error_distribution["low_similarity"] == 1
        assert status.error_distribution["no_chunks"] == 1

    def test_clear_completed(
        self,
        correction_queue: CorrectionQueueService,
    ):
        """Test clearing completed items."""
        now = datetime.now(timezone.utc)

        # Add completed and pending items
        for i, status in enumerate([CorrectionStatus.COMPLETED, CorrectionStatus.PENDING, CorrectionStatus.FAILED]):
            item = CorrectionQueueItem(
                correction_id=uuid4(),
                mission_uuid=uuid4(),
                mission_id="TEST-001",
                evidence_id=f"EV-{i:03d}",
                project_id=uuid4(),
                status=status,
                error_type=CorrectionErrorType.LOW_SIMILARITY,
                retry_count=0,
                max_retries=MAX_RETRIES,
                best_similarity=0.5,
                similarity_threshold=0.7,
                last_error=None,
                created_at=now,
                updated_at=now,
                next_retry_at=now,
                callback_url=None,
                evidence_summary="",
            )
            correction_queue._queue[item.correction_id] = item

        assert correction_queue.get_status().stats.total == 3

        cleared = correction_queue.clear_completed()

        assert cleared == 1  # Only COMPLETED items cleared
        assert correction_queue.get_status().stats.total == 2


class TestBackoffSchedule:
    """Tests for retry backoff schedule."""

    def test_backoff_schedule_values(self):
        """Verify backoff schedule matches integration contract."""
        assert BACKOFF_SCHEDULE == [5, 30]
        assert MAX_RETRIES == 2

    def test_backoff_progression(
        self,
        correction_queue: CorrectionQueueService,
        sample_auto_link_result: EvidenceAutoLinkingResult,
    ):
        """Test that retry scheduling uses correct backoff."""
        correction_queue.queue_failed_items(
            mission_uuid=uuid4(),
            mission_id="TEST-001",
            project_id=uuid4(),
            result=sample_auto_link_result,
        )

        # Check initial schedule
        for item in correction_queue._queue.values():
            assert item.next_retry_at is not None
            # First retry should be ~5 seconds from now
            time_until = (item.next_retry_at - datetime.now(timezone.utc)).total_seconds()
            assert 0 < time_until <= BACKOFF_SCHEDULE[0] + 1


class TestTelemetry:
    """Tests for telemetry logging."""

    def test_webhook_telemetry_logged(
        self,
        webhook_client: WebhookClient,
        temp_telemetry_path: Path,
    ):
        """Test that webhook deliveries are logged to telemetry."""
        payload = create_success_payload(
            mission_uuid=uuid4(),
            mission_id="TEST-001",
            evidence_id="EV-001",
            chunk_id="chunk-123",
            similarity=0.85,
        )

        with patch.object(
            httpx.AsyncClient,
            "post",
            new_callable=AsyncMock,
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.is_success = True
            mock_response.text = '{"status": "received"}'
            mock_post.return_value = mock_response

            asyncio.run(webhook_client.send_correction_notification(
                "https://deepsearch.example/webhook",
                payload,
            ))

        # Check telemetry file
        assert temp_telemetry_path.exists()
        with open(temp_telemetry_path) as f:
            record = json.loads(f.readline())
            assert record["event"] == "webhook_success"
            assert record["success"] is True

    def test_correction_queue_telemetry(
        self,
        correction_queue: CorrectionQueueService,
        sample_auto_link_result: EvidenceAutoLinkingResult,
        temp_telemetry_path: Path,
    ):
        """Test that correction events are logged to telemetry."""
        correction_queue.queue_failed_items(
            mission_uuid=uuid4(),
            mission_id="TEST-001",
            project_id=uuid4(),
            result=sample_auto_link_result,
        )

        # Check telemetry file
        assert temp_telemetry_path.exists()
        with open(temp_telemetry_path) as f:
            lines = f.readlines()
            assert len(lines) == 2  # 2 items queued
            for line in lines:
                record = json.loads(line)
                assert record["event"] == "correction_queued"
                assert "error_type" in record

    def test_telemetry_summary_format(
        self,
        correction_queue: CorrectionQueueService,
        sample_auto_link_result: EvidenceAutoLinkingResult,
    ):
        """Test Grafana-ready telemetry summary format."""
        correction_queue.queue_failed_items(
            mission_uuid=uuid4(),
            mission_id="TEST-001",
            project_id=uuid4(),
            result=sample_auto_link_result,
        )

        summary = correction_queue.get_telemetry_summary()

        assert "ts" in summary
        assert summary["event"] == "correction_summary"
        assert "pending" in summary
        assert "completed" in summary
        assert "failed" in summary
        assert "success_rate" in summary
        assert "webhook_stats" in summary


class TestEvidenceAutoLinkingWithErrors:
    """Tests for evidence auto-linking error taxonomy and classification."""

    def test_error_taxonomy_has_required_types(self):
        """Verify error taxonomy has all required types per mission spec (5+ types)."""
        required = {
            AutoLinkErrorType.NO_EMBEDDING,
            AutoLinkErrorType.LOW_SIMILARITY,
            AutoLinkErrorType.NO_CHUNKS,
            AutoLinkErrorType.TIMEOUT,
            AutoLinkErrorType.VALIDATION_ERROR,
            AutoLinkErrorType.EMPTY_CONTENT,
            AutoLinkErrorType.DATABASE_ERROR,
        }
        actual = set(AutoLinkErrorType)
        assert actual == required, f"Missing types: {required - actual}"
        assert len(actual) >= 5, "Must have at least 5 error types per spec"

    def test_error_result_structure(self, sample_auto_link_result: EvidenceAutoLinkingResult):
        """Verify error results include all required fields."""
        # Our sample result should have errors with proper structure
        assert sample_auto_link_result.failed == 2
        assert len(sample_auto_link_result.errors) == 2

        for error in sample_auto_link_result.errors:
            assert "evidence_id" in error
            assert "error_type" in error
            assert "message" in error

    def test_failure_rate_calculation(self, sample_auto_link_result: EvidenceAutoLinkingResult):
        """Verify failure rate is calculated correctly."""
        # 2 failed out of 3 attempted
        expected_failure_rate = round(2 / 3, 3)
        assert sample_auto_link_result.failure_rate == expected_failure_rate

    def test_error_types_in_sample(self, sample_auto_link_result: EvidenceAutoLinkingResult):
        """Verify sample contains expected error types."""
        error_types = [e["error_type"] for e in sample_auto_link_result.errors]
        assert AutoLinkErrorType.LOW_SIMILARITY.value in error_types
        assert AutoLinkErrorType.NO_CHUNKS.value in error_types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
