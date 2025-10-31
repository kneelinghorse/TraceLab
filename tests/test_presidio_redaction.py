"""Tests for the Presidio redaction service and API integration."""
from __future__ import annotations

import json
import re
import os
from types import SimpleNamespace
from typing import List

import pytest

pytest.importorskip("presidio_analyzer")
pytest.importorskip("presidio_anonymizer")
pytest.importorskip("presidio_evaluator")

from httpx import AsyncClient, ASGITransport

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./tests/test.db")

from app.api.v1 import redaction as redaction_module
from app.main import app
from app.services.presidio_redaction import (
    ParticipantIDRecognizer,
    PresidioRedactionService,
    ProjectIDRecognizer,
)


class DummyRegistry:
    """Collects recognizers added during service initialization."""

    def __init__(self) -> None:
        self.registered: List[object] = []

    def add_recognizer(self, recognizer: object) -> None:
        self.registered.append(recognizer)


class DummyAnalyzer:
    """Stub AnalyzerEngine used to avoid heavyweight Presidio dependencies."""

    def __init__(self) -> None:
        self.registry = DummyRegistry()
        self._results: List[object] = []

    def set_results(self, results: List[object]) -> None:
        self._results = results

    def analyze(self, text: str, language: str = "en") -> List[object]:
        return list(self._results)


class DummyAnonymizer:
    """Stub AnonymizerEngine to capture operator configuration."""

    def __init__(self) -> None:
        self.last_call: dict | None = None
        self.output_text: str = "pseudonymized"

    def anonymize(self, text: str, analyzer_results: List[object], operators: dict) -> SimpleNamespace:
        self.last_call = {
            "text": text,
            "operators": operators,
            "results": list(analyzer_results),
        }
        return SimpleNamespace(text=self.output_text)


@pytest.fixture
def dummy_redaction_service(tmp_path):
    """Provide a PresidioRedactionService instance backed by stubs."""
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

    analyzer = DummyAnalyzer()
    anonymizer = DummyAnonymizer()
    service = PresidioRedactionService(
        analyzer_engine=analyzer,
        anonymizer_engine=anonymizer,
        deny_list_path=str(deny_file),
        ensure_spacy_model=False,
    )

    return service, analyzer, anonymizer


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

    assert {"PID-2024-1234", "PARTICIPANT-UX99-4321", "P-2024-0001"} <= participant_matches
    assert {"PROJ-ALPHA-9876"} <= project_matches


def test_redact_document_uses_pseudonymization_and_audit(dummy_redaction_service):
    """Ensure redaction output includes audit details and custom operators."""
    service, analyzer, anonymizer = dummy_redaction_service
    text = (
        "Participant PID-2024-1234 can be reached at john@example.com "
        "about project PROJ-ALPHA-1234."
    )

    spans = []
    for entity_type, value in [
        ("PARTICIPANT_ID", "PID-2024-1234"),
        ("EMAIL_ADDRESS", "john@example.com"),
        ("PROJECT_ID", "PROJ-ALPHA-1234"),
    ]:
        start = text.index(value)
        end = start + len(value)
        spans.append(SimpleNamespace(entity_type=entity_type, start=start, end=end, score=0.9))

    analyzer.set_results(spans)
    anonymizer.output_text = "pseudonymized output"

    recognizer_types = {type(rec).__name__ for rec in analyzer.registry.registered}
    assert {"ParticipantIDRecognizer", "ProjectIDRecognizer"} <= recognizer_types

    result = service.redact_document(
        text=text,
        document_id="doc-001",
        metadata={"doc_type": "transcript"},
        use_pseudonymization=True,
    )

    assert result["redacted_text"] == "pseudonymized output"
    assert result["audit_trail"]["document_id"] == "doc-001"
    assert result["audit_trail"]["metadata"]["doc_type"] == "transcript"
    assert result["audit_trail"]["deny_list_counts"]["PARTICIPANT_ID"] == 1
    assert {"PARTICIPANT_ID", "EMAIL_ADDRESS", "PROJECT_ID"} == {
        entity["entity_type"] for entity in result["entities"]
    }
    assert anonymizer.last_call and anonymizer.last_call["operators"]["PARTICIPANT_ID"].operator_name == "custom"
    assert anonymizer.last_call["operators"]["PROJECT_ID"].operator_name == "custom"


@pytest.mark.asyncio
async def test_redaction_endpoint(monkeypatch, dummy_redaction_service):
    """Validate API surface using the stubbed redaction service."""
    service, analyzer, anonymizer = dummy_redaction_service
    analyzer.set_results([])
    anonymizer.output_text = "no entities"

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
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["redacted_text"] == "no entities"
    assert payload["audit_trail"]["document_id"] == "doc-002"
    assert payload["audit_trail"]["metadata"]["doc_type"] == "brief"
    assert payload["entities"] == []
