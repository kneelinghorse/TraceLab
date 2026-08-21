"""Service credentials are confined to the explicit machine carve-outs.

The service role is deliberately not a fifth human privilege tier. These HTTP
tests use real JWT and API-key resolution and keep the seeded resources owned by
the service account, so they fail if either the central human-principal gate or
the RBAC-independent nature of that gate regresses.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import (
    ROLE_SERVICE,
    create_access_token,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
)
from app.main import app
from app.models.api_key import APIKey
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace

API = settings.api_v1_prefix
_HASH = "placeholder-not-a-real-hash"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _service_user(db) -> User:
    user = User(
        email=f"service-boundary-{uuid4().hex[:8]}@example.test",
        display_name="service-boundary",
        password_hash=_HASH,
        role=ROLE_SERVICE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(db, service: User, credential: str) -> dict[str, str]:
    if credential == "jwt":
        token = create_access_token(subject=str(service.id))
        return {"Authorization": f"Bearer {token}"}

    plain = generate_api_key()
    db.add(
        APIKey(
            user_id=service.id,
            name="Service boundary regression",
            key_hash=hash_api_key(plain),
            key_prefix=get_key_prefix(plain),
        )
    )
    db.commit()
    return {"X-API-Key": plain}


def _completed_mission_owned_by(db, service: User) -> tuple[Project, Mission]:
    workspace = Workspace(name=f"Service boundary {uuid4().hex[:8]}")
    db.add(workspace)
    db.flush()
    project = Project(
        name="Service-owned project",
        owner_id=service.id,
        workspace_id=workspace.id,
    )
    db.add(project)
    db.flush()

    claim = "The explicit service evidence route remains available."
    source_url = "https://example.test/service-boundary"
    mission = Mission(
        project_id=project.id,
        mission_id=f"SERVICE-{uuid4().hex[:8]}",
        title="Service boundary fixture",
        objective="Prove service credentials cannot cross into human routes.",
        success_criteria=["Only explicit machine routes accept the credential."],
        status="completed",
        deepsearch_job_id="ds-service-boundary-v1",
        result_markdown=claim,
        result_protocol={
            "sources_collected": [
                {
                    "url": source_url,
                    "title": "Service boundary source",
                    "alive": True,
                }
            ],
            "citations": [
                {
                    "type": "url_citation",
                    "url": source_url,
                    "start_index": 0,
                    "end_index": len(claim),
                    "live": True,
                }
            ],
        },
        execution_metadata={
            "synthesis_telemetry": {
                "tool_outcomes": {
                    "ledger_records": [],
                    "ledger_records_truncated": 0,
                }
            }
        },
        owner_id=service.id,
        workspace_id=workspace.id,
        completed_at=datetime.utcnow(),
    )
    db.add(mission)
    db.commit()
    db.refresh(project)
    db.refresh(mission)
    return project, mission


@pytest.mark.parametrize("rbac_enabled", (False, True), ids=("rbac-off", "rbac-on"))
@pytest.mark.parametrize("credential", ("jwt", "api-key"))
def test_service_credential_is_machine_only_in_every_rbac_state(
    client,
    db_session,
    monkeypatch,
    rbac_enabled,
    credential,
):
    monkeypatch.setattr(settings, "rbac_enabled", rbac_enabled)
    service = _service_user(db_session)
    headers = _headers(db_session, service, credential)
    project, mission = _completed_mission_owned_by(db_session, service)

    # Role verification is the sole non-write carve-out used at worker startup.
    profile = client.get(f"{API}/auth/me", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["role"] == ROLE_SERVICE

    # Human reads and writes are denied even though the service owns both rows.
    ordinary_requests = (
        client.get(f"{API}/projects", headers=headers),
        client.get(f"{API}/projects/{project.id}", headers=headers),
        client.get(f"{API}/missions/{mission.id}", headers=headers),
        client.post(
            f"{API}/projects",
            headers=headers,
            json={"name": "Service must not create projects"},
        ),
        client.patch(
            f"{API}/missions/{mission.id}",
            headers=headers,
            json={"title": "Service must not mutate missions"},
        ),
        client.post(
            f"{API}/evidence/capture",
            headers=headers,
            json={
                "project_id": str(project.id),
                "mission_id": str(mission.id),
                "session_key": "service-must-not-capture",
                "entries": [
                    {
                        "claim": "Caller-controlled service evidence is forbidden.",
                        "source_url": "https://example.test/forbidden",
                        "disposition": "supporting",
                    }
                ],
            },
        ),
    )
    assert [response.status_code for response in ordinary_requests] == [403] * len(ordinary_requests)

    logs = client.post(
        f"{API}/missions/{mission.id}/logs",
        headers=headers,
        json={"logs": [{"level": "INFO", "message": "trusted runner log"}]},
    )
    assert logs.status_code == 201, logs.text
    assert logs.json() == {"accepted": 1}

    evidence = client.post(
        f"{API}/missions/{mission.id}/evidence",
        headers=headers,
        json={
            "schema_version": 1,
            "deepsearch_job_id": mission.deepsearch_job_id,
        },
    )
    assert evidence.status_code == 201, evidence.text
    assert evidence.json()["status"] == "captured"


def test_evidence_openapi_documents_initial_and_replay_responses(client):
    operation = client.get("/openapi.json").json()["paths"][f"{API}/missions/{{mission_id}}/evidence"]["post"]

    assert set(operation["responses"]) >= {"200", "201", "422"}
    assert "replay" in operation["responses"]["200"]["description"].lower()


def test_raw_principal_dependency_is_limited_to_reviewed_carve_outs():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    call_sites = {
        str(path.relative_to(app_dir)): path.read_text().count("Depends(require_authenticated_principal)")
        for path in app_dir.rglob("*.py")
        if "Depends(require_authenticated_principal)" in path.read_text()
    }

    assert call_sites == {
        "api/v1/auth.py": 1,
        "api/v1/missions.py": 2,
    }
