"""Tests for the outbound HMAC signer (T40.4)."""
from __future__ import annotations

import hashlib
import hmac

import pytest

from app.services.deepsearch_hmac_signer import (
    HmacSigningError,
    sign_payload,
    verify_signature,
)

SECRET = "test-secret-" + "a" * 48  # 64-char for realism


class TestSignPayload:
    def test_signs_with_timestamp_by_default(self):
        signed = sign_payload(b'{"hello":"world"}', secret=SECRET)
        assert signed.body == b'{"hello":"world"}'
        assert "X-TraceLab-Signature" in signed.headers
        assert signed.headers["X-TraceLab-Signature"].startswith("sha256=")
        assert "X-TraceLab-Timestamp" in signed.headers

    def test_signs_without_timestamp_when_disabled(self):
        signed = sign_payload(
            b'{"hello":"world"}',
            include_timestamp=False,
            secret=SECRET,
        )
        assert "X-TraceLab-Timestamp" not in signed.headers
        assert "X-TraceLab-Signature" in signed.headers

    def test_signature_matches_manual_hmac_no_timestamp(self):
        body = b'{"x":1}'
        signed = sign_payload(body, include_timestamp=False, secret=SECRET)
        expected = hmac.new(
            SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        assert signed.headers["X-TraceLab-Signature"] == f"sha256={expected}"

    def test_signature_matches_manual_hmac_with_timestamp(self):
        body = b'{"x":1}'
        signed = sign_payload(body, include_timestamp=True, secret=SECRET)
        timestamp = signed.headers["X-TraceLab-Timestamp"]
        expected = hmac.new(
            SECRET.encode("utf-8"),
            f"{timestamp}.{body.decode('utf-8')}".encode(),
            hashlib.sha256,
        ).hexdigest()
        assert signed.headers["X-TraceLab-Signature"] == f"sha256={expected}"

    def test_missing_secret_raises(self, monkeypatch):
        """No explicit secret + no env config = hard error (prod safety)."""
        from app.core import config as config_module

        monkeypatch.setattr(
            config_module.settings,
            "deepsearch_tracelab_service_secret",
            None,
            raising=False,
        )
        monkeypatch.setattr(
            config_module.settings,
            "deepsearch_webhook_secret",
            None,
            raising=False,
        )
        with pytest.raises(
            HmacSigningError,
            match="DEEPSEARCH_TRACELAB_SERVICE_SECRET",
        ):
            sign_payload(b'{"x":1}')

    def test_settings_bind_only_the_tracelab_receiver_env_name(self, monkeypatch):
        """The inverse DeepSearch signer name must not fake receiver readiness."""
        from app.core.config import Settings

        for name in (
            "DEEPSEARCH_TRACELAB_SERVICE_SECRET",
            "TRACELAB_DEEPSEARCH_SERVICE_SECRET",
            "DEEPSEARCH_WEBHOOK_SECRET",
        ):
            monkeypatch.delenv(name, raising=False)

        receiver_value = "configured-receiver-secret"
        monkeypatch.setenv(
            "DEEPSEARCH_TRACELAB_SERVICE_SECRET",
            receiver_value,
        )
        receiver_settings = Settings(_env_file=None, environment="test")
        assert receiver_settings.effective_deepsearch_service_secret == receiver_value

        monkeypatch.delenv("DEEPSEARCH_TRACELAB_SERVICE_SECRET")
        monkeypatch.setenv(
            "TRACELAB_DEEPSEARCH_SERVICE_SECRET",
            "sender-only-secret",
        )
        sender_only_settings = Settings(_env_file=None, environment="test")
        assert sender_only_settings.effective_deepsearch_service_secret is None

    def test_falls_back_to_legacy_env(self, monkeypatch):
        """Transitional: deepsearch_webhook_secret still works when new isn't set."""
        from app.core import config as config_module

        monkeypatch.setattr(
            config_module.settings,
            "deepsearch_tracelab_service_secret",
            None,
            raising=False,
        )
        monkeypatch.setattr(
            config_module.settings,
            "deepsearch_webhook_secret",
            "legacy-secret",
            raising=False,
        )
        signed = sign_payload(b'{"x":1}', include_timestamp=False)
        expected = hmac.new(
            b"legacy-secret",
            b'{"x":1}',
            hashlib.sha256,
        ).hexdigest()
        assert signed.headers["X-TraceLab-Signature"] == f"sha256={expected}"

    def test_new_secret_takes_precedence_over_legacy(self, monkeypatch):
        from app.core import config as config_module

        monkeypatch.setattr(
            config_module.settings,
            "deepsearch_tracelab_service_secret",
            "new-secret",
            raising=False,
        )
        monkeypatch.setattr(
            config_module.settings,
            "deepsearch_webhook_secret",
            "legacy-secret",
            raising=False,
        )
        signed = sign_payload(b'{"x":1}', include_timestamp=False)
        expected = hmac.new(
            b"new-secret",
            b'{"x":1}',
            hashlib.sha256,
        ).hexdigest()
        assert signed.headers["X-TraceLab-Signature"] == f"sha256={expected}"


class TestVerifySignature:
    def test_round_trip_with_timestamp(self):
        signed = sign_payload(b'{"ok":true}', secret=SECRET)
        assert verify_signature(
            signed.body,
            signed.headers["X-TraceLab-Signature"],
            signed.headers["X-TraceLab-Timestamp"],
            secret=SECRET,
        )

    def test_round_trip_without_timestamp(self):
        signed = sign_payload(b'{"ok":true}', include_timestamp=False, secret=SECRET)
        assert verify_signature(
            signed.body,
            signed.headers["X-TraceLab-Signature"],
            None,
            secret=SECRET,
        )

    def test_wrong_secret_fails_verification(self):
        signed = sign_payload(b'{"ok":true}', secret=SECRET)
        assert not verify_signature(
            signed.body,
            signed.headers["X-TraceLab-Signature"],
            signed.headers["X-TraceLab-Timestamp"],
            secret=SECRET[::-1],
        )

    def test_mutated_body_fails_verification(self):
        signed = sign_payload(b'{"ok":true}', secret=SECRET)
        assert not verify_signature(
            b'{"ok":false}',
            signed.headers["X-TraceLab-Signature"],
            signed.headers["X-TraceLab-Timestamp"],
            secret=SECRET,
        )

    def test_missing_header_raises(self):
        with pytest.raises(HmacSigningError):
            verify_signature(b'{"x":1}', None, None, secret=SECRET)

    def test_wrong_prefix_raises(self):
        with pytest.raises(HmacSigningError):
            verify_signature(b'{"x":1}', "md5=abc", None, secret=SECRET)
