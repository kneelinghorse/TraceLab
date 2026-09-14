"""SEC-2: project ownership grants document reads across actual HTTP consumers."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.reports import get_report_service_factory
from app.api.v1.synthesize import get_synthesis_service_factory
from app.core.config import settings
from app.core.security import create_access_token, generate_api_key, get_key_prefix, hash_api_key
from app.main import app
from app.models.api_key import APIKey
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace
from app.services.report_service import ReportService
from app.services.synthesis import SynthesisService

API = "/api/v1"
_HASH = "unused-test-hash"


def actor(db, role="member", credential="jwt"):
    user = User(email=f"{uuid4()}@example.test", display_name="SEC-2 reader", password_hash=_HASH, role=role)
    db.add(user)
    db.flush()
    return user, credentials(db, user, credential)


def credentials(db, user, credential):
    if credential == "jwt":
        return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    key = generate_api_key()
    db.add(APIKey(user_id=user.id, name="SEC-2 test", key_hash=hash_api_key(key), key_prefix=get_key_prefix(key)))
    db.flush()
    return {"X-API-Key": key}


@pytest.fixture
def source(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    owner, headers = actor(db_session)
    other, _ = actor(db_session)
    space = Workspace(name="Project Space without owner membership")
    db_session.add(space)
    db_session.flush()
    project = Project(name="Owned research project", owner_id=owner.id, workspace_id=space.id)
    collection = Collection(name="Owned research context", owner_id=owner.id)
    db_session.add_all([project, collection])
    db_session.flush()
    file = tmp_path / "sibling.md"
    file.write_text("Sibling research source")
    document = Document(name="Sibling research source", project_id=project.id, owner_id=other.id, file_path=str(file), mime_type="text/markdown")
    db_session.add(document)
    db_session.flush()
    chunk = DocumentChunk(document_id=document.id, chunk_index=0, content="Sibling research finding", token_count=3)
    job = IngestionJob(project_id=project.id, document_id=document.id, status="PENDING")
    db_session.add_all([chunk, job])
    db_session.flush()
    db_session.add(CollectionItem(collection_id=collection.id, chunk_id=chunk.id))
    db_session.commit()
    assert db_session.query(SpaceMember).filter_by(user_id=owner.id).count() == 0
    provider = MagicMock()
    completion = MagicMock()
    completion.choices[0].message.content = "Sibling finding [1]."
    completion.usage.prompt_tokens = 10
    completion.usage.completion_tokens = 5
    completion.usage.total_tokens = 15
    provider.chat.completions.create.return_value = completion
    service = SynthesisService(client=provider, enable_cache=False, cost_monitor=MagicMock())
    # Only the external provider is replaced. Authentication and authorization are real.
    app.dependency_overrides[get_synthesis_service_factory] = lambda: lambda: service
    app.dependency_overrides[get_report_service_factory] = lambda: lambda: ReportService(synthesis_service=service)
    try:
        with TestClient(app) as client:
            yield client, owner, headers, project, document, chunk, collection, job, provider
    finally:
        app.dependency_overrides.pop(get_synthesis_service_factory, None)
        app.dependency_overrides.pop(get_report_service_factory, None)


@pytest.mark.parametrize("outsider", [False, True])
def test_document_read_consumers_and_collection_attachments(source, db_session, outsider):
    client, _, headers, project, doc, chunk, collection, job, _ = source
    if outsider:
        _, headers = actor(db_session)
        db_session.commit()
    expected = 403 if outsider else 200
    for suffix in ("", "/chunks", "/download"):
        response = client.get(f"{API}/documents/{doc.id}{suffix}", headers=headers)
        assert response.status_code == expected, (suffix, response.text)
        if not outsider:
            assert str(doc.id) in response.text if suffix != "/download" else response.text == "Sibling research source"
    listed = client.get(f"{API}/documents", params={"project_id": str(project.id)}, headers=headers)
    assert listed.status_code == 200
    assert {row["id"] for row in listed.json()["data"]} == (set() if outsider else {str(doc.id)})
    stats = client.get(f"{API}/projects/{project.id}/stats", headers=headers)
    assert stats.status_code == expected, stats.text
    if not outsider:
        assert stats.json()["document_count"] == stats.json()["chunk_count"] == 1
    detail = client.get(f"{API}/collections/{collection.id}", headers=headers)
    assert detail.status_code == expected, detail.text
    if not outsider:
        assert detail.json()["item_count"] == 1
        assert {item["chunk_id"] for item in detail.json()["items"]} == {str(chunk.id)}
    exported = client.get(f"{API}/collections/{collection.id}/export", headers=headers)
    assert exported.status_code == expected, exported.text
    assert ("Sibling research finding" in exported.text) is not outsider
    if not outsider:
        # Exercise a fresh attachment, independently of duplicate-item rejection.
        db_session.query(CollectionItem).filter_by(collection_id=collection.id, chunk_id=chunk.id).delete()
        db_session.commit()
    attached = client.post(f"{API}/collections/{collection.id}/chunks", json={"chunk_id": str(chunk.id)}, headers=headers)
    assert attached.status_code == (403 if outsider else 201), attached.text
    attached_doc = client.post(f"{API}/collections/{collection.id}/documents", json={"document_id": str(doc.id)}, headers=headers)
    assert attached_doc.status_code == (404 if outsider else 201), attached_doc.text
    navigation = client.get(f"{API}/navigation/search", params={"q": "Sibling", "entity_type": "document"}, headers=headers)
    assert navigation.status_code == 200, navigation.text
    ids = {item["id"] for group in navigation.json()["groups"] for item in group["items"]}
    assert ids == (set() if outsider else {str(doc.id)})
    job_detail = client.get(f"{API}/jobs/{job.id}", headers=headers)
    assert job_detail.status_code == expected, job_detail.text
    jobs = client.get(f"{API}/jobs", headers=headers)
    assert jobs.status_code == 200
    assert {row["document_id"] for row in jobs.json()} == (set() if outsider else {str(doc.id)})


@pytest.mark.parametrize("outsider", [False, True])
@pytest.mark.parametrize("input_kind", ["collection", "chunks"])
def test_reports_and_synthesis_persist_only_readable_sources(source, db_session, outsider, input_kind):
    client, _, headers, _, doc, chunk, collection, _, provider = source
    if outsider:
        _, headers = actor(db_session)
        db_session.commit()
    inputs = {"collection_id": str(collection.id)} if input_kind == "collection" else {"chunk_ids": [str(chunk.id)]}
    for endpoint, extra, success in (
        ("reports", {"title": "Sibling findings"}, 201),
        ("synthesize", {}, 200),
        ("synthesize", {"save_as_report": True, "report_title": "Saved sibling findings"}, 200),
    ):
        response = client.post(f"{API}/{endpoint}", json={**inputs, **extra}, headers=headers)
        assert response.status_code == (403 if outsider and input_kind == "collection" else success), response.text
        if response.status_code == 403:
            continue
        body = response.json()
        if endpoint == "synthesize":
            assert body["chunk_count"] == (0 if outsider else 1)
            assert {c["document_id"] for c in body["citations"]} == (set() if outsider else {str(doc.id)})
        report_id = body.get("report_id") if endpoint == "synthesize" else body["id"]
        if report_id:
            assert db_session.get(Report, report_id).chunk_count == (0 if outsider else 1)
            sources = db_session.query(ReportSource).filter_by(report_id=report_id, source_type="chunk").all()
            assert {str(s.source_id) for s in sources} == (set() if outsider else {str(chunk.id)})
    if outsider:
        provider.chat.completions.create.assert_not_called()


@pytest.mark.parametrize("method,path,body", [
    ("patch", "/documents/{doc}", {}),
    ("post", "/documents/{doc}/process", None),
    ("delete", "/documents/{doc}?confirm=true", None),
    ("post", "/documents/{doc}/restore", None),
    ("post", "/jobs?document_id={doc}", None),
])
def test_project_owner_cannot_mutate_sibling_document(source, db_session, method, path, body):
    client, _, headers, _, doc, _, _, _, provider = source
    before = db_session.query(IngestionJob).count()
    response = client.request(method, API + path.format(doc=doc.id), json=body, headers=headers)
    assert response.status_code == 403, response.text
    db_session.refresh(doc)
    assert doc.deleted_at is None
    assert doc.name == "Sibling research source"
    assert db_session.query(IngestionJob).count() == before
    provider.chat.completions.create.assert_not_called()


@pytest.mark.parametrize("rbac", [True, False])
@pytest.mark.parametrize("credential", ["jwt", "api_key"])
@pytest.mark.parametrize("role", ["project_owner", "member", "viewer", "admin", "owner", "service"])
def test_alternate_caller_document_read_matrix(source, db_session, monkeypatch, rbac, credential, role):
    """Decision #402: record six mounted routes for every real flag/credential/principal cell."""
    client, project_owner, _, project, doc, chunk, collection, _, _ = source
    if role == "project_owner":
        headers = credentials(db_session, project_owner, credential)
    else:
        _, headers = actor(db_session, role, credential)
    db_session.commit()
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    visible = role != "service" and (not rbac or role in {"project_owner", "admin", "owner"})
    denied = role == "service"
    rows = []
    requests = [
        ("document", "GET", f"/documents/{doc.id}", None, 403 if not visible else 200),
        ("documents", "GET", f"/documents?project_id={project.id}", None, 403 if denied else 200),
        ("export", "GET", f"/collections/{collection.id}/export", None, 403 if not visible else 200),
        ("report", "POST", "/reports", {"title": "Matrix report", "chunk_ids": [str(chunk.id)]}, 403 if denied else 201),
        ("synthesize", "POST", "/synthesize", {"chunk_ids": [str(chunk.id)]}, 403 if denied else 200),
        ("jobs", "GET", "/jobs", None, 403 if denied else 200),
    ]
    for name, method, path, body, expected in requests:
        response = client.request(method, API + path, json=body, headers=headers)
        assert response.status_code == expected, (name, response.text)
        included = set()
        if response.status_code < 300:
            if name == "document":
                included = {response.json()["id"]}
            elif name == "documents":
                included = {row["id"] for row in response.json()["data"]}
            elif name == "export":
                included = {str(doc.id)} if "Sibling research finding" in response.text else set()
            elif name == "report":
                sources = db_session.query(ReportSource).filter_by(report_id=response.json()["id"], source_type="chunk").all()
                included = {str(doc.id)} if any(str(row.source_id) == str(chunk.id) for row in sources) else set()
            elif name == "synthesize":
                included = {c["document_id"] for c in response.json()["citations"]}
            else:
                included = {row["document_id"] for row in response.json()}
        assert included == ({str(doc.id)} if visible else set()), (name, response.text)
        rows.append({"method": method, "path": API + path, "status": response.status_code, "included_document_ids": sorted(included)})
    if output := os.environ.get("SEC2_SWEEP_OUTPUT"):
        with Path(output).open("a") as stream:
            stream.write(json.dumps({"rbac_enabled": rbac, "credential": credential, "principal": role, "cells": rows}) + "\n")
