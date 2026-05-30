"""API tests for DeepSearch ingestion endpoint."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.mission import Mission
from app.schemas.deepsearch import DeepSearchIngestRequest
from app.services.evidence_auto_linking import EvidenceAutoLinkingService


@pytest.fixture
def client(auth_headers):
    with TestClient(app) as test_client:
        yield test_client


def _mission_request() -> dict:
    base_payload = {
        "mission_id": "DSR.10.2",
        "title": "Passwordless Auth Research",
        "status": "complete",
        "research_statement": {
            "topic": "Passwordless authentication",
            "objective": "Document proven approaches",
            "scope": "Consumer SaaS",
        },
        "key_questions": [
            {
                "question": "What patterns dominate?",
                "status": "answered",
                "answer": "Magic links are ubiquitous.",
            }
        ],
        "synthesis": {
            "key_insights": ["Magic links dominate due to ease of use."],
            "surprising_findings": [],
            "contradictory_information": [],
            "contradiction_resolutions": [],
            "recommendations": ["Prototype passwordless onboarding."],
            "next_steps": ["Ship the revised flow."],
        },
        "evidence": [
            {
                "evidence_id": "EV-1",
                "source": "DeepSearch",
                "summary": "Magic links dominate consumer onboarding.",
                "chunk_id": None,
            }
        ],
        "quality_checkpoints": [
            {"gate": "research_statement", "status": "pass"},
            {"gate": "evidence_links", "status": "pass"},
            {"gate": "synthesis_quality", "status": "pass"},
            {"gate": "traceability", "status": "pass"},
            {"gate": "contradictions_resolved", "status": "pass"},
        ],
    }
    return base_payload


def _seed_documents(db_session, project_id):
    document = Document(
        project_id=project_id,
        name="DeepSearch Output",
        file_type="report",
        content="Magic links dominate.",
    )
    db_session.add(document)
    db_session.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="Magic links dominate consumer onboarding for SaaS.",
        content_tsv="Magic links dominate consumer onboarding for SaaS.",
    )
    db_session.add(chunk)
    db_session.commit()
    return chunk


def test_ingest_endpoint_persists_mission_and_auto_links(
    client: TestClient,
    db_session,
    project,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    """Successful ingestion should store the mission, pass gates, and capture auto-link metadata."""

    chunk = _seed_documents(db_session, project.id)
    from app.api.v1 import deepsearch as deepsearch_module

    telemetry_path = tmp_path / "ingest.jsonl"
    monkeypatch.setattr(
        deepsearch_module,
        "_auto_linker",
        EvidenceAutoLinkingService(telemetry_path=telemetry_path),
    )

    payload = {
        "project_id": str(project.id),
        "mission": _mission_request(),
    }
    response = client.post(
        "/api/v1/deepsearch/ingest", json=payload, headers=auth_headers
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mission_uuid"]
    assert body["quality_gates_passed"] is True
    assert body["auto_linking"]["linked"] == 1
    mission_record = db_session.query(Mission).one()
    exec_meta = mission_record.execution_metadata or {}
    assert exec_meta.get("evidence_linking", {}).get("linked") == 1
    assert mission_record.context["evidence"][0]["chunk_id"] == str(chunk.id)


def test_ingest_endpoint_returns_quality_gate_failure(
    db_session,
    project,
    tmp_path,
    monkeypatch,
):
    """Missing chunk links should trigger a structured quality gate failure."""

    from app.api.v1 import deepsearch as deepsearch_module

    telemetry_path = tmp_path / "failure.jsonl"
    monkeypatch.setattr(
        deepsearch_module,
        "_auto_linker",
        EvidenceAutoLinkingService(telemetry_path=telemetry_path),
    )

    request = DeepSearchIngestRequest(
        project_id=project.id,
        mission=_mission_request(),
    )
    response = deepsearch_module.ingest_deepsearch_payload(request, db=db_session)

    assert hasattr(response, "status_code") and response.status_code == 400
    body = json.loads(response.body.decode("utf-8"))
    assert body["error"]["code"] == "QUALITY_GATE_FAILURE"
    assert "evidence_links" in body["error"]["details"]["failing_gates"]


def test_resolve_project_auto_create_assigns_default_workspace(db_session):
    """T44.4: the DeepSearch auto-create path also assigns the default Space, so
    DeepSearch-created projects are not left space-less. _resolve_project only
    reads project_id/auto_create_project/project_name, so a lightweight stand-in
    avoids building a full MissionProtocolComplete payload."""
    from types import SimpleNamespace

    from app.api.v1 import deepsearch as deepsearch_module
    from app.models.workspace import DEFAULT_WORKSPACE_ID, Workspace

    # Seed the Default Workspace (FK target; the create_all'd test DB starts empty).
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Default Workspace"))
    db_session.commit()

    payload = SimpleNamespace(
        project_id=None, auto_create_project=True, project_name="DS Auto Project"
    )
    project = deepsearch_module._resolve_project(db_session, payload)

    assert str(project.workspace_id) == DEFAULT_WORKSPACE_ID, (
        "DeepSearch auto-created project must get the default Space, not NULL"
    )
