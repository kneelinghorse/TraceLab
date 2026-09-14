"""SEC-1: cached responses and host paths must not bypass resource authorization."""

import json
import os
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
)
from app.main import app
from app.models.api_key import APIKey
from app.models.document import Document
from app.models.idempotency import IdempotencyRecord
from app.models.ingestion_job import IngestionJob
from app.models.processing_status import DocumentProcessingStatus
from app.models.project import Project
from app.models.user import User
from app.onboarding import api as onboarding_api

API = "/api/v1"
COUNTED = (Project, Document, DocumentProcessingStatus, IdempotencyRecord, IngestionJob)
_HASH = "unused-test-hash"


def actor(db, role="member", credential="jwt"):
    user = User(email=f"{uuid4()}@example.test", display_name="SEC-1 caller", password_hash=_HASH, role=role)
    db.add(user)
    db.flush()
    if credential == "jwt":
        headers = {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    else:
        key = generate_api_key()
        db.add(APIKey(user_id=user.id, name="SEC-1 test", key_hash=hash_api_key(key), key_prefix=get_key_prefix(key)))
        headers = {"X-API-Key": key}
    db.commit()
    return user, headers


def counts(db):
    return {model.__tablename__: db.query(model).count() for model in COUNTED}


@pytest.fixture
def setup(client, db_session, tmp_path, monkeypatch):
    owner, headers = actor(db_session)
    project = Project(name="Private registration target", owner_id=owner.id, workspace_id=uuid4())
    db_session.add(project)
    db_session.commit()
    root = tmp_path / "ingest"
    root.mkdir()
    source = root / "source.md"
    source.write_text("# Confined research source")
    # raising=False lets the security regression run before the new setting exists.
    monkeypatch.setattr(settings, "onboarding_ingest_root", str(root), raising=False)
    payload = {"project_id": str(project.id), "name": "Registered source", "file_path": str(source)}
    return project, headers, payload, root


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    # Exercise real job persistence, without running the unrelated ingestion worker.
    monkeypatch.setattr(onboarding_api, "process_job", lambda _job_id: None)
    with TestClient(app) as client:
        yield client


def test_registration_denial_precedes_paths_and_cache(client, db_session, setup):
    _, owner_headers, payload, root = setup
    _, outsider = actor(db_session)
    before = counts(db_session)
    responses = []
    for file_path in (payload["file_path"], str(root / "missing"), None, "", "   "):
        response = client.post(f"{API}/documents", json={**payload, "file_path": file_path}, headers={**outsider, "Idempotency-Key": "denied"})
        assert response.status_code == 403, response.text
        responses.append(response.json())
        assert counts(db_session) == before
    assert all(body == responses[0] for body in responses)
    headers = {**owner_headers, "Idempotency-Key": "owner-registration"}
    first = client.post(f"{API}/documents", json=payload, headers=headers)
    assert first.status_code == 201, first.text
    before = counts(db_session)
    replay = client.post(f"{API}/documents", json=payload, headers={**outsider, "Idempotency-Key": "owner-registration"})
    assert replay.status_code == 403, replay.text
    assert counts(db_session) == before


@pytest.mark.parametrize("missing", [False, True])
def test_missing_or_deleted_project_precedes_path_handling(client, db_session, setup, monkeypatch, missing):
    project, owner_headers, payload, _ = setup
    _, outsider = actor(db_session)
    if missing:
        payload["project_id"] = str(uuid4())
    else:
        project.deleted_at = datetime.utcnow()
        db_session.commit()
    before = counts(db_session)
    with monkeypatch.context() as guarded:
        def forbidden_resolve(*_args, **_kwargs):
            pytest.fail("a missing/deleted project must be rejected before path resolution")
        guarded.setattr(settings, "resolve_onboarding_file", forbidden_resolve)
        for headers in (owner_headers, outsider):
            response = client.post(f"{API}/documents", json=payload, headers=headers)
            assert response.status_code == 404, response.text
    assert counts(db_session) == before


@pytest.mark.parametrize("role", ["project_owner", "admin", "owner"])
def test_registration_inherits_project_and_canonicalizes_path(client, db_session, setup, role):
    project, headers, payload, root = setup
    if role != "project_owner":
        _, headers = actor(db_session, role)
    payload["file_path"] = str(root / ".." / "ingest" / "source.md")
    response = client.post(f"{API}/documents", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    doc = db_session.get(Document, UUID(response.json()["id"]))
    assert doc.file_path == str((root / "source.md").resolve())
    assert doc.owner_id == project.owner_id
    assert doc.workspace_id == project.workspace_id


@pytest.mark.parametrize("escape", ["absolute", "traversal", "symlink", "missing-outside"])
def test_escape_never_stats_or_opens_the_external_target(client, db_session, setup, monkeypatch, escape):
    _, headers, payload, root = setup
    external = root.parent / "outside.md"
    if escape != "missing-outside":
        external.write_text("Private host file")
    if escape == "symlink":
        candidate = root / "link.md"
        candidate.symlink_to(external)
    elif escape == "traversal":
        candidate = root / ".." / external.name
    else:
        candidate = external
    before = counts(db_session)
    original_stat, original_open = Path.stat, Path.open
    def guarded_stat(path, *args, **kwargs):
        assert path != external, "external file metadata must not be read"
        return original_stat(path, *args, **kwargs)
    def guarded_open(path, *args, **kwargs):
        assert path != external, "external file must not be opened"
        return original_open(path, *args, **kwargs)
    with monkeypatch.context() as guarded:
        guarded.setattr(Path, "stat", guarded_stat)
        guarded.setattr(Path, "open", guarded_open)
        response = client.post(f"{API}/documents", json={**payload, "file_path": str(candidate)}, headers=headers)
    assert response.status_code == 400, response.text
    assert str(candidate) not in response.text
    assert counts(db_session) == before


def test_relative_ingest_root_and_internal_symlink_resolve_from_cwd(client, db_session, setup, monkeypatch):
    _, headers, payload, root = setup
    (root / "link.md").symlink_to("source.md")
    monkeypatch.chdir(root.parent)
    monkeypatch.setattr(settings, "onboarding_ingest_root", "ingest")
    response = client.post(f"{API}/documents", json={**payload, "file_path": "ingest/link.md"}, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["file_path"] == str(root / "source.md")


@pytest.mark.parametrize("kind,status", [("missing", 404), ("directory", 400), ("blank", 400), ("none", 400)])
def test_authorized_path_errors_do_not_persist(client, db_session, setup, kind, status):
    _, headers, payload, root = setup
    candidate = {"missing": str(root / "absent"), "directory": str(root), "blank": "   ", "none": None}[kind]
    before = counts(db_session)
    response = client.post(f"{API}/documents", json={**payload, "file_path": candidate}, headers=headers)
    assert response.status_code == status, response.text
    assert counts(db_session) == before


@pytest.mark.parametrize("rbac", [True, False])
@pytest.mark.parametrize("role,credential", [(role, credential) for role in ("member", "viewer", "project_owner", "admin", "owner", "service") for credential in ("jwt", "api_key")])
def test_alternate_callers_cannot_use_replay_to_gain_access(client, db_session, setup, monkeypatch, rbac, role, credential):
    """Decision #402: five actual handlers, both flags/credentials, no auth overrides."""
    project, owner_headers, payload, _ = setup
    user, headers = actor(db_session, "member" if role == "project_owner" else role, credential)
    if role == "project_owner":
        # Ownership must match the credential's actual database principal.
        project.owner_id = user.id
        owner_headers = headers
        db_session.commit()
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    registered = client.post(f"{API}/documents", json=payload, headers=owner_headers)
    assert registered.status_code == 201, registered.text
    doc_id = registered.json()["id"]
    requests = [
        ("post", f"{API}/documents", payload, 201),
        ("patch", f"{API}/projects/{project.id}", {"description": "Authorized update"}, 200),
        ("patch", f"{API}/documents/{doc_id}", {"name": "Authorized update"}, 200),
        ("post", f"{API}/jobs?document_id={doc_id}", None, 202),
        ("post", f"{API}/projects", {"name": "Original private project"}, 201),
    ]
    denied = role == "service" or (rbac and role in ("member", "viewer"))
    cells = []
    for method, path, body, success in requests:
        key = str(uuid4())
        first = client.request(method, path, json=body, headers={**owner_headers, "Idempotency-Key": key})
        assert first.status_code == success, first.text
        before = counts(db_session)
        replay = client.request(method, path, json=body, headers={**headers, "Idempotency-Key": key})
        after = counts(db_session)
        assert replay.status_code == (403 if denied else success), (role, path, replay.text)
        assert after == before, "a replay or denial must not write another resource"
        if not denied:
            assert replay.json() == first.json()
            if "/jobs?" in path:
                assert replay.headers["Location"] == first.headers["Location"]
        anonymous = client.request(method, path, json=body, headers={"Idempotency-Key": key})
        assert anonymous.status_code == 401
        assert counts(db_session) == before
        cells.append({"method": method, "path": path, "status": replay.status_code, "anonymous_status": anonymous.status_code, "row_delta": {table: after[table] - before[table] for table in before}})
    # Also prove the un-cached registration policy, including flag-off and service.
    before = counts(db_session)
    fresh = client.post(f"{API}/documents", json=payload, headers=headers)
    assert fresh.status_code == (403 if denied else 201), fresh.text
    after = counts(db_session)
    assert after["documents"] - before["documents"] == (0 if denied else 1)
    if denied:
        assert after == before
    cells.append({"method": "post", "path": f"{API}/documents", "replay": False, "status": fresh.status_code, "row_delta": {table: after[table] - before[table] for table in before}})
    if output := os.environ.get("SEC1_SWEEP_OUTPUT"):
        with Path(output).open("a") as stream:
            stream.write(json.dumps({"rbac": rbac, "role": role, "credential": credential, "cells": cells}) + "\n")


@pytest.mark.parametrize("deleted", [False, True])
def test_create_project_replay_requires_the_original_project(client, db_session, deleted):
    _, headers = actor(db_session)
    headers["Idempotency-Key"] = "original-project"
    body = {"name": "Original project"}
    first = client.post(f"{API}/projects", json=body, headers=headers)
    assert first.status_code == 201
    project = db_session.get(Project, UUID(first.json()["id"]))
    if deleted:
        project.deleted_at = datetime.utcnow()
    else:
        db_session.delete(project)
    db_session.commit()
    before = counts(db_session)
    replay = client.post(f"{API}/projects", json=body, headers=headers)
    assert replay.status_code == 404, replay.text
    assert counts(db_session) == before


def test_create_project_replay_does_not_disclose_another_owners_project(client, db_session):
    _, owner_headers = actor(db_session)
    _, outsider = actor(db_session)
    body = {"name": "Private project"}
    key = {"Idempotency-Key": "private-project"}
    first = client.post(f"{API}/projects", json=body, headers={**owner_headers, **key})
    assert first.status_code == 201
    before = counts(db_session)
    replay = client.post(f"{API}/projects", json=body, headers={**outsider, **key})
    assert replay.status_code == 403, replay.text
    assert counts(db_session) == before


@pytest.mark.parametrize("conflict", ["method", "path"])
def test_idempotency_keys_cannot_cross_method_or_path(client, db_session, setup, conflict):
    project, headers, _, _ = setup
    body = {"name": "Same payload across endpoints"}
    headers = {**headers, "Idempotency-Key": "route-bound-key"}
    if conflict == "method":
        first = client.post(f"{API}/projects", json=body, headers=headers)
        assert first.status_code == 201
        # Isolate the method mismatch from the path mismatch; it must be checked
        # before comparing the different create/update schema payload hashes.
        record = db_session.get(IdempotencyRecord, "route-bound-key")
        record.path = f"{API}/projects/{project.id}"
        db_session.commit()
    else:
        first = client.patch(f"{API}/projects/{project.id}", json=body, headers=headers)
        assert first.status_code == 200
        other = Project(name="Another authorized project", owner_id=project.owner_id)
        db_session.add(other)
        db_session.commit()
        project = other
    before = counts(db_session)
    response = client.patch(f"{API}/projects/{project.id}", json=body, headers=headers)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Idempotency key reused with different method or path"
    assert counts(db_session) == before
