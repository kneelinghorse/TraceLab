"""Authored scope survives real REST persistence and Python MCP serialization."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mcp_server.tools.missions import _serialize_mission
from app.models.mission import Mission

FIXTURE = Path(__file__).parent / "fixtures/authored_scope_v1"


@pytest.fixture
def client(auth_headers):
    return TestClient(app, headers=auth_headers)


def test_canonical_authoring_create_read_preview_and_explicit_clear(client, project, db_session):
    authored = json.loads((FIXTURE / "postgresql-authored.json").read_text())
    authored["project_id"] = str(project.id)
    created = client.post("/api/v1/missions", json=authored)
    assert created.status_code == 201, created.text
    mission = created.json()
    url = f"/api/v1/missions/{mission['id']}"
    preview = client.get(url + "/contract-preview")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["canonical_contract_id"] == "8ca1ebfaa604dc7e"
    assert body["canonical_contract_sha256"] == "163e7af36080b8440afe55f501b023cb2e3aba84e1b8644298fc0784167b5cb6"
    assert body["compiler_semantic_revision"] == 3
    assert body["authored_scope"]["max_sources"] == 2
    assert client.get(url).json()["status"] == "draft"
    # Explicit empty values must clear legacy fallback on every read surface.
    context = {"authored_scope": {"max_words": 400}, "constraints": ["at most 350 words"], "unrelated": {"keep": True}}
    update = client.patch(url, json={"context": context, "constraints": [], "references": []})
    assert update.status_code == 200, update.text
    assert update.json()["context"] == context
    assert update.json()["constraints"] == []
    changed = client.get(url + "/contract-preview").json()
    # Original authored 300-500 words intersects with the structured 400 max.
    assert changed["authored_scope"]["max_words"] == 400
    assert changed["canonical_contract_id"] != body["canonical_contract_id"]
    stored = db_session.get(Mission, uuid.UUID(mission["id"]))
    db_session.refresh(stored)
    serialized = _serialize_mission(stored, slim=False)
    assert serialized["context"] == context
    assert serialized["references"] == []
    assert serialized["constraints"] == []
    cleared = client.patch(url, json={"context": None, "references": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["context"] in (None, {})


def test_invalid_authored_scope_fails_preview_without_dispatch(client, project):
    payload = json.loads((FIXTURE / "postgresql-authored.json").read_text())
    payload.update(project_id=str(project.id), context={"authored_scope": {"max_words": 200, "min_words": 500}})
    created = client.post("/api/v1/missions", json=payload)
    assert created.status_code == 201, created.text
    url = f"/api/v1/missions/{created.json()['id']}"
    response = client.get(url + "/contract-preview")
    assert response.status_code == 422, response.text
    assert "min_words" in response.text
    assert client.get(url).json()["status"] == "draft"


def test_scoped_preview_member_access_and_denied_project(client, project, db_session, monkeypatch):
    import app.core.authorization as authorization
    from app.core.security import AuthenticatedUser, require_authenticated_user
    from app.models.user import User

    owner = db_session.query(User).first()
    project.owner_id = owner.id
    db_session.commit()
    monkeypatch.setattr(authorization.settings, "rbac_enabled", True)
    member = AuthenticatedUser(user_id=owner.id, email=owner.email, display_name="Member", role="member")
    app.dependency_overrides[require_authenticated_user] = lambda: member
    try:
        payload = json.loads((FIXTURE / "postgresql-authored.json").read_text())
        payload["project_id"] = str(project.id)
        response = client.post("/api/v1/missions", json=payload)
        assert response.status_code == 201, response.text
        url = f"/api/v1/missions/{response.json()['id']}"
        assert client.get(url + "/contract-preview").status_code == 200
        stranger = AuthenticatedUser(user_id=uuid.uuid4(), email="stranger@example.test", display_name="Stranger", role="member")
        app.dependency_overrides[require_authenticated_user] = lambda: stranger
        assert client.get(url).status_code == 403
        assert client.get(url + "/contract-preview").status_code == 403
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)
