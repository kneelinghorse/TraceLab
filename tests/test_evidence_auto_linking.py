"""Unit tests for the evidence auto-linking service."""
from __future__ import annotations

from pathlib import Path

from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.models.mission_protocol import MissionProtocolComplete
from app.services.evidence_auto_linking import EvidenceAutoLinkingService


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


def test_auto_linking_assigns_chunk_and_writes_telemetry(db_session, project, tmp_path):
    """Auto-linker should populate chunk_id and log telemetry when similarity passes threshold."""

    chunk_texts = [
        "Magic links dominate due to minimal friction.",
        "WebAuthn offers higher assurance for regulated industries.",
    ]
    chunks = _seed_chunks(db_session, project.id, chunk_texts)
    mission = _build_mission(["Magic links dominate due to minimal friction."])

    telemetry_path = tmp_path / "linking.jsonl"
    service = EvidenceAutoLinkingService(telemetry_path=telemetry_path)

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
    service = EvidenceAutoLinkingService(similarity_threshold=0.95, telemetry_path=telemetry_path)

    result = service.link_evidence(db_session, mission, project_id=project.id, similarity_threshold=0.95)

    assert result.linked == 0
    assert result.skipped == 1  # already linked evidence
    assert result.attempted == 1
    assert result.matches[0]["chunk_id"] is None
    assert telemetry_path.exists()
