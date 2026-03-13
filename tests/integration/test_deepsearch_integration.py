"""End-to-end DeepSearch integration tests covering ingestion + search."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project
from app.services.evidence_auto_linking import EvidenceAutoLinkingService
import app.services.rag_service as rag_service_module

from app.api.v1 import deepsearch as deepsearch_module, search as search_module

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "deepsearch_missions"


def _load_mission_payload(name: str) -> Dict[str, object]:
    path = FIXTURE_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _request_payload(
    project_id: UUID | str,
    fixture_name: str,
    **overrides: object,
) -> Dict[str, object]:
    payload: Dict[str, object] = {
        "project_id": str(project_id),
        "mission": _load_mission_payload(fixture_name),
    }
    payload.update(overrides)
    return payload


def _seed_chunks(
    db_session,
    *,
    project_id: UUID | str,
    contents: List[str],
) -> List[DocumentChunk]:
    """Persist document + chunk rows matching the supplied contents."""
    document = Document(
        project_id=project_id,
        name="DeepSearch fixture",
        file_type="report",
        content="\n".join(contents),
        processed=True,
        chunked=True,
    )
    db_session.add(document)
    db_session.flush()

    chunks: List[DocumentChunk] = []
    for index, text in enumerate(contents):
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=text,
            content_tsv=text,
        )
        db_session.add(chunk)
        chunks.append(chunk)
    db_session.commit()
    return chunks


@pytest.fixture
def client(auth_headers):
    with TestClient(app) as test_client:
        test_client.headers.update(auth_headers)
        yield test_client


@pytest.fixture(autouse=True)
def configure_auto_linker(monkeypatch, tmp_path):
    telemetry_path = tmp_path / "auto-linking.jsonl"
    service = EvidenceAutoLinkingService(telemetry_path=telemetry_path)
    monkeypatch.setattr(deepsearch_module, "_auto_linker", service)
    return telemetry_path


def test_ingest_customer_onboarding_links_all_evidence(
    client: TestClient,
    project: Project,
    db_session,
):
    payload = _request_payload(project.id, "customer_onboarding_playbook")
    evidence = payload["mission"]["evidence"]  # type: ignore[index]
    _seed_chunks(
        db_session,
        project_id=project.id,
        contents=[item["summary"] for item in evidence],
    )

    response = client.post("/api/v1/deepsearch/ingest", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["auto_linking"]["linked"] == len(evidence)

    mission_record = db_session.query(Mission).order_by(Mission.created_at.desc()).first()
    assert mission_record is not None
    chunk_ids = {ev["chunk_id"] for ev in mission_record.context["evidence"]}
    assert len(chunk_ids) == len(evidence)
    assert None not in chunk_ids


def test_ingest_security_payload_exposes_match_metadata(
    client: TestClient,
    project: Project,
    db_session,
):
    payload = _request_payload(project.id, "security_incident_coordination")
    evidence = payload["mission"]["evidence"]  # type: ignore[index]
    _seed_chunks(
        db_session,
        project_id=project.id,
        contents=[item["summary"] for item in evidence],
    )

    response = client.post("/api/v1/deepsearch/ingest", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    matches = body["auto_linking"]["matches"]
    assert len(matches) == len(evidence)
    assert all(match["summary_preview"] for match in matches)


def test_ingest_auto_creates_project_when_requested(
    client: TestClient,
    db_session,
):
    initial_count = db_session.query(Project).count()
    mission_payload = _load_mission_payload("operations_resilience_report")
    for index, evidence in enumerate(mission_payload["evidence"]):
        evidence["chunk_id"] = f"prelinked-chunk-{index}"
    payload = {
        "mission": mission_payload,
        "auto_create_project": True,
        "project_name": "DeepSearch Integration QA",
    }

    response = client.post("/api/v1/deepsearch/ingest", json=payload)

    assert response.status_code == 201, response.text
    assert db_session.query(Project).count() == initial_count + 1
    assert response.json()["project_id"] is not None


def test_ingest_requires_project_identifier_without_auto_create(
    client: TestClient,
):
    payload = {"mission": _load_mission_payload("ux_diary_analysis")}
    response = client.post("/api/v1/deepsearch/ingest", json=payload)
    assert response.status_code == 400
    assert "project_id is required" in response.json()["detail"]


def test_ingest_similarity_threshold_override_blocks_links(
    client: TestClient,
    project: Project,
    db_session,
):
    payload = _request_payload(
        project.id,
        "ai_infrastructure_benchmark",
        similarity_threshold=1.0,
    )
    evidence = payload["mission"]["evidence"]  # type: ignore[index]
    modified_contents = [
        f"{item['summary']} :: extracted signals" for item in evidence
    ]
    _seed_chunks(db_session, project_id=project.id, contents=modified_contents)

    response = client.post("/api/v1/deepsearch/ingest", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "QUALITY_GATE_FAILURE"
    assert body["error"]["details"]["auto_linking"]["linked"] == 0


def test_ingest_quality_gate_failure_returns_structured_error(
    client: TestClient,
    project: Project,
):
    payload = _request_payload(project.id, "market_signals_scan")

    response = client.post("/api/v1/deepsearch/ingest", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "QUALITY_GATE_FAILURE"
    assert "evidence_links" in body["error"]["details"]["failing_gates"]


def test_ingest_skips_prelinked_evidence_entries(
    client: TestClient,
    project: Project,
    db_session,
):
    payload = _request_payload(project.id, "operations_resilience_report")
    evidence = payload["mission"]["evidence"]  # type: ignore[index]
    chunks = _seed_chunks(
        db_session,
        project_id=project.id,
        contents=[item["summary"] for item in evidence],
    )
    evidence[0]["chunk_id"] = str(chunks[0].id)

    response = client.post("/api/v1/deepsearch/ingest", json=payload)

    assert response.status_code == 201, response.text
    summary = response.json()["auto_linking"]
    assert summary["skipped"] == 1
    assert summary["linked"] == len(evidence) - 1


def test_ingest_writes_auto_linking_telemetry(
    client: TestClient,
    project: Project,
    db_session,
    configure_auto_linker: Path,
):
    payload = _request_payload(project.id, "ux_diary_analysis")
    evidence = payload["mission"]["evidence"]  # type: ignore[index]
    _seed_chunks(
        db_session,
        project_id=project.id,
        contents=[item["summary"] for item in evidence],
    )

    response = client.post("/api/v1/deepsearch/ingest", json=payload)

    assert response.status_code == 201, response.text
    assert configure_auto_linker.exists()
    lines = configure_auto_linker.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event_type"] == "evidence.auto_linking.completed"
    assert entry["payload"]["mission_id"] == payload["mission"]["mission_id"]


def test_ingest_project_scoped_linking(
    client: TestClient,
    project: Project,
    db_session,
):
    payload = _request_payload(project.id, "customer_onboarding_playbook")
    evidence = payload["mission"]["evidence"]  # type: ignore[index]
    target_chunks = _seed_chunks(
        db_session,
        project_id=project.id,
        contents=[item["summary"] for item in evidence],
    )
    alt_project = Project(name="Other Project", description="Control")
    db_session.add(alt_project)
    db_session.commit()
    _seed_chunks(
        db_session,
        project_id=alt_project.id,
        contents=[item["summary"] for item in evidence],
    )

    response = client.post("/api/v1/deepsearch/ingest", json=payload)

    assert response.status_code == 201, response.text
    mission_record = db_session.query(Mission).order_by(Mission.created_at.desc()).first()
    chunk_ids = {item["chunk_id"] for item in mission_record.context["evidence"]}
    assert chunk_ids == {str(chunk.id) for chunk in target_chunks}


def test_ingested_mission_available_via_search_endpoint(
    client: TestClient,
    project: Project,
    db_session,
    monkeypatch,
):
    payload = _request_payload(project.id, "customer_onboarding_playbook")
    evidence = payload["mission"]["evidence"]  # type: ignore[index]
    chunks = _seed_chunks(
        db_session,
        project_id=project.id,
        contents=[item["summary"] for item in evidence],
    )
    response = client.post("/api/v1/deepsearch/ingest", json=payload)
    assert response.status_code == 201, response.text

    mission = db_session.query(Mission).order_by(Mission.created_at.desc()).first()
    chunk_id = mission.context["evidence"][0]["chunk_id"]
    selected_chunk = next(chunk for chunk in chunks if str(chunk.id) == chunk_id)

    class _FakeRagService:
        def __init__(self):
            self.calls: List[Dict[str, object]] = []

        def run_query(
            self,
            query: str,
            top_k: int = 5,
            project_id: Optional[str] = None,
            document_id: Optional[str] = None,
            source_type: Optional[str] = None,
            document_types: Optional[List[str]] = None,
            source_types: Optional[List[str]] = None,
            date_from: Optional[object] = None,
            date_to: Optional[object] = None,
            tags: Optional[List[str]] = None,
            hnsw_ef: Optional[int] = None,
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            search_mode: str = "semantic",
            min_quality_gates: Optional[int] = None,
            status_filters: Optional[List[str]] = None,
            allow_pii: Optional[bool] = True,
            governance_mode: Optional[str] = None,
            **kwargs,
        ) -> Dict[str, object]:
            self.calls.append(
                {
                    "query": query,
                    "project_id": project_id,
                    "top_k": top_k,
                    "search_mode": search_mode,
                }
            )
            return {
                "answer": "Activation playbook recommendations ready.",
                "citations": [
                    {
                        "document_id": str(selected_chunk.document_id),
                        "chunk_id": str(selected_chunk.id),
                        "chunk_index": selected_chunk.chunk_index,
                        "source_type": "report",
                        "score": 0.9,
                        "snippet": "Activation runs faster when tours and checklists align.",
                    }
                ],
                "sources": [
                    {
                        "chunk_id": str(selected_chunk.id),
                        "content": selected_chunk.content,
                        "document_id": str(selected_chunk.document_id),
                        "project_id": str(project.id),
                        "chunk_index": selected_chunk.chunk_index,
                        "source_type": "report",
                        "document_type": "analysis",
                        "collection_date": None,
                        "tags": ["onboarding"],
                        "score": 0.92,
                        "quality_score": 0.95,
                        "quality_base_score": 0.8,
                        "quality_boost": 0.15,
                        "quality_status": mission.status,
                        "quality_gates_passed": 5,
                        "quality_gates_total": 5,
                        "quality_validated": True,
                        "quality_mission_id": mission.mission_id,
                        "quality_pii_flagged": False,
                    }
                ],
                "latency_ms": 12.5,
                "compression": {
                    "original_chunks": 4,
                    "filtered_chunks": 1,
                    "original_tokens": 1200,
                    "filtered_tokens": 320,
                    "reduction_ratio": 0.73,
                    "threshold": 0.6,
                    "compression_ms": 2.2,
                },
                "cache": {"hit": False, "score": None, "age_seconds": None, "ttl_seconds": 30},
                "quality": {
                    "composite_score": 0.95,
                    "threshold": 0.8,
                    "pillar_scores": {
                        "linguistic_uncertainty": 0.05,
                        "answer_integrity": 0.03,
                        "source_provenance": 0.02,
                    },
                    "hard_failures": [],
                    "reasons": [],
                    "pre_escalation_score": 0.91,
                },
                "routing": {
                    "selected_model": "gpt-5.1",
                    "escalated": False,
                    "attempts": [
                        {
                            "model": "gpt-5.1",
                            "quality_score": 0.95,
                            "below_threshold": False,
                            "hard_failures": [],
                            "citation_count": 1,
                        }
                    ],
                    "estimated_cost_usd": 0.001,
                    "metrics": {"total_queries": 1, "escalations": 0},
                },
                "search_mode": "semantic",
            }

    class _FakeHistory:
        def __init__(self):
            self.records: List[Dict[str, object]] = []

        def record_search(self, **kwargs: object):
            self.records.append(kwargs)

    fake_rag = _FakeRagService()
    fake_history = _FakeHistory()
    monkeypatch.setattr(search_module, "get_rag_service", lambda: fake_rag)
    monkeypatch.setattr(rag_service_module, "get_rag_service", lambda: fake_rag)
    client.app.dependency_overrides[search_module.get_search_history_service] = lambda: fake_history

    search_payload = {
        "query": "activation checklist",
        "top_k": 3,
        "project_id": str(project.id),
        "search_mode": "semantic",
    }
    try:
        search_response = client.post("/api/v1/search", json=search_payload)
    finally:
        client.app.dependency_overrides.pop(search_module.get_search_history_service, None)

    assert search_response.status_code == 200, search_response.text
    body = search_response.json()
    assert body["sources"][0]["chunk_id"] == chunk_id
    assert fake_rag.calls[-1]["project_id"] == str(project.id)
    assert fake_history.records
