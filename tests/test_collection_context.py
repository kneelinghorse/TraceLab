"""Collections carry complete, currently readable document context into authoring."""

from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.project import Project
from app.models.user import User

API = "/api/v1"
_HASH = "placeholder-not-a-real-hash"


@pytest.fixture
def context_fixture(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    owner = User(email=f"{uuid4()}@example.test", display_name="Context author", password_hash=_HASH, role="member")
    other = User(email=f"{uuid4()}@example.test", display_name="Other author", password_hash=_HASH, role="member")
    db_session.add_all([owner, other])
    db_session.flush()
    project = Project(name="Source project", owner_id=owner.id)
    collection = Collection(name="Research context", owner_id=owner.id)
    db_session.add_all([project, collection])
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(subject=str(owner.id))}"}
    other_headers = {"Authorization": f"Bearer {create_access_token(subject=str(other.id))}"}
    with TestClient(app) as client:
        yield client, owner, other, project, collection, headers, other_headers


def test_instructions_are_persisted_and_can_be_explicitly_cleared(context_fixture):
    client, _, _, _, collection, headers, _ = context_fixture
    path = f"{API}/collections/{collection.id}"
    assert client.put(path, json={"instructions": "Compare primary sources and preserve contradictions."}, headers=headers).status_code == 200
    assert client.get(path, headers=headers).json()["instructions"] == "Compare primary sources and preserve contradictions."
    assert client.put(path, json={"instructions": None}, headers=headers).status_code == 200
    assert client.get(path, headers=headers).json()["instructions"] is None


def test_document_context_pages_and_seed_include_more_than_one_hundred_unique_sources(context_fixture, db_session):
    client, owner, other, project, collection, headers, _ = context_fixture
    documents = [Document(name=f"Source {index:03}", project_id=project.id, owner_id=owner.id) for index in range(124)]
    db_session.add_all(documents)
    db_session.commit()
    path = f"{API}/collections/{collection.id}"
    for doc in documents:
        assert client.post(path + "/documents", json={"document_id": str(doc.id)}, headers=headers).status_code == 201
    # Repeated additions and existing excerpts must not double-count a document.
    assert client.post(path + "/documents", json={"document_id": str(documents[0].id)}, headers=headers).status_code == 201
    chunk = DocumentChunk(document_id=documents[0].id, chunk_index=0, content="An excerpt already in context")
    db_session.add(chunk)
    db_session.flush()
    db_session.add(CollectionItem(collection_id=collection.id, chunk_id=chunk.id))
    # Losing read access removes the child from both totals and the seed immediately.
    documents[-1].owner_id = other.id
    db_session.commit()
    first = client.get(path + "/documents?page=1&page_size=100", headers=headers)
    second = client.get(path + "/documents?page=2&page_size=100", headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 123
    assert len(first.json()["items"]) == 100
    assert len(second.json()["items"]) == 23
    ids = {row["id"] for row in first.json()["items"] + second.json()["items"]}
    assert len(ids) == 123 and str(documents[-1].id) not in ids
    client.put(path, json={"instructions": "Audit the original research sources."}, headers=headers)
    seed = client.get(path + "/mission-seed", headers=headers)
    assert seed.status_code == 200, seed.text
    payload = seed.json()
    assert payload["background"].startswith("Audit the original research sources.")
    assert payload["project_id"] == str(project.id)
    assert {ref["document_id"] for ref in payload["references"]} == ids
    assert set(payload["context"]["document_ids"]) == ids
    assert payload["context"]["collection_id"] == str(collection.id)
    assert all(ref["href"] == f"/documents/{ref['document_id']}" for ref in payload["references"])
    assert all(ref["document_id"] in payload["background"] for ref in payload["references"])


def test_removal_detaches_document_and_excerpts_without_deleting_the_source(context_fixture, db_session):
    client, owner, _, project, collection, headers, _ = context_fixture
    doc = Document(name="Keep the source", project_id=project.id, owner_id=owner.id)
    db_session.add(doc)
    db_session.flush()
    chunk = DocumentChunk(document_id=doc.id, chunk_index=0, content="Collected excerpt")
    db_session.add(chunk)
    db_session.flush()
    db_session.add(CollectionItem(collection_id=collection.id, chunk_id=chunk.id))
    db_session.commit()
    path = f"{API}/collections/{collection.id}/documents"
    assert client.get(path, headers=headers).json()["total"] == 1
    assert client.post(path, json={"document_id": str(doc.id)}, headers=headers).status_code == 201
    assert client.delete(path + f"/{doc.id}", headers=headers).status_code == 204
    assert client.get(path, headers=headers).json()["total"] == 0
    assert client.get(f"{API}/documents/{doc.id}", headers=headers).status_code == 200
    assert db_session.query(DocumentChunk).filter_by(id=chunk.id).count() == 1
    assert db_session.query(CollectionItem).filter_by(collection_id=collection.id).count() == 0


def test_context_requires_collection_and_document_access_and_excludes_deleted_parents(context_fixture, db_session):
    client, owner, other, project, collection, headers, other_headers = context_fixture
    doc = Document(name="Readable", project_id=project.id, owner_id=owner.id)
    hidden = Document(name="Private", project_id=project.id, owner_id=other.id)
    db_session.add_all([doc, hidden])
    db_session.commit()
    path = f"{API}/collections/{collection.id}"
    assert client.get(path + "/mission-seed", headers=other_headers).status_code == 404
    assert client.get(path + "/documents", headers=other_headers).status_code == 404
    assert client.post(path + "/documents", json={"document_id": str(doc.id)}, headers=other_headers).status_code == 404
    assert client.post(path + "/documents", json={"document_id": str(hidden.id)}, headers=headers).status_code == 404
    assert client.post(path + "/documents", json={"document_id": str(doc.id)}, headers=headers).status_code == 201
    project.deleted_at = datetime.utcnow()
    db_session.commit()
    assert client.get(path + "/documents", headers=headers).json()["total"] == 0
    assert client.get(path + "/mission-seed", headers=headers).json()["references"] == []
    assert client.post(path + "/documents", json={"document_id": str(doc.id)}, headers=headers).status_code == 404


def test_project_collection_tab_includes_direct_documents_without_inventing_chunks(context_fixture, db_session):
    client, owner, _, project, collection, headers, _ = context_fixture
    doc = Document(name="Not processed yet", project_id=project.id, owner_id=owner.id)
    db_session.add(doc)
    db_session.commit()
    listing = f"{API}/collections?project_id={project.id}&page_size=20"
    assert client.get(listing, headers=headers).json()["total"] == 0
    assert client.post(f"{API}/collections/{collection.id}/documents", json={"document_id": str(doc.id)}, headers=headers).status_code == 201
    result = client.get(listing, headers=headers).json()
    assert result["total"] == 1
    assert result["data"][0]["id"] == str(collection.id)
    assert result["data"][0]["item_count"] == 0


def test_collection_detail_and_export_do_not_reveal_unreadable_document_excerpts(context_fixture, db_session):
    client, owner, other, project, collection, headers, _ = context_fixture
    docs = [Document(name="Visible", project_id=project.id, owner_id=owner.id), Document(name="Private", project_id=project.id, owner_id=other.id), Document(name="Deleted", project_id=project.id, owner_id=owner.id, deleted_at=datetime.utcnow())]
    db_session.add_all(docs)
    db_session.flush()
    chunks = [DocumentChunk(document_id=doc.id, chunk_index=0, content=text) for doc, text in zip(docs, ["Readable source excerpt", "Private child secret", "Deleted child secret"], strict=True)]
    db_session.add_all(chunks)
    db_session.flush()
    db_session.add_all([CollectionItem(collection_id=collection.id, chunk_id=chunk.id) for chunk in chunks])
    db_session.commit()
    path = f"{API}/collections/{collection.id}"
    detail = client.get(path, headers=headers).json()
    assert {item["chunk_id"] for item in detail["items"]} == {str(chunks[0].id)}
    assert detail["item_count"] == 1
    exported = client.get(path + "/export", headers=headers)
    assert exported.status_code == 200
    assert "Readable source excerpt" in exported.text
    assert "Private child secret" not in exported.text
    assert "Deleted child secret" not in exported.text


def test_report_creation_resolves_readable_document_subset_before_synthesis(context_fixture, db_session):
    """A report must not send a private sibling document to a provider or persist it as a source."""
    from unittest.mock import MagicMock

    from app.api.v1.reports import get_report_service_factory
    from app.models.report import ReportSource
    from app.services.report_service import ReportService

    client, owner, other, project, collection, headers, _ = context_fixture
    public = Document(name="Readable source", project_id=project.id, owner_id=owner.id)
    private = Document(name="Private sibling", project_id=project.id, owner_id=other.id)
    db_session.add_all([public, private])
    db_session.flush()
    chunks = [DocumentChunk(document_id=doc.id, chunk_index=0, content=doc.name) for doc in (public, private)]
    db_session.add_all(chunks)
    db_session.flush()
    db_session.add_all([CollectionItem(collection_id=collection.id, chunk_id=chunk.id) for chunk in chunks])
    db_session.commit()
    synthesis = MagicMock()
    synthesis.synthesize.return_value = {"content": "Readable findings", "citations": [], "effective_chunk_ids": [str(chunks[0].id)], "chunk_count": 1}
    app.dependency_overrides[get_report_service_factory] = lambda: lambda: ReportService(synthesis_service=synthesis)
    try:
        response = client.post(f"{API}/reports", json={"title": "Scoped collection report", "collection_id": str(collection.id)}, headers=headers)
        assert response.status_code == 201, response.text
        call = synthesis.synthesize.call_args.kwargs
        assert call.get("collection_id") is None, "The provider must receive a resolved subset, never re-expand the parent"
        assert call["chunk_ids"] == [chunks[0].id]
        sources = db_session.query(ReportSource).filter(ReportSource.report_id == response.json()["id"], ReportSource.source_type == "chunk").all()
        assert [str(source.source_id) for source in sources] == [str(chunks[0].id)]
    finally:
        app.dependency_overrides.pop(get_report_service_factory, None)


@pytest.mark.parametrize("format", ["md", "txt", "json"])
def test_report_export_bytes_remain_stable_with_citation_ui(context_fixture, db_session, format):
    """Presentation must not rewrite the authored artifact, citations, Unicode or whitespace."""
    import json
    from uuid import UUID

    from app.models.report import Report

    client, owner, _, _, _, headers, _ = context_fixture
    stamp = datetime(2026, 9, 13, 12, 0, 0)
    report = Report(id=UUID("80000000-0000-4000-8000-000000000008"), title="Cafe / findings", content="A café claim.\n\n[source](https://example.test/primary)\n", owner_id=owner.id, status="final", report_type="markdown", tokens_used=12, chunk_count=1, created_at=stamp, updated_at=stamp)
    db_session.add(report)
    db_session.commit()
    expected = {
        "md": "# Cafe / findings\n\nA café claim.\n\n[source](https://example.test/primary)\n",
        "txt": "Cafe / findings\n===============\n\nA café claim.\n\n[source](https://example.test/primary)\n",
        "json": json.dumps({"id": str(report.id), "title": "Cafe / findings", "content": "A café claim.\n\n[source](https://example.test/primary)\n", "citations": [], "tokens_used": 12, "status": "final", "created_at": "2026-09-13T12:00:00", "project_id": None, "report_type": "markdown", "prompt": None, "chunk_count": 1, "sources": [], "updated_at": "2026-09-13T12:00:00"}, indent=2),
    }
    response = client.get(f"{API}/reports/{report.id}/export", params={"format": format}, headers=headers)
    assert response.status_code == 200
    assert response.content == expected[format].encode("utf-8")
    assert response.headers["content-disposition"] == f'attachment; filename="Cafe---findings.{format}"'


def test_unicode_report_title_exports_without_invalid_response_headers(context_fixture, db_session):
    from app.models.report import Report

    client, owner, _, _, _, headers, _ = context_fixture
    report = Report(title="Café 研究", content="Original café text\n", owner_id=owner.id)
    db_session.add(report)
    db_session.commit()
    response = client.get(f"{API}/reports/{report.id}/export?format=md", headers=headers)
    assert response.status_code == 200
    assert response.content == "# Café 研究\n\nOriginal café text\n".encode()
    assert "filename*=UTF-8''Caf%C3%A9-%E7%A0%94%E7%A9%B6.md" in response.headers["content-disposition"]
