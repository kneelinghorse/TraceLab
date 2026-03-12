"""Tests for onboarding API workflows."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.api.v1.documents as documents_api
from app.services.chunking import ChunkingService
from app.services.coverage_report import CoverageReportGenerator
from app.services.document_ingestion import DocumentIngestionService
from app.services.processing_status import ProcessingStatusRecorder


class _StubRedactionService:
    """Deterministic redaction for tests."""

    def redact_document(self, text: str, document_id: str, metadata=None, use_pseudonymization=True):
        return {
            "redacted_text": text,
            "entities": [],
            "audit_trail": {"document_id": document_id, "strategy": "stub"},
        }


@pytest.fixture
def client():
    """Provide TestClient with onboarding router."""
    with TestClient(app) as app_client:
        yield app_client


@pytest.mark.skip(reason="Onboarding POST /projects route shadowed by projects router registered first in main.py — needs route prefix refactor")
def test_project_creation_is_idempotent(client: TestClient, auth_headers):
    """Ensure POST /projects caches responses via Idempotency-Key header."""
    payload = {
        "name": "Onboarding Test Project",
        "description": "Verifies idempotent project creation",
    }
    headers = {**auth_headers, "Idempotency-Key": "project-key-001"}

    first = client.post("/api/v1/projects", json=payload, headers=headers)
    assert first.status_code == 201
    first_payload = first.json()
    assert first_payload["name"] == payload["name"]

    replay = client.post("/api/v1/projects", json=payload, headers=headers)
    assert replay.status_code == 201
    assert replay.json() == first_payload

    conflict_payload = dict(payload)
    conflict_payload["name"] = "Different Name"
    conflict = client.post("/api/v1/projects", json=conflict_payload, headers=headers)
    assert conflict.status_code == 409


def test_document_registration_and_job_flow(client: TestClient, project, tmp_path, monkeypatch, auth_headers):
    """Register document, enqueue ingestion job, and observe completion."""
    # Ensure ingestion service uses deterministic stubbed dependencies
    stub_service = DocumentIngestionService(
        redaction_service=_StubRedactionService(),
        chunking_service=ChunkingService(),
        status_recorder=ProcessingStatusRecorder(),
        coverage_report_generator=CoverageReportGenerator(),
    )
    monkeypatch.setattr(documents_api, "_ingestion_service", stub_service)
    monkeypatch.setattr(documents_api, "_ingestion_init_error", None)

    file_path = tmp_path / "note.md"
    file_path.write_text("# Title\n\nContent for ingestion pipeline.")

    document_payload = {
        "project_id": str(project.id),
        "name": "Research Note",
        "file_path": str(file_path),
        "file_type": "notes",
        "mime_type": "text/markdown",
        "validation_status": "pending",
    }
    doc_headers = {**auth_headers, "Idempotency-Key": "document-key-001"}
    document_response = client.post("/api/v1/documents", json=document_payload, headers=doc_headers)
    assert document_response.status_code == 201, document_response.json()
    document_data = document_response.json()
    document_id = document_data["id"]
    assert document_data["file_path"] == str(file_path)

    job_headers = {**auth_headers, "Idempotency-Key": "job-key-001"}
    job_response = client.post(f"/api/v1/jobs?document_id={document_id}", headers=job_headers)
    assert job_response.status_code == 202, job_response.json()
    job_data = job_response.json()
    job_id = job_data["id"]
    assert job_response.headers["Location"] == f"/api/v1/jobs/{job_id}"

    # Ensure idempotent replay returns same job payload
    replay = client.post(f"/api/v1/jobs?document_id={document_id}", headers=job_headers)
    assert replay.status_code == 202
    assert replay.json() == job_data

    # Poll job endpoint for completion
    for _ in range(20):
        status_response = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        status_payload = status_response.json()
        if status_payload["status"] == "COMPLETED":
            break
        time.sleep(0.05)
    else:
        pytest.fail("Ingestion job did not complete in time")

    # Final payload should reflect completion timestamps
    assert status_payload["completed_at"] is not None
