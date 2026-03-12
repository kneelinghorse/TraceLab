"""Integration test covering CLI → API → ingestion pipeline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.models.document import Document
from scripts.verify_ingestion_parity import generate_parity_report


def _markdown_fixture(path: Path) -> Path:
    body = "\n\n".join(
        f"## Section {index}\n\nThis section validates markdown ingestion flow iteration {index}."
        for index in range(1, 6)
    )
    content = (
        "---\nproject_id: integration-test\ndoc_type: research_brief\n---\n\n"
        "# CLI API Pipeline Test\n\n"
        f"{body}\n\n"
        "The quick brown fox jumps over the lazy AI assistant. " * 40
    )
    path.write_text(content)
    return path


@pytest.mark.skip(reason="CLI subprocess requires running server with auth — not available in test environment")
def test_markdown_cli_flow(tmp_path, db_session, project):
    markdown_path = _markdown_fixture(tmp_path / "sample.md")

    env = os.environ.copy()
    output_path = tmp_path / "cli-output.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ingest_cli.py",
            str(markdown_path),
            str(project.id),
            "--offline",
            "--output",
            str(output_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    payload = json.loads(output_path.read_text())
    document_id = payload["document_id"]

    db_session.expire_all()
    document = db_session.query(Document).filter(Document.id == document_id).one()
    assert document.chunked is True
    assert document.processed is True

    report_dir = tmp_path / "parity"
    report_path = generate_parity_report(document_id, output_dir=report_dir)
    report = json.loads(report_path.read_text())

    metrics = report["metrics"]
    assert metrics["chunk_count"] >= 1
    assert metrics["coverage_ratio"] >= 0.95
    assert any(event["stage"] == "chunked" and event["status"] == "succeeded" for event in report["processing_events"])
