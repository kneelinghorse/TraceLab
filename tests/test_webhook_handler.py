"""Tests for webhook handler (B16.6).

Comprehensive tests covering:
- Webhook schema validation
- Signature verification
- Mission updates on success/failure/cancellation
- Idempotent processing
- Error handling

Note: Some tests require a running PostgreSQL database due to PostgreSQL-specific
columns in the schema (content_tsv in document_chunks). Run with:
    DATABASE_URL=postgresql://... pytest tests/test_webhook_handler.py -v
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.schemas.webhook import (
    DeepSearchWebhookPayload,
    DeepSearchWebhookStatus,
    ExecutionMetadata,
)
from app.services.webhook_handler import (
    WebhookHandler,
    WebhookProcessingError,
    WebhookValidationError,
)


# Lazy import of Mission model to allow schema tests to run without DB
def _get_mission_model():
    from app.models.mission import Mission

    return Mission


def _get_app():
    from app.main import app

    return app


def _create_test_mission(
    db_session,
    mission_id: str = "WH-001",
    title: str = "Webhook Test Mission",
    status: str = "in_progress",
    deepsearch_job_id: str = None,
):
    """Create a test mission for webhook testing."""
    Mission = _get_mission_model()
    mission = Mission(
        mission_id=mission_id,
        title=title,
        objective="Test objective for webhook testing",
        success_criteria=["Criterion 1", "Criterion 2"],
        status=status,
        deepsearch_job_id=deepsearch_job_id,
        context={"key": "value"},
    )
    db_session.add(mission)
    db_session.commit()
    db_session.refresh(mission)
    return mission


def _create_webhook_signature(payload: dict, secret: str, timestamp: str = None) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    payload_str = json.dumps(payload, separators=(",", ":"))
    message = f"{timestamp}.{payload_str}" if timestamp else payload_str
    signature = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={signature}"


def _colliding_execution_metadata(private_id: str, *, loops: int) -> ExecutionMetadata:
    """Build valid worker metadata that collides with TraceLab's reserved state."""
    return ExecutionMetadata(
        loops_executed=loops,
        worker_metric="merged",
        result_materialization={
            "status": "worker-private-status",
            "attempt_count": 99,
            "attempted_at": private_id,
            "errors": [f"private provider detail for {private_id}"],
            "document_id": private_id,
        },
    )


class TestWebhookSchemas:
    """Tests for webhook Pydantic schemas."""

    def test_execution_metadata_minimal(self):
        """Test ExecutionMetadata with minimal fields."""
        data = ExecutionMetadata()
        assert data.loops_executed is None
        assert data.sources_found is None

    def test_execution_metadata_full(self):
        """Test ExecutionMetadata with all fields."""
        data = ExecutionMetadata(
            loops_executed=3,
            sources_found=12,
            duration_seconds=187.5,
            model_used="gemini-1.5-flash",
            pedr_checked=True,
            pedr_reused=False,
        )
        assert data.loops_executed == 3
        assert data.sources_found == 12
        assert data.duration_seconds == 187.5
        assert data.model_used == "gemini-1.5-flash"
        assert data.pedr_checked is True
        assert data.pedr_reused is False

    def test_execution_metadata_extra_fields(self):
        """Test ExecutionMetadata accepts extra fields."""
        data = ExecutionMetadata(
            loops_executed=3,
            custom_field="custom_value",
        )
        assert data.loops_executed == 3
        assert data.custom_field == "custom_value"

    def test_webhook_payload_complete(self):
        """Test DeepSearchWebhookPayload with complete status."""
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-abc123",
            mission_id="B16.1",
            status=DeepSearchWebhookStatus.COMPLETE,
            execution_metadata=ExecutionMetadata(loops_executed=3),
            result_markdown="# Results\nSome results",
            result_protocol={"summary": "Done"},
        )
        assert payload.job_id == "ds-job-abc123"
        assert payload.mission_id == "B16.1"
        assert payload.status == DeepSearchWebhookStatus.COMPLETE
        assert payload.execution_metadata.loops_executed == 3
        assert payload.result_markdown is not None
        assert payload.error is None

    def test_webhook_payload_failed(self):
        """Test DeepSearchWebhookPayload with failed status."""
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-xyz789",
            mission_id="B16.2",
            status=DeepSearchWebhookStatus.FAILED,
            error="Rate limit exceeded",
        )
        assert payload.status == DeepSearchWebhookStatus.FAILED
        assert payload.error == "Rate limit exceeded"
        assert payload.result_markdown is None

    def test_webhook_payload_cancelled(self):
        """Test DeepSearchWebhookPayload with cancelled status."""
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-cancel",
            mission_id="B16.3",
            status=DeepSearchWebhookStatus.CANCELLED,
            error="User cancelled",
        )
        assert payload.status == DeepSearchWebhookStatus.CANCELLED


class TestWebhookSignatureValidation:
    """Tests for webhook signature validation."""

    def test_validate_signature_no_secret_configured_in_development(self):
        """Unsigned callbacks remain available only for local development."""
        handler = WebhookHandler()
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = None
            mock_settings.environment = "development"
            mock_settings.debug = True
            result = handler.validate_signature(b'{"test": "data"}', None)
            assert result is True

    @pytest.mark.parametrize("environment", ["production", "prod", "staging"])
    def test_validate_signature_no_secret_configured_outside_local_debug(
        self, environment
    ):
        """Every deployed environment fails closed on an unsigned receipt."""
        handler = WebhookHandler()
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = None
            mock_settings.environment = environment
            mock_settings.debug = True
            with pytest.raises(
                WebhookValidationError, match="service secret is not configured"
            ):
                handler.validate_signature(b'{"test": "data"}', None)

    def test_default_development_without_debug_fails_closed(self):
        """A missing deployment ENVIRONMENT cannot enable unsigned receipts."""
        handler = WebhookHandler()
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = None
            mock_settings.environment = "development"
            mock_settings.debug = False
            with pytest.raises(
                WebhookValidationError, match="service secret is not configured"
            ):
                handler.validate_signature(b'{"test": "data"}', None)

    def test_validate_signature_missing_header(self):
        """Validation fails when signature header is missing."""
        handler = WebhookHandler()
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = "test-secret"  # noqa: S105
            with pytest.raises(
                WebhookValidationError, match="Missing X-DeepSearch-Signature"
            ):
                handler.validate_signature(b'{"test": "data"}', None)

    def test_validate_signature_invalid_format(self):
        """Validation fails with invalid signature format."""
        handler = WebhookHandler()
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = "test-secret"  # noqa: S105
            with pytest.raises(
                WebhookValidationError, match="Invalid signature format"
            ):
                handler.validate_signature(b'{"test": "data"}', "md5=abc123")

    def test_validate_signature_invalid_signature(self):
        """Validation fails with incorrect signature."""
        handler = WebhookHandler()
        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = "test-secret"  # noqa: S105
            with pytest.raises(
                WebhookValidationError, match="Invalid webhook signature"
            ):
                handler.validate_signature(b'{"test": "data"}', "sha256=wrongsignature")

    def test_validate_signature_valid(self):
        """Validation passes with correct signature."""
        handler = WebhookHandler()
        secret = "test-secret"  # noqa: S105
        payload = b'{"test": "data"}'
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = secret
            result = handler.validate_signature(payload, f"sha256={expected_sig}")
            assert result is True

    def test_validate_signature_with_timestamp(self):
        """Validation passes with timestamp included in signature."""
        handler = WebhookHandler()
        secret = "test-secret"  # noqa: S105
        payload = b'{"test": "data"}'
        timestamp = "1234567890"
        message = f"{timestamp}.{payload.decode('utf-8')}"
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = secret
            result = handler.validate_signature(
                payload, f"sha256={expected_sig}", timestamp=timestamp
            )
            assert result is True


class TestWebhookProcessing:
    """Tests for webhook processing logic."""

    def test_process_complete_webhook(self, db_session):
        """Success merges worker metrics without accepting reserved-state collisions."""
        mission = _create_test_mission(
            db_session, mission_id="COMPLETE-001", status="in_progress"
        )
        canonical_state = {
            "status": "pending",
            "attempt_count": 1,
            "attempted_at": "2026-01-01T00:00:00+00:00",
            "error_categories": [],
        }
        mission.execution_metadata = {
            "existing_metric": "preserved",
            "result_materialization": canonical_state,
        }
        db_session.commit()
        private_id = str(uuid4())

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-complete",
            mission_id="COMPLETE-001",
            status=DeepSearchWebhookStatus.COMPLETE,
            execution_metadata=_colliding_execution_metadata(private_id, loops=3),
            result_markdown="# Research Results\n\nFindings here.",
            result_protocol={"summary": "Completed successfully"},
        )

        updated_mission, status_msg = handler.process_deepsearch_webhook(
            db_session, payload
        )

        assert updated_mission.status == "completed"
        assert updated_mission.deepsearch_job_id == "ds-job-complete"
        assert updated_mission.result_markdown == "# Research Results\n\nFindings here."
        assert updated_mission.result_protocol == {"summary": "Completed successfully"}
        assert updated_mission.execution_metadata["loops_executed"] == 3
        assert updated_mission.execution_metadata["worker_metric"] == "merged"
        assert updated_mission.execution_metadata["existing_metric"] == "preserved"
        assert updated_mission.execution_metadata["result_materialization"] == (
            canonical_state
        )
        assert private_id not in json.dumps(updated_mission.execution_metadata)
        assert updated_mission.completed_at is not None
        assert updated_mission.error_message is None
        assert status_msg == "completed"

    def test_complete_webhook_collision_stays_canonical_when_materializer_raises(
        self,
        db_session,
    ):
        """A failed materializer cannot leave worker-private reserved metadata behind."""
        mission = _create_test_mission(
            db_session,
            mission_id="COMPLETE-COLLISION-ERROR",
            status="in_progress",
        )
        canonical_state = {
            "status": "pending",
            "attempt_count": 2,
            "attempted_at": "2026-01-02T00:00:00+00:00",
            "error_categories": [],
        }
        mission.execution_metadata = {
            "existing_metric": "preserved",
            "result_materialization": canonical_state,
        }
        db_session.commit()
        private_id = str(uuid4())
        materializer = MagicMock()
        materializer.materialize.side_effect = RuntimeError(
            f"private materializer failure for {private_id}"
        )
        handler = WebhookHandler()
        handler._materialization_service = materializer
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-complete-collision-error",
            mission_id=mission.mission_id,
            status=DeepSearchWebhookStatus.COMPLETE,
            execution_metadata=_colliding_execution_metadata(private_id, loops=4),
            result_markdown="# Persisted before materialization failed",
        )

        with pytest.raises(
            WebhookProcessingError,
            match=r"unexpected_materialization_error$",
        ) as exc_info:
            handler.process_deepsearch_webhook(db_session, payload)

        db_session.refresh(mission)
        assert mission.status == "completed"
        assert mission.execution_metadata["loops_executed"] == 4
        assert mission.execution_metadata["worker_metric"] == "merged"
        assert mission.execution_metadata["existing_metric"] == "preserved"
        assert mission.execution_metadata["result_materialization"] == canonical_state
        assert private_id not in json.dumps(mission.execution_metadata)
        assert private_id not in str(exc_info.value)
        materializer.materialize.assert_called_once()

    def test_process_failed_webhook(self, db_session):
        """Failure merges metrics without overwriting canonical reserved state."""
        mission = _create_test_mission(
            db_session, mission_id="FAILED-001", status="in_progress"
        )
        canonical_state = {
            "status": "pending",
            "attempt_count": 1,
            "attempted_at": "2026-01-01T00:00:00+00:00",
            "error_categories": [],
        }
        mission.execution_metadata = {
            "existing_metric": "preserved",
            "result_materialization": canonical_state,
        }
        db_session.commit()
        private_id = str(uuid4())

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-failed",
            mission_id="FAILED-001",
            status=DeepSearchWebhookStatus.FAILED,
            execution_metadata=_colliding_execution_metadata(private_id, loops=1),
            error="API rate limit exceeded",
        )

        updated_mission, status_msg = handler.process_deepsearch_webhook(
            db_session, payload
        )

        assert updated_mission.status == "blocked"
        assert updated_mission.deepsearch_job_id == "ds-job-failed"
        assert updated_mission.error_message == "API rate limit exceeded"
        assert updated_mission.execution_metadata["loops_executed"] == 1
        assert updated_mission.execution_metadata["worker_metric"] == "merged"
        assert updated_mission.execution_metadata["existing_metric"] == "preserved"
        assert updated_mission.execution_metadata["result_materialization"] == (
            canonical_state
        )
        assert private_id not in json.dumps(updated_mission.execution_metadata)
        assert status_msg == "failed"

    def test_process_cancelled_webhook(self, db_session):
        """Cancellation merges metrics without overwriting canonical reserved state."""
        mission = _create_test_mission(
            db_session, mission_id="CANCEL-001", status="in_progress"
        )
        canonical_state = {
            "status": "failed",
            "attempt_count": 2,
            "attempted_at": "2026-01-02T00:00:00+00:00",
            "error_categories": ["not_search_ready"],
        }
        mission.execution_metadata = {
            "existing_metric": "preserved",
            "result_materialization": canonical_state,
        }
        db_session.commit()
        private_id = str(uuid4())

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-cancelled",
            mission_id="CANCEL-001",
            status=DeepSearchWebhookStatus.CANCELLED,
            execution_metadata=_colliding_execution_metadata(private_id, loops=2),
            error="User requested cancellation",
        )

        updated_mission, status_msg = handler.process_deepsearch_webhook(
            db_session, payload
        )

        assert updated_mission.status == "cancelled"
        assert updated_mission.deepsearch_job_id == "ds-job-cancelled"
        assert "cancellation" in updated_mission.error_message.lower()
        assert updated_mission.execution_metadata["loops_executed"] == 2
        assert updated_mission.execution_metadata["worker_metric"] == "merged"
        assert updated_mission.execution_metadata["existing_metric"] == "preserved"
        assert updated_mission.execution_metadata["result_materialization"] == (
            canonical_state
        )
        assert private_id not in json.dumps(updated_mission.execution_metadata)
        assert status_msg == "cancelled"

    def test_process_webhook_mission_not_found(self, db_session):
        """Processing fails for unknown mission."""
        from app.services.mission_service import MissionNotFoundError

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-unknown",
            mission_id="UNKNOWN-999",
            status=DeepSearchWebhookStatus.COMPLETE,
        )

        with pytest.raises(MissionNotFoundError):
            handler.process_deepsearch_webhook(db_session, payload)

    def test_process_webhook_idempotent_same_job(self, db_session):
        """Webhook is idempotent - same job_id processed twice returns early."""
        _create_test_mission(
            db_session,
            mission_id="IDEMPOTENT-001",
            status="completed",
            deepsearch_job_id="ds-job-idempotent",
        )

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-idempotent",
            mission_id="IDEMPOTENT-001",
            status=DeepSearchWebhookStatus.COMPLETE,
            result_markdown="New content that should NOT be saved",
        )

        updated_mission, status_msg = handler.process_deepsearch_webhook(
            db_session, payload
        )

        assert status_msg == "already_processed"
        # Content should not be updated
        assert updated_mission.result_markdown is None

    def test_process_webhook_idempotent_cancelled_status(self, db_session):
        """Webhook is idempotent for cancelled missions."""
        _create_test_mission(
            db_session,
            mission_id="IDEMPOTENT-002",
            status="cancelled",
            deepsearch_job_id="ds-job-cancelled",
        )

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-cancelled",
            mission_id="IDEMPOTENT-002",
            status=DeepSearchWebhookStatus.COMPLETE,
        )

        updated_mission, status_msg = handler.process_deepsearch_webhook(
            db_session, payload
        )

        assert status_msg == "already_processed"
        assert updated_mission.status == "cancelled"

    def test_process_webhook_clears_previous_error(self, db_session):
        """Successful webhook clears previous error message."""
        mission = _create_test_mission(
            db_session, mission_id="CLEAR-ERROR-001", status="blocked"
        )
        mission.error_message = "Previous error"
        db_session.commit()

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-job-retry",
            mission_id="CLEAR-ERROR-001",
            status=DeepSearchWebhookStatus.COMPLETE,
            result_markdown="# Success",
        )

        updated_mission, status_msg = handler.process_deepsearch_webhook(
            db_session, payload
        )

        assert updated_mission.status == "completed"
        assert updated_mission.error_message is None


class TestWebhookAPIEndpoint:
    """Tests for POST /api/v1/webhooks/deepsearch endpoint."""

    def test_webhook_endpoint_success(self, db_session):
        """Webhook endpoint processes valid payload."""
        client = TestClient(_get_app())
        _create_test_mission(db_session, mission_id="API-001", status="in_progress")

        payload = {
            "job_id": "ds-api-job",
            "mission_id": "API-001",
            "status": "complete",
            "execution_metadata": {
                "loops_executed": 2,
                "sources_found": 8,
            },
            "result_markdown": "# Results",
            "result_protocol": {"done": True},
        }

        response = client.post("/api/v1/webhooks/deepsearch", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True
        assert data["mission_id"] == "API-001"
        assert data["status"] == "completed"

    def test_webhook_endpoint_mission_not_found(self, db_session):
        """Webhook endpoint returns 404 for unknown mission."""
        client = TestClient(_get_app())

        payload = {
            "job_id": "ds-unknown",
            "mission_id": "NONEXISTENT-999",
            "status": "complete",
        }

        response = client.post("/api/v1/webhooks/deepsearch", json=payload)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_webhook_endpoint_invalid_payload(self, db_session):
        """Webhook endpoint returns 422 for invalid payload."""
        client = TestClient(_get_app())

        payload = {
            "job_id": "ds-invalid",
            # Missing required field: mission_id
            "status": "complete",
        }

        response = client.post("/api/v1/webhooks/deepsearch", json=payload)

        assert response.status_code == 422

    def test_webhook_endpoint_invalid_status(self, db_session):
        """Webhook endpoint returns 422 for invalid status."""
        client = TestClient(_get_app())

        payload = {
            "job_id": "ds-bad-status",
            "mission_id": "API-001",
            "status": "not_a_valid_status",
        }

        response = client.post("/api/v1/webhooks/deepsearch", json=payload)

        assert response.status_code == 422

    def test_webhook_endpoint_signature_invalid(self, db_session):
        """Webhook endpoint returns 401 for invalid signature."""
        client = TestClient(_get_app())
        _create_test_mission(db_session, mission_id="SIG-001", status="in_progress")

        payload = {
            "job_id": "ds-sig-test",
            "mission_id": "SIG-001",
            "status": "complete",
        }

        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = "real-secret"  # noqa: S105

            response = client.post(
                "/api/v1/webhooks/deepsearch",
                json=payload,
                headers={"X-DeepSearch-Signature": "sha256=wrong"},
            )

            assert response.status_code == 401
            assert "signature" in response.json()["detail"].lower()

    def test_webhook_endpoint_signature_valid(self, db_session):
        """Webhook endpoint succeeds with valid signature."""
        client = TestClient(_get_app())
        _create_test_mission(db_session, mission_id="SIGOK-001", status="in_progress")

        payload = {
            "job_id": "ds-sig-valid",
            "mission_id": "SIGOK-001",
            "status": "complete",
            "result_markdown": "# Done",
        }

        # Compute signature (need to match exact JSON serialization)
        secret = "test-webhook-secret"  # noqa: S105
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

        with patch("app.services.webhook_handler.settings") as mock_settings:
            mock_settings.effective_deepsearch_service_secret = secret

            response = client.post(
                "/api/v1/webhooks/deepsearch",
                content=payload_bytes,
                headers={
                    "X-DeepSearch-Signature": f"sha256={signature}",
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 200
            assert response.json()["received"] is True

    def test_webhook_endpoint_no_auth_required(self, db_session):
        """Webhook endpoint does not require JWT authentication."""
        client = TestClient(_get_app())
        _create_test_mission(db_session, mission_id="NOAUTH-001", status="in_progress")

        payload = {
            "job_id": "ds-noauth",
            "mission_id": "NOAUTH-001",
            "status": "complete",
        }

        # No Authorization header - should still work
        response = client.post("/api/v1/webhooks/deepsearch", json=payload)

        assert response.status_code == 200


class TestWebhookFailedStatus:
    """Detailed tests for failed webhook handling."""

    def test_failed_without_error_message(self, db_session):
        """Failed webhook without error uses default message."""
        _create_test_mission(
            db_session, mission_id="FAIL-NO-MSG", status="in_progress"
        )

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-fail-no-msg",
            mission_id="FAIL-NO-MSG",
            status=DeepSearchWebhookStatus.FAILED,
            # No error field
        )

        updated_mission, _ = handler.process_deepsearch_webhook(db_session, payload)

        assert updated_mission.status == "blocked"
        assert "failed without error message" in updated_mission.error_message.lower()

    def test_failed_preserves_partial_results(self, db_session):
        """Failed webhook can still have partial execution_metadata."""
        _create_test_mission(
            db_session, mission_id="FAIL-PARTIAL", status="in_progress"
        )

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-fail-partial",
            mission_id="FAIL-PARTIAL",
            status=DeepSearchWebhookStatus.FAILED,
            execution_metadata=ExecutionMetadata(
                loops_executed=2,
                sources_found=5,
            ),
            error="Timeout after 2 loops",
        )

        updated_mission, _ = handler.process_deepsearch_webhook(db_session, payload)

        assert updated_mission.status == "blocked"
        assert updated_mission.execution_metadata["loops_executed"] == 2
        assert updated_mission.execution_metadata["sources_found"] == 5


class TestWebhookEdgeCases:
    """Edge case tests for webhook handling."""

    def test_empty_execution_metadata(self, db_session):
        """Webhook with no execution_metadata uses empty dict."""
        _create_test_mission(
            db_session, mission_id="EMPTY-META", status="in_progress"
        )

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-empty-meta",
            mission_id="EMPTY-META",
            status=DeepSearchWebhookStatus.COMPLETE,
            result_markdown="# Done",
        )

        updated_mission, _ = handler.process_deepsearch_webhook(db_session, payload)

        assert updated_mission.status == "completed"
        assert updated_mission.execution_metadata == {}

    def test_large_result_markdown(self, db_session):
        """Webhook with large markdown content is stored correctly."""
        _create_test_mission(
            db_session, mission_id="LARGE-MD", status="in_progress"
        )

        large_markdown = "# Results\n\n" + ("Lorem ipsum dolor sit amet. " * 1000)

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-large-md",
            mission_id="LARGE-MD",
            status=DeepSearchWebhookStatus.COMPLETE,
            result_markdown=large_markdown,
        )

        updated_mission, _ = handler.process_deepsearch_webhook(db_session, payload)

        assert updated_mission.status == "completed"
        assert len(updated_mission.result_markdown) > 10000

    def test_complex_result_protocol(self, db_session):
        """Webhook with complex nested result_protocol."""
        _create_test_mission(
            db_session, mission_id="COMPLEX-PROTO", status="in_progress"
        )

        complex_protocol = {
            "findings": [
                {"id": 1, "title": "Finding 1", "confidence": 0.95},
                {"id": 2, "title": "Finding 2", "confidence": 0.87},
            ],
            "sources": [
                {"url": "https://example.com", "relevance": 0.9},
            ],
            "metadata": {
                "version": "1.0",
                "nested": {"deeply": {"nested": "value"}},
            },
        }

        handler = WebhookHandler()
        payload = DeepSearchWebhookPayload(
            job_id="ds-complex",
            mission_id="COMPLEX-PROTO",
            status=DeepSearchWebhookStatus.COMPLETE,
            result_protocol=complex_protocol,
        )

        updated_mission, _ = handler.process_deepsearch_webhook(db_session, payload)

        assert updated_mission.result_protocol["findings"][0]["confidence"] == 0.95
        assert (
            updated_mission.result_protocol["metadata"]["nested"]["deeply"]["nested"]
            == "value"
        )
