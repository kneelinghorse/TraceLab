"""Tests for the lightweight redaction service and API integration."""

from __future__ import annotations

import json
import os
import re

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./tests/test.db")

from app.api.v1 import redaction as redaction_module
from app.main import app
from app.services.presidio_redaction import (
    ParticipantIDRecognizer,
    PresidioRedactionService,
    ProjectIDRecognizer,
)


@pytest.fixture
def passthrough_redaction_service(tmp_path):
    """Provide a PresidioRedactionService instance with a custom deny list."""
    deny_file = tmp_path / "deny.json"
    deny_file.write_text(
        json.dumps(
            {
                "PARTICIPANT_ID": ["PID-CONTROL-9999"],
                "PROJECT_ID": ["PROJ-DEMO-0001"],
            }
        ),
        encoding="utf-8",
    )

    service = PresidioRedactionService(
        deny_list_path=str(deny_file),
    )

    return service


def test_custom_recognizers_cover_expected_patterns():
    """Participant and project recognizers should detect domain-specific identifiers."""
    participant_recognizer = ParticipantIDRecognizer()
    project_recognizer = ProjectIDRecognizer()
    text = (
        "Participants PID-2024-1234 and PARTICIPANT-UX99-4321 "
        "were enrolled under P-2024-0001 for project PROJ-ALPHA-9876."
    )

    participant_matches = {
        match.group(0)
        for pattern in participant_recognizer.patterns
        for match in re.finditer(pattern.regex, text)
    }
    project_matches = {
        match.group(0)
        for pattern in project_recognizer.patterns
        for match in re.finditer(pattern.regex, text)
    }

    assert {
        "PID-2024-1234",
        "PARTICIPANT-UX99-4321",
        "P-2024-0001",
    } <= participant_matches
    assert {"PROJ-ALPHA-9876"} <= project_matches or {
        "PROJECT-BETA-9999"
    } <= project_matches


def test_redact_document_uses_pseudonymization_and_audit(passthrough_redaction_service):
    """Ensure redaction output includes audit details and pseudo identifiers."""
    service = passthrough_redaction_service
    text = (
        "Participant PID-2024-1234 can be reached at john@example.com "
        "about project PROJ-ALPHA-1234 while control ID PID-CONTROL-9999 waits."
    )

    result = service.redact_document(
        text=text,
        document_id="doc-001",
        metadata={"doc_type": "transcript"},
        use_pseudonymization=True,
    )

    assert "PID-2024-1234" not in result["redacted_text"]
    assert "john@example.com" not in result["redacted_text"]
    assert result["redacted_text"].count("PARTICIPANT_ID-PSEUDO") >= 1
    assert result["audit_trail"]["document_id"] == "doc-001"
    assert result["audit_trail"]["metadata"]["doc_type"] == "transcript"
    deny_counts = result["audit_trail"]["deny_list_counts"]
    assert deny_counts["PARTICIPANT_ID"] == 1
    detected_entities = {entity["entity_type"] for entity in result["entities"]}
    assert {"PARTICIPANT_ID", "EMAIL_ADDRESS", "PROJECT_ID"} <= detected_entities


@pytest.mark.asyncio
async def test_redaction_endpoint(monkeypatch, auth_headers):
    """Validate API surface using the stubbed redaction service."""

    class _FakeRedactionService:
        def __init__(self):
            self.calls: list[dict] = []

        def redact_document(self, **payload):
            self.calls.append(payload)
            return {
                "redacted_text": "no entities",
                "entities": [],
                "audit_trail": {
                    "document_id": payload.get("document_id"),
                    "metadata": payload.get("metadata") or {},
                    "deny_list_counts": {},
                    "redaction_performed": False,
                },
            }

    service = _FakeRedactionService()

    monkeypatch.setattr(redaction_module, "_redaction_service", service)
    monkeypatch.setattr(redaction_module, "_service_init_error", None)
    monkeypatch.setattr(redaction_module, "get_redaction_service", lambda: service)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/redaction/redact",
            json={
                "text": "Nothing sensitive here.",
                "document_id": "doc-002",
                "metadata": {"doc_type": "brief"},
                "use_pseudonymization": True,
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["redacted_text"] == "no entities"
    assert payload["audit_trail"]["document_id"] == "doc-002"
    assert payload["audit_trail"]["metadata"]["doc_type"] == "brief"
    assert payload["entities"] == []
