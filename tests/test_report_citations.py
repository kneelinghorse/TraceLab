"""REPORT-1: a saved claim must keep its exact, still-readable support."""

from unittest.mock import Mock

import pytest

from app.services.synthesis import SynthesisService


@pytest.fixture
def synthesis():
    return SynthesisService(client=Mock(), cost_monitor=Mock(), enable_cache=False)


def test_sparse_repeated_markers_keep_their_identity(synthesis):
    sources = {
        1: {"chunk_id": "a", "document_id": "doc", "excerpt": "First"},
        3: {"chunk_id": "c", "document_id": "doc", "excerpt": "Third"},
    }
    content = "First finding [1]. Third finding [3]. Repeated [1]."
    text, citations = synthesis._process_citations(content, sources)
    assert text == content
    assert [(c["marker"], c["chunk_id"]) for c in citations] == [(1, "a"), (3, "c")]


@pytest.mark.parametrize("content", ["Invented support [99].", "Uncited finding.", "Supported [1].\n\nUncited finding."])
def test_fabricated_or_uncited_claims_cannot_be_grounded(synthesis, content):
    with pytest.raises(ValueError, match="citation"):
        synthesis._process_citations(content, {1: {"chunk_id": "a", "excerpt": "Actual text"}})


def test_empty_sources_never_enter_the_supplied_context(synthesis):
    _, mapping, _ = synthesis._build_context([
        {"chunk_id": "a", "content": "  "},
        {"chunk_id": "b", "content": "Useful text"},
    ])
    assert 1 not in mapping
    assert mapping[2]["chunk_id"] == "b"


@pytest.fixture(autouse=True)
def isolated_collaborators(monkeypatch):
    """No provider, Qdrant or outbound service may escape this regression suite."""
    import socket

    from app.core.config import settings

    monkeypatch.setattr(settings, "rbac_enabled", False)
    def forbidden(*args, **kwargs):
        raise AssertionError("REPORT-1 tests must not use outbound network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)


@pytest.fixture
def corpus(db_session):
    from tests.test_reports_api import _create_test_chunk, _create_test_document, _create_test_project

    project = _create_test_project(db_session)
    document = _create_test_document(db_session, project.id)
    chunks = [_create_test_chunk(db_session, document.id, i, f"Finding number {i}.") for i in range(3)]
    return project, document, chunks


@pytest.fixture
def report_client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.v1.reports import get_report_service_factory
    from app.api.v1.synthesize import get_synthesis_service_factory
    from app.main import app
    from app.services.report_service import ReportService
    from app.services.synthesis_cache import SynthesisCacheService

    synthesis = SynthesisService(client=Mock(), cost_monitor=Mock(), cache_service=SynthesisCacheService())
    completion = Mock(return_value=("First finding [1]. Third finding [3]. Again [1].", {"total_tokens": 50}))
    monkeypatch.setattr(synthesis, "_generate_completion", completion)
    app.dependency_overrides[get_report_service_factory] = lambda: lambda: ReportService(synthesis_service=synthesis)
    app.dependency_overrides[get_synthesis_service_factory] = lambda: lambda: synthesis
    # No lifespan: startup probes are not part of report route behavior.
    try:
        yield TestClient(app), synthesis, completion
    finally:
        app.dependency_overrides.pop(get_report_service_factory, None)
        app.dependency_overrides.pop(get_synthesis_service_factory, None)


@pytest.mark.parametrize("writer", ["reports", "synthesize"])
def test_both_writers_reload_update_export_exact_sparse_citations(writer, report_client, corpus, auth_headers, db_session):
    from app.models.report import Report, ReportSource

    client, _, completion = report_client
    project, _, chunks = corpus
    body = {"chunk_ids": [str(c.id) for c in chunks], "project_id": str(project.id)}
    body.update({"title": "Cited report"} if writer == "reports" else {"save_as_report": True, "report_title": "Cited report"})
    created = client.post(f"/api/v1/{writer}", json=body, headers=auth_headers)
    assert created.status_code in (200, 201), created.text
    data = created.json()
    report_id = data.get("report_id") or data["id"]
    reopened = client.get(f"/api/v1/reports/{report_id}", headers=auth_headers).json()
    assert reopened["content"] == data["content"]
    assert [(c["marker"], c["chunk_id"]) for c in reopened["citations"]] == [(c["marker"], c["chunk_id"]) for c in data["citations"]]
    assert [c["marker"] for c in reopened["citations"]] == [1, 3]
    assert all(c["available"] and f"chunk={c['chunk_id']}" in c["href"] for c in reopened["citations"])
    assert reopened["generation_provenance"]["accepted_by"] is None
    updated = client.put(f"/api/v1/reports/{report_id}", json={"status": "final"}, headers=auth_headers).json()
    assert updated["citations"] == reopened["citations"]
    exported = client.get(f"/api/v1/reports/{report_id}/export?format=json", headers=auth_headers).json()
    assert exported["citations"] == reopened["citations"]
    for fmt in ("md", "txt"):
        output = client.get(f"/api/v1/reports/{report_id}/export?format={fmt}", headers=auth_headers).text
        assert reopened["content"] in output
        assert reopened["citations"][1]["href"] in output
        assert "[3] http" in output
    replay = client.post(f"/api/v1/{writer}", json=body, headers=auth_headers).json()
    assert [(c["marker"], c["chunk_id"]) for c in replay["citations"]] == [(c["marker"], c["chunk_id"]) for c in data["citations"]]
    assert completion.call_count == 1
    saved = db_session.get(Report, report_id)
    assert {str(s.source_id) for s in db_session.query(ReportSource).filter_by(report_id=saved.id, source_type="chunk")} == {str(c.id) for c in chunks}


@pytest.mark.parametrize("change", ["deleted", "project_deleted", "revoked", "edited", "removed"])
def test_lost_support_is_unavailable_without_leaking_source(change, report_client, corpus, auth_headers, db_session, monkeypatch):
    from datetime import datetime

    from sqlalchemy import false

    client, _, _ = report_client
    project, doc, chunks = corpus
    created = client.post("/api/v1/reports", json={"title": "Retained prose", "chunk_ids": [str(c.id) for c in chunks]}, headers=auth_headers).json()
    if change == "deleted":
        doc.deleted_at = datetime.utcnow()
    elif change == "project_deleted":
        project.deleted_at = datetime.utcnow()
    elif change == "revoked":
        monkeypatch.setattr("app.services.report_citations.document_read_policy", lambda *args: false())
    elif change == "edited":
        for chunk in chunks:
            chunk.content = "Replacement text"
    else:
        for chunk in chunks:
            db_session.delete(chunk)
    db_session.commit()
    reopened = client.get(f"/api/v1/reports/{created['id']}", headers=auth_headers).json()
    assert reopened["content"] == created["content"]
    for citation in reopened["citations"]:
        assert citation["available"] is False
        assert citation["chunk_id"] is None and citation["document_id"] is None
        assert citation["href"] is None and citation["excerpt"] == ""


@pytest.mark.parametrize("writer", ["reports", "synthesize"])
def test_source_removed_during_generation_prevents_report_write(writer, report_client, corpus, auth_headers, db_session):
    from app.models.report import Report

    client, _, completion = report_client
    _, doc, chunks = corpus
    def generate(*args):
        from datetime import datetime
        doc.deleted_at = datetime.utcnow()
        db_session.commit()
        return "Finding [1].", {"total_tokens": 5}
    completion.side_effect = generate
    body = {"chunk_ids": [str(c.id) for c in chunks]}
    body.update({"title": "Unsafe"} if writer == "reports" else {"save_as_report": True, "report_title": "Unsafe"})
    response = client.post(f"/api/v1/{writer}", json=body, headers=auth_headers)
    assert response.status_code == 400, response.text
    assert db_session.query(Report).count() == 0


def test_legacy_has_no_invented_mapping_and_unchanged_text_exports(report_client, corpus, auth_headers, db_session):
    from app.models.report import Report, ReportSource

    client, _, _ = report_client
    _, _, chunks = corpus
    report = Report(title="Legacy", content="An old claim [3].")
    db_session.add(report)
    db_session.flush()
    db_session.add(ReportSource(report_id=report.id, source_type="chunk", source_id=chunks[0].id))
    db_session.commit()
    data = client.get(f"/api/v1/reports/{report.id}", headers=auth_headers).json()
    assert data["citations"] == [] and data["citation_status"] == "legacy_unavailable"
    output = client.get(f"/api/v1/reports/{report.id}/export?format=md", headers=auth_headers).text
    assert output == "# Legacy\n\nAn old claim [3]."


def test_context_budget_excludes_unsupplied_chunks_from_persistence(report_client, corpus, auth_headers, db_session, monkeypatch):
    from app.models.report import ReportSource

    client, _, completion = report_client
    _, _, chunks = corpus
    monkeypatch.setattr("app.services.synthesis.MAX_CONTEXT_CHARS", 30)
    completion.return_value = ("Only one finding [1].", {})
    created = client.post("/api/v1/reports", json={"title": "Bounded", "chunk_ids": [str(c.id) for c in chunks]}, headers=auth_headers)
    assert created.status_code == 201, created.text
    sources = db_session.query(ReportSource).filter_by(report_id=created.json()["id"], source_type="chunk").all()
    assert len(sources) == 1
    assert str(sources[0].source_id) == created.json()["citations"][0]["chunk_id"]


def test_cache_never_reuses_citations_for_rewritten_text(report_client, corpus, auth_headers, db_session):
    client, _, completion = report_client
    _, _, chunks = corpus
    body = {"title": "Cache integrity", "chunk_ids": [str(c.id) for c in chunks]}
    first = client.post("/api/v1/reports", json=body, headers=auth_headers)
    assert first.status_code == 201, first.text
    for chunk in chunks:
        chunk.content = "Rewritten source content"
    db_session.commit()
    second = client.post("/api/v1/reports", json=body, headers=auth_headers)
    assert second.status_code == 201, second.text
    assert completion.call_count == 2
    assert all(c["excerpt"] == "Rewritten source content" for c in second.json()["citations"])


@pytest.mark.parametrize("mutation", ["fabricated_marker", "foreign_chunk", "empty_text", "missing_hash"])
def test_persistence_refuses_fabricated_support(mutation, corpus, db_session):
    from app.services.report_citations import persistable_citations, text_hash

    _, doc, chunks = corpus
    citation = {"marker": 1, "chunk_id": str(chunks[0].id), "document_id": str(doc.id), "content_hash": text_hash(chunks[0].content)}
    result = {"content": "Supported claim [1].", "citations": [citation], "effective_chunk_ids": [str(chunks[0].id)]}
    if mutation == "fabricated_marker":
        result["content"] = "Forged claim [99]."
    elif mutation == "foreign_chunk":
        result["effective_chunk_ids"] = [str(chunks[1].id)]
    elif mutation == "empty_text":
        chunks[0].content = ""
        db_session.commit()
    else:
        citation.pop("content_hash")
    with pytest.raises(ValueError, match="citation"):
        persistable_citations(db_session, result)
