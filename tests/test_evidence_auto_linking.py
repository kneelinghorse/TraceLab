"""Unit tests for the evidence auto-linking service."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.database import engine, SessionLocal
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.models.project import Project
from app.models.mission_protocol import MissionProtocolComplete
from app.services.evidence_auto_linking import (
    AutoLinkErrorType,
    EvidenceAutoLinkingService,
)

# ---------------------------------------------------------------
# SQLite-compatible table creation (avoids PostgreSQL-only DDL)
# ---------------------------------------------------------------

_CREATE_PROJECTS = """
CREATE TABLE IF NOT EXISTS projects (
    id CHAR(36) PRIMARY KEY NOT NULL,
    name VARCHAR NOT NULL,
    description TEXT,
    user_id CHAR(36),
    mission_protocol_id CHAR(36),
    research_type VARCHAR,
    methodology VARCHAR,
    status VARCHAR,
    quality_score INTEGER,
    last_quality_check DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    deleted_at DATETIME,
    deleted_by VARCHAR(100)
)
"""

_CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id CHAR(36) PRIMARY KEY NOT NULL,
    project_id CHAR(36) NOT NULL,
    name VARCHAR NOT NULL,
    file_path VARCHAR,
    file_type VARCHAR,
    content TEXT,
    raw_content BLOB,
    uploaded_at DATETIME,
    updated_at DATETIME,
    file_size BIGINT,
    mime_type VARCHAR,
    source_type VARCHAR,
    participant_count INTEGER,
    collection_date DATE,
    processed BOOLEAN,
    chunked BOOLEAN,
    embedded BOOLEAN,
    transcription_accuracy NUMERIC(3, 2),
    validation_status VARCHAR,
    document_metadata JSON,
    source_report_id CHAR(36),
    source_mission_id CHAR(36),
    source_origin VARCHAR(20),
    deleted_at DATETIME,
    deleted_by VARCHAR(100),
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
)
"""

_CREATE_CHUNKS = """
CREATE TABLE IF NOT EXISTS document_chunks (
    id CHAR(36) PRIMARY KEY NOT NULL,
    document_id CHAR(36) NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_tsv TEXT,
    embedding_id VARCHAR,
    token_count INTEGER,
    start_char INTEGER,
    end_char INTEGER,
    prev_chunk_id CHAR(36),
    next_chunk_id CHAR(36),
    created_at DATETIME,
    UNIQUE (document_id, chunk_index),
    FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
)
"""


@pytest.fixture(autouse=True)
def _create_tables():
    """Create SQLite-compatible tables for evidence auto-linking tests.

    Uses raw DDL instead of Base.metadata.create_all() to avoid
    PostgreSQL-specific features (to_tsvector generated columns,
    jsonb_array_length constraints) that break SQLite.
    """
    with engine.connect() as conn:
        conn.execute(text(_CREATE_PROJECTS))
        conn.execute(text(_CREATE_DOCUMENTS))
        conn.execute(text(_CREATE_CHUNKS))
    yield
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS document_chunks"))
        conn.execute(text("DROP TABLE IF EXISTS documents"))
        conn.execute(text("DROP TABLE IF EXISTS projects"))


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------


def _build_mission(evidence_texts: list[str]) -> MissionProtocolComplete:
    evidence_payloads = [
        {
            "evidence_id": f"EV-{index}",
            "source": "DeepSearch",
            "summary": text,
            "chunk_id": None,
        }
        for index, text in enumerate(evidence_texts, start=1)
    ]
    return MissionProtocolComplete.model_validate(
        {
            "mission_id": "DSR.10.2",
            "title": "Passwordless Auth Patterns",
            "status": "complete",
            "research_statement": {
                "topic": "Passwordless authentication",
                "objective": "Document proven implementation approaches",
                "scope": "Consumer products 2020-2025",
            },
            "key_questions": [
                {
                    "question": "What methods dominate consumer apps?",
                    "status": "answered",
                    "answer": "Magic links dominate modern implementations.",
                }
            ],
            "synthesis": {
                "key_insights": [
                    "Magic links dominate due to ease-of-use.",
                    "WebAuthn is gaining ground for high-assurance flows.",
                ],
                "surprising_findings": [],
                "contradictory_information": [],
                "contradiction_resolutions": [],
                "recommendations": ["Prototype a passwordless auth stack."],
                "next_steps": ["Ship the onboarding pilot."],
            },
            "evidence": evidence_payloads,
            "quality_checkpoints": [
                {"gate": "research_statement", "status": "pass"},
                {"gate": "evidence_links", "status": "pass"},
                {"gate": "synthesis_quality", "status": "pass"},
                {"gate": "traceability", "status": "pass"},
                {"gate": "contradictions_resolved", "status": "pass"},
            ],
        }
    )


def _seed_chunks(db_session, project_id, texts: list[str]) -> list[DocumentChunk]:
    document = Document(project_id=project_id, name="DeepSearch drop", file_type="report", content=" ".join(texts))
    db_session.add(document)
    db_session.flush()
    chunks: list[DocumentChunk] = []
    for index, text in enumerate(texts):
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=text,
            content_tsv=text,
        )
        db_session.add(chunk)
        chunks.append(chunk)
    db_session.flush()
    return chunks


# ---------------------------------------------------------------
# Original difflib path tests
# ---------------------------------------------------------------


def test_auto_linking_assigns_chunk_and_writes_telemetry(db_session, project, tmp_path):
    """Auto-linker should populate chunk_id and log telemetry when similarity passes threshold."""

    chunk_texts = [
        "Magic links dominate due to minimal friction.",
        "WebAuthn offers higher assurance for regulated industries.",
    ]
    chunks = _seed_chunks(db_session, project.id, chunk_texts)
    mission = _build_mission(["Magic links dominate due to minimal friction."])

    telemetry_path = tmp_path / "linking.jsonl"
    service = EvidenceAutoLinkingService(
        similarity_threshold=0.7,
        fallback_to_difflib=True,
        telemetry_path=telemetry_path,
    )
    service._resolve_services = lambda: (None, None)

    result = service.link_evidence(db_session, mission, project_id=project.id)

    assert result.linked == 1
    assert result.attempted == 1
    assert result.success_rate == 1.0
    assert mission.evidence[0].chunk_id == str(chunks[0].id)
    assert telemetry_path.exists()
    events = telemetry_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(events) == 1
    assert "\"mission_id\": \"DSR.10.2\"" in events[0]


def test_auto_linking_respects_threshold_and_counts_skips(db_session, project, tmp_path):
    """Evidence below the similarity threshold should remain unlinked while existing links are skipped."""

    _seed_chunks(db_session, project.id, ["Magic links dominate consumer onboarding."])
    mission = _build_mission(["Completely unrelated summary that should not match."])
    mission.evidence.append(
        {
            "evidence_id": "EV-already-linked",
            "source": "DeepSearch",
            "summary": "Pre-linked entry",
            "chunk_id": "1234",
        }
    )
    mission = MissionProtocolComplete.model_validate(mission.model_dump())

    telemetry_path = tmp_path / "linking-high-threshold.jsonl"
    service = EvidenceAutoLinkingService(
        similarity_threshold=0.95,
        fallback_to_difflib=True,
        telemetry_path=telemetry_path,
    )
    service._resolve_services = lambda: (None, None)

    result = service.link_evidence(db_session, mission, project_id=project.id, similarity_threshold=0.95)

    assert result.linked == 0
    assert result.skipped == 1  # already linked evidence
    assert result.attempted == 1
    assert result.matches[0]["chunk_id"] is None
    assert telemetry_path.exists()


# ---------------------------------------------------------------
# Embedding path tests (T29.6)
# ---------------------------------------------------------------


def test_embedding_path_links_evidence(db_session, project, tmp_path):
    """Embedding path should link evidence via Qdrant when services are available."""

    mock_embedding_svc = MagicMock()
    mock_embedding_svc.generate_embedding.return_value = [0.1] * 3072

    mock_qdrant_svc = MagicMock()
    mock_qdrant_svc.search_chunks.return_value = [
        {"chunk_id": "qdrant-chunk-001", "content": "Magic links dominate.",
         "score": 0.92, "document_id": "doc-1", "project_id": str(project.id)},
        {"chunk_id": "qdrant-chunk-002", "content": "WebAuthn for high-assurance.",
         "score": 0.71, "document_id": "doc-1", "project_id": str(project.id)},
    ]

    telemetry_path = tmp_path / "embed-link.jsonl"
    service = EvidenceAutoLinkingService(
        embedding_service=mock_embedding_svc,
        qdrant_service=mock_qdrant_svc,
        telemetry_path=telemetry_path,
    )
    mission = _build_mission(["Magic links dominate due to minimal friction."])
    result = service.link_evidence(db_session, mission, project_id=project.id)

    assert result.linked == 1
    assert result.attempted == 1
    assert result.matches[0]["method"] == "embedding"
    assert result.matches[0]["chunk_id"] == "qdrant-chunk-001"
    assert result.matches[0]["runner_up_score"] == 0.71
    assert mission.evidence[0].chunk_id == "qdrant-chunk-001"
    mock_embedding_svc.generate_embedding.assert_called_once()
    mock_qdrant_svc.search_chunks.assert_called_once()

    # Verify telemetry uses unified envelope format
    entry = json.loads(telemetry_path.read_text().strip())
    assert entry["event_type"] == "evidence.auto_linking.completed"
    assert entry["source"] == "tracelab"
    assert entry["payload"]["linking_method"] == "embedding"


def test_embedding_path_below_threshold(db_session, project, tmp_path):
    """Embedding path should report LOW_SIMILARITY when Qdrant score is below threshold."""

    mock_embedding_svc = MagicMock()
    mock_embedding_svc.generate_embedding.return_value = [0.1] * 3072

    mock_qdrant_svc = MagicMock()
    mock_qdrant_svc.search_chunks.return_value = [
        {"chunk_id": "chunk-low", "content": "Unrelated content.",
         "score": 0.50, "document_id": "doc-1", "project_id": str(project.id)},
    ]

    telemetry_path = tmp_path / "embed-low.jsonl"
    service = EvidenceAutoLinkingService(
        similarity_threshold=0.78,
        embedding_service=mock_embedding_svc,
        qdrant_service=mock_qdrant_svc,
        telemetry_path=telemetry_path,
    )
    mission = _build_mission(["Magic links dominate due to minimal friction."])
    result = service.link_evidence(db_session, mission, project_id=project.id)

    assert result.linked == 0
    assert result.failed == 1
    assert result.errors[0]["error_type"] == AutoLinkErrorType.LOW_SIMILARITY.value
    assert result.errors[0]["best_similarity"] == 0.5
    assert mission.evidence[0].chunk_id is None


def test_embedding_failure_falls_back_to_difflib(db_session, project, tmp_path):
    """When embedding services are unavailable, difflib fallback should work."""

    chunk_texts = ["Magic links dominate due to minimal friction."]
    chunks = _seed_chunks(db_session, project.id, chunk_texts)
    mission = _build_mission(["Magic links dominate due to minimal friction."])

    telemetry_path = tmp_path / "fallback.jsonl"
    service = EvidenceAutoLinkingService(
        similarity_threshold=0.7,
        embedding_service=None,
        qdrant_service=None,
        fallback_to_difflib=True,
        telemetry_path=telemetry_path,
    )
    service._resolve_services = lambda: (None, None)

    result = service.link_evidence(db_session, mission, project_id=project.id)

    assert result.linked == 1
    assert result.matches[0]["method"] == "difflib"
    assert mission.evidence[0].chunk_id == str(chunks[0].id)


def test_qdrant_error_classified_correctly(db_session, project, tmp_path):
    """Qdrant exceptions should produce QDRANT_ERROR in results."""

    mock_embedding_svc = MagicMock()
    mock_embedding_svc.generate_embedding.return_value = [0.1] * 3072

    mock_qdrant_svc = MagicMock()
    mock_qdrant_svc.search_chunks.side_effect = ConnectionError("Qdrant unreachable")

    telemetry_path = tmp_path / "qdrant-err.jsonl"
    service = EvidenceAutoLinkingService(
        embedding_service=mock_embedding_svc,
        qdrant_service=mock_qdrant_svc,
        telemetry_path=telemetry_path,
    )
    mission = _build_mission(["Magic links dominate due to minimal friction."])
    result = service.link_evidence(db_session, mission, project_id=project.id)

    assert result.failed == 1
    assert result.linked == 0
    assert result.errors[0]["error_type"] == AutoLinkErrorType.QDRANT_ERROR.value
    assert "Qdrant unreachable" in result.errors[0]["message"]


def test_fallback_disabled_fails_all(db_session, project, tmp_path):
    """When fallback is disabled and no services available, all items should fail."""

    mission = _build_mission(["Magic links dominate due to minimal friction."])

    telemetry_path = tmp_path / "no-fallback.jsonl"
    service = EvidenceAutoLinkingService(
        embedding_service=None,
        qdrant_service=None,
        fallback_to_difflib=False,
        telemetry_path=telemetry_path,
    )
    service._resolve_services = lambda: (None, None)

    result = service.link_evidence(db_session, mission, project_id=project.id)

    assert result.failed == 1
    assert result.linked == 0
    assert result.errors[0]["error_type"] == AutoLinkErrorType.EMBEDDING_FAILED.value
    assert result.matches[0]["method"] == "none"
