"""Project bundles must count the full readable set and keep favorites private."""

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
from app.models.report import Report
from app.models.user import User

API = "/api/v1"

_HASH = "placeholder-not-a-real-hash"


def actor(db):
    row = User(email=f"{uuid4()}@example.test", display_name="Bundle reader", password_hash=_HASH, role="member")
    db.add(row)
    db.flush()
    return row, {"Authorization": f"Bearer {create_access_token(subject=str(row.id))}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    with TestClient(app) as client:
        yield client


def test_project_stats_count_all_readable_children_not_one_page_or_other_owners(client, db_session):
    first, headers = actor(db_session)
    other, _ = actor(db_session)
    project = Project(name="Large bundle", owner_id=first.id)
    db_session.add(project)
    db_session.flush()
    for index in range(124):
        doc = Document(project_id=project.id, name=f"Document {index}", owner_id=first.id if index < 123 else other.id)
        db_session.add(doc)
        db_session.flush()
        db_session.add_all([DocumentChunk(document_id=doc.id, chunk_index=i, content="A source", token_count=7) for i in range(2)])
    db_session.add_all([
        Report(project_id=project.id, title="Readable report", content="Result", owner_id=first.id),
        Report(project_id=project.id, title="Private report", content="Hidden", owner_id=other.id),
        Document(project_id=project.id, name="Deleted", owner_id=first.id, deleted_at=datetime.utcnow()),
    ])
    db_session.commit()
    stats = client.get(f"{API}/projects/{project.id}/stats", headers=headers)
    assert stats.status_code == 200, stats.text
    assert stats.json()["document_count"] == 123
    assert stats.json()["chunk_count"] == 246
    assert stats.json()["total_tokens"] == 1722
    assert stats.json()["report_count"] == 1
    listed = client.get(f"{API}/documents", params={"project_id": str(project.id), "page_size": 100}, headers=headers).json()
    assert listed["pagination"]["total"] == stats.json()["document_count"]
    assert len(listed["data"]) == 100


def test_favorites_are_idempotent_per_user_and_disappear_when_access_is_lost(client, db_session):
    first, headers = actor(db_session)
    _, other_headers = actor(db_session)
    project = Project(name="Personal shortcut", owner_id=first.id)
    db_session.add(project)
    db_session.commit()
    path = f"{API}/home/favorites/projects/{project.id}"
    for _ in range(2):
        assert client.put(path, headers=headers).status_code == 204
    snapshot = client.get(f"{API}/home", headers=headers).json()
    assert snapshot["favorites"]["total"] == 1
    assert snapshot["favorites"]["items"][0]["href"] == f"/projects/{project.id}"
    assert client.get(f"{API}/home", headers=other_headers).json()["favorites"]["total"] == 0
    assert client.put(path, headers=other_headers).status_code == 404
    selected = client.get(f"{API}/home/favorites", params={"project_id": str(project.id)}, headers=headers).json()
    assert selected["total"] == 1
    project.deleted_at = datetime.utcnow()
    db_session.commit()
    assert client.get(f"{API}/home", headers=headers).json()["favorites"]["total"] == 0
    assert client.put(path, headers=headers).status_code == 404
    # Removing one's stale shortcut is safe even when its resource was removed.
    assert client.delete(path, headers=headers).status_code == 204


def test_project_collections_page_only_real_readable_chunk_relationships(client, db_session):
    first, headers = actor(db_session)
    other, _ = actor(db_session)
    project = Project(name="Bundle", owner_id=first.id)
    db_session.add(project)
    db_session.flush()
    doc = Document(name="Source", project_id=project.id, owner_id=first.id)
    hidden = Document(name="Private source", project_id=project.id, owner_id=other.id)
    db_session.add_all([doc, hidden])
    db_session.flush()
    chunks = [DocumentChunk(document_id=d.id, chunk_index=0, content="Context") for d in [doc, hidden]]
    db_session.add_all(chunks)
    db_session.flush()
    for i in range(24):
        collection = Collection(name=f"Context {i}", owner_id=first.id if i < 23 else other.id)
        db_session.add(collection)
        db_session.flush()
        db_session.add(CollectionItem(collection_id=collection.id, chunk_id=chunks[0 if i < 22 else 1].id))
    db_session.commit()
    params = {"project_id": str(project.id), "page": 2, "page_size": 20}
    response = client.get(f"{API}/collections", params=params, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 22
    assert len(response.json()["data"]) == 2
    assert client.get(f"{API}/collections", params={**params, "project_id": str(uuid4())}, headers=headers).status_code == 404


def test_upload_and_delete_refresh_cached_project_counts(client, db_session, monkeypatch, tmp_path):
    from app.api.v1 import documents as documents_route

    monkeypatch.setattr(documents_route, "UPLOAD_DIR", tmp_path)
    user, headers = actor(db_session)
    user.role = "admin"
    project = Project(name="Fresh upload counts", owner_id=user.id)
    db_session.add(project)
    db_session.commit()
    stats_path = f"{API}/projects/{project.id}/stats"
    assert client.get(stats_path, headers=headers).json()["document_count"] == 0

    uploaded = client.post(f"{API}/documents/upload", params={"project_id": str(project.id)}, files={"file": ("source.txt", b"Primary research source.", "text/plain")}, headers=headers)
    assert uploaded.status_code == 200, uploaded.text
    assert client.get(stats_path, headers=headers).json()["document_count"] == 1
    assert client.delete(f"{API}/documents/{uploaded.json()['id']}?confirm=true", headers=headers).status_code == 200
    assert client.get(stats_path, headers=headers).json()["document_count"] == 0


def test_upload_authorizes_the_project_before_persisting_a_file(client, db_session, monkeypatch, tmp_path):
    from app.api.v1 import documents as documents_route

    monkeypatch.setattr(documents_route, "UPLOAD_DIR", tmp_path)
    owner, owner_headers = actor(db_session)
    _, stranger_headers = actor(db_session)
    project = Project(name="Private upload target", owner_id=owner.id)
    db_session.add(project)
    db_session.commit()
    args = {"params": {"project_id": str(project.id)}, "files": {"file": ("source.txt", b"Original source.", "text/plain")}}
    assert client.post(f"{API}/documents/upload", headers=stranger_headers, **args).status_code == 403
    assert not list(tmp_path.iterdir())
    project.deleted_at = datetime.utcnow()
    db_session.commit()
    assert client.post(f"{API}/documents/upload", headers=owner_headers, **args).status_code == 404
    assert not list(tmp_path.iterdir())
