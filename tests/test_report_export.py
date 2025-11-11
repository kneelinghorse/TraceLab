"""Unit tests for the ReportExportService."""
from __future__ import annotations

import pytest

from app.models.mission_protocol import MissionProtocolDraft
from app.services.report_export import ReportExportService


def _mission_payload() -> MissionProtocolDraft:
    return MissionProtocolDraft.model_validate(
        {
            "mission_id": "B6.5-test",
            "title": "Report Export System",
            "version": "1.0.0",
            "status": "complete",
            "owner": "Agent Zero",
            "summary": "Generate traceable multi-format reports",
            "research_statement": {
                "topic": "Reporting",
                "objective": "Share readable mission summaries",
                "scope": "Mission Protocol",
                "audience": "Executives",
                "methodology": "Desk research",
                "success_metrics": ["All gates pass", "Reports include citations"],
                "risks": ["Missing citations", "Out-of-date evidence"],
            },
            "key_questions": [
                {
                    "question": "How do exports include citations?",
                    "status": "answered",
                    "answer": "Embed chunk IDs and sources",
                    "confidence": 0.9,
                    "owner": "Agent Zero",
                }
            ],
            "synthesis": {
                "key_insights": ["Markdown is the canonical template."],
                "surprising_findings": ["Existing CLI already had an export stub."],
                "contradictory_information": [],
                "contradiction_resolutions": [],
                "recommendations": ["Add PDF and DOCX flows."],
                "next_steps": ["Ship UI button."],
            },
            "evidence": [
                {
                    "evidence_id": "EV-001",
                    "source": "docs/mission_protocol.md",
                    "summary": "Mission Protocol captures enough metadata for exports.",
                    "chunk_id": "11111111-1111-1111-1111-111111111111",
                    "relevance_score": 0.87,
                }
            ],
            "quality_checkpoints": [
                {"gate": "research_statement", "status": "pass"},
                {"gate": "evidence_links", "status": "pass"},
                {"gate": "synthesis_quality", "status": "pass"},
            ],
            "methodology_details": {
                "total_participants": 12,
                "participant_segments": [
                    {"segment": "PM", "count": 7},
                    {"segment": "Researcher", "percentage": 0.25},
                ],
                "recruitment_method": "Internal backlog",
                "validation_steps_completed": ["Peer review"],
                "artifacts_verified": ["reports.md"],
                "notes": "Synthetic mission data",
            },
            "tags": ["reporting", "mission-protocol"],
            "discussion_guide": ["Outline motivation", "Demo export"],
        }
    )


def test_markdown_export_contains_required_sections(tmp_path):
    service = ReportExportService()
    result = service.export(_mission_payload(), format="md", completion_percentage=95)
    assert result.filename.endswith(".md")
    assert result.media_type.startswith("text/markdown")
    markdown = result.content.decode("utf-8")
    assert "# Report Export System" in markdown
    assert "Evidence Summary" in markdown
    assert "Mission ID" in markdown


def test_docx_export_creates_office_document():
    pytest.importorskip("docx")
    service = ReportExportService()
    result = service.export(_mission_payload(), format="docx", completion_percentage=95)
    assert result.filename.endswith(".docx")
    # DOCX is a ZIP archive starting with PK header
    assert result.content[:2] == b"PK"


def test_pdf_export_starts_with_pdf_header():
    pytest.importorskip("reportlab")
    service = ReportExportService()
    result = service.export(_mission_payload(), format="pdf", completion_percentage=95)
    assert result.filename.endswith(".pdf")
    assert result.content.startswith(b"%PDF")
