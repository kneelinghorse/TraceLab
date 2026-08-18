"""Per-route RBAC enforcement tests (Sprint C — T46.2).

Proves the centralized ``authorize()`` chokepoint (app/core/authorization.py) is
actually WIRED into every per-id read/write route and that its verdict surfaces
correctly through the HTTP layer:

  * 401 — unauthenticated requests are rejected on every per-id route
           (router-level ``protected_dependencies`` in app/main.py; asserted here
           so the guarantee is regression-locked per route).
  * flag ON, caller is neither owner nor Space member -> 403 (the OWASP BOLA/IDOR
           deny requirement — the whole point of Sprint C).
  * flag ON, caller is the resource owner            -> 200.
  * flag ON, caller is a member of the resource's Space -> 200 (incl. child
           project_id -> space_id inheritance for missions).
  * flag OFF -> byte-identical no-op: an authenticated non-owner/non-member is
           still allowed, exactly as before Sprint C.

The ``authorize()`` POLICY itself (owner/member/orphan/fail-closed matrix) is
exhaustively unit-tested in tests/unit/test_space_membership.py. THIS suite is
about the wiring: that each route loads the resource, calls ``authorize_or_403``
before acting, and lets the 403 propagate (NOT swallowed as a 500 by a broad
``except`` — the specific risk fixed in missions.py get/delete handlers).

DB-backed (not @pytest.mark.unit) so the autouse fixture seeds the bootstrap user.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_SERVICE,
    ROLE_VIEWER,
    create_access_token,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
)
from app.main import app
from app.models.api_key import APIKey
from app.models.collection import Collection
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.models.mission import Mission
from app.models.mission_log import MissionLog
from app.models.project import Project
from app.models.report import Report
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace

_HASH = "placeholder-not-a-real-hash"

API = settings.api_v1_prefix


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def rbac_on(monkeypatch):
    """Activate deny-by-default enforcement for the duration of a test."""
    monkeypatch.setattr(settings, "rbac_enabled", True)


# --- seed helpers -----------------------------------------------------------


def _make_user(db, email, role=ROLE_MEMBER) -> User:
    user = User(
        email=email, display_name=email.split("@")[0], password_hash=_HASH, role=role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_space(db, name="Space") -> Workspace:
    space = Workspace(name=name)
    db.add(space)
    db.commit()
    db.refresh(space)
    return space


def _grant(db, space_id, user_id) -> None:
    db.add(SpaceMember(workspace_id=space_id, user_id=user_id))
    db.commit()


def _make_project(db, *, owner_id=None, workspace_id=None, name="Proj") -> Project:
    project = Project(name=name, owner_id=owner_id, workspace_id=workspace_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _make_collection(db, *, owner_id=None, workspace_id=None, name="Coll") -> Collection:
    coll = Collection(name=name, owner_id=owner_id, workspace_id=workspace_id)
    db.add(coll)
    db.commit()
    db.refresh(coll)
    return coll


def _make_mission(db, *, owner_id=None, workspace_id=None, project_id=None) -> Mission:
    mission = Mission(
        mission_id=f"T-{uuid4().hex[:8]}",
        title="Enforcement fixture mission",
        objective="exercise authorize() wiring",
        success_criteria=["c1"],
        owner_id=owner_id,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission


def _make_report(db, *, owner_id=None, workspace_id=None, project_id=None) -> Report:
    report = Report(
        title="Enforcement fixture report",
        content="body",
        owner_id=owner_id,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _make_document(db, *, owner_id, workspace_id, project_id) -> Document:
    # Document.project_id is NOT NULL — a document can never be an orphan.
    doc = Document(
        name="fixture.pdf",
        project_id=project_id,
        owner_id=owner_id,
        workspace_id=workspace_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _bearer(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


def _api_key(db, user) -> str:
    plain = generate_api_key()
    db.add(
        APIKey(
            user_id=user.id,
            name="service-gate route test",
            key_hash=hash_api_key(plain),
            key_prefix=get_key_prefix(plain),
        )
    )
    db.commit()
    return plain


# ---------------------------------------------------------------------------
# Part A — 401: every per-id route rejects unauthenticated callers.
# ---------------------------------------------------------------------------

# (method, path) for every per-id read/write route wired in T46.2. A random UUID
# is enough: authentication is enforced before the handler ever loads a resource.
_RID = str(uuid4())
PER_ID_ROUTES = [
    ("get", f"{API}/projects/{_RID}"),
    ("put", f"{API}/projects/{_RID}"),
    ("delete", f"{API}/projects/{_RID}?confirm=true"),
    ("get", f"{API}/projects/{_RID}/stats"),
    ("post", f"{API}/projects/{_RID}/restore"),
    ("patch", f"{API}/projects/{_RID}"),  # onboarding PATCH project
    ("get", f"{API}/collections/{_RID}"),
    ("get", f"{API}/collections/{_RID}/export"),
    ("put", f"{API}/collections/{_RID}"),
    ("delete", f"{API}/collections/{_RID}"),
    ("post", f"{API}/collections/{_RID}/chunks"),
    ("delete", f"{API}/collections/{_RID}/chunks/{_RID}"),
    ("get", f"{API}/missions/{_RID}"),
    ("patch", f"{API}/missions/{_RID}"),
    ("delete", f"{API}/missions/{_RID}"),
    ("get", f"{API}/missions/{_RID}/export"),
    ("post", f"{API}/missions/{_RID}/submit"),
    ("get", f"{API}/missions/{_RID}/contract-preview"),
    ("post", f"{API}/missions/{_RID}/promote-report"),
    ("get", f"{API}/reports/{_RID}"),
    ("get", f"{API}/reports/{_RID}/export"),
    ("put", f"{API}/reports/{_RID}"),
    ("delete", f"{API}/reports/{_RID}"),
    ("post", f"{API}/documents/{_RID}/process"),
    ("get", f"{API}/documents/{_RID}"),
    ("get", f"{API}/documents/{_RID}/download"),
    ("get", f"{API}/documents/{_RID}/chunks"),
    ("delete", f"{API}/documents/{_RID}?confirm=true"),
    ("post", f"{API}/documents/{_RID}/restore"),
    ("patch", f"{API}/documents/{_RID}"),  # onboarding PATCH document
    # Adjacent mission-read routes (relationships.py / quality.py) surfaced by the
    # fail-open audit and wired to close the mission BOLA surface fully.
    ("get", f"{API}/missions/{_RID}/related"),
    ("get", f"{API}/missions/{_RID}/quality"),
    # T46.5: human-facing mission log read + ingestion jobs (governed via parent
    # Document). POST /missions/{id}/logs is the runner write path: as of T47.4 it is
    # SERVICE-GATED (authorize_service_or_403), not per-user authorized, so it is
    # excluded from this per-user matrix — its full triad (anon-401 / human-403 /
    # service-2xx) is proved by TestServiceRoleLogIngest below.
    ("get", f"{API}/missions/{_RID}/logs"),
    ("post", f"{API}/jobs?document_id={_RID}"),
    ("get", f"{API}/jobs/{_RID}"),
]


@pytest.mark.parametrize("method,path", PER_ID_ROUTES)
def test_per_id_route_requires_authentication(client, method, path):
    """No bearer token / API key -> 401 on every per-id route."""
    kwargs = {"json": {}} if method in ("put", "patch") else {}
    resp = getattr(client, method)(path, **kwargs)
    assert resp.status_code == 401, f"{method.upper()} {path} -> {resp.status_code}"


# ---------------------------------------------------------------------------
# Part B — flag ON: deny non-owner/non-member (403), allow owner/member (200).
# ---------------------------------------------------------------------------


class TestForbiddenForOutsider:
    """flag ON + authenticated member who is neither owner nor Space member -> 403.

    The resource is owned by someone else and lives in a Space the caller is not in
    (or has no Space at all), so every allow-path misses and authorize() denies.
    """

    def test_get_project_forbidden(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "out-proj@x.io")
        proj = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        resp = client.get(f"{API}/projects/{proj.id}", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_put_project_forbidden(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "out-proj-w@x.io")
        proj = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        resp = client.put(
            f"{API}/projects/{proj.id}",
            json={"description": "hijack"},
            headers=_bearer(outsider),
        )
        assert resp.status_code == 403, resp.text

    def test_get_collection_forbidden(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "out-coll@x.io")
        coll = _make_collection(db_session, owner_id=uuid4(), workspace_id=None)
        resp = client.get(f"{API}/collections/{coll.id}", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_delete_collection_forbidden(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "out-coll-w@x.io")
        coll = _make_collection(db_session, owner_id=uuid4(), workspace_id=None)
        resp = client.delete(f"{API}/collections/{coll.id}", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_get_mission_forbidden_and_not_500(self, client, db_session, rbac_on):
        """Orphan mission (project_id NULL) owned by another -> 403, NOT a 500.

        Guards the missions.py fix that adds `except HTTPException: raise` so the
        403 is not re-wrapped as 500 by the handler's broad `except Exception`.
        """
        outsider = _make_user(db_session, "out-mission@x.io")
        mission = _make_mission(db_session, owner_id=uuid4(), project_id=None)
        resp = client.get(f"{API}/missions/{mission.id}", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_delete_mission_forbidden_and_not_500(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "out-mission-w@x.io")
        mission = _make_mission(db_session, owner_id=uuid4(), project_id=None)
        resp = client.delete(f"{API}/missions/{mission.id}", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_get_report_forbidden(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "out-report@x.io")
        report = _make_report(db_session, owner_id=uuid4(), project_id=None)
        resp = client.get(f"{API}/reports/{report.id}", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_get_document_forbidden(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "out-doc@x.io")
        # Document is a child: its Space is the OWNING PROJECT's Space, not its own.
        other_space = _make_space(db_session, "doc-space")
        project = _make_project(db_session, owner_id=uuid4(), workspace_id=other_space.id)
        doc = _make_document(
            db_session, owner_id=uuid4(), workspace_id=None, project_id=project.id
        )
        resp = client.get(f"{API}/documents/{doc.id}", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text


class TestAllowedForOwner:
    """flag ON + caller IS the resource owner -> 200 via the owner_id allow-path."""

    def test_get_project_owner_ok(self, client, db_session, rbac_on):
        owner = _make_user(db_session, "own-proj@x.io")
        proj = _make_project(db_session, owner_id=owner.id, workspace_id=None)
        resp = client.get(f"{API}/projects/{proj.id}", headers=_bearer(owner))
        assert resp.status_code == 200, resp.text

    def test_get_collection_owner_ok(self, client, db_session, rbac_on):
        owner = _make_user(db_session, "own-coll@x.io")
        coll = _make_collection(db_session, owner_id=owner.id, workspace_id=None)
        resp = client.get(f"{API}/collections/{coll.id}", headers=_bearer(owner))
        assert resp.status_code == 200, resp.text

    def test_get_mission_owner_ok(self, client, db_session, rbac_on):
        owner = _make_user(db_session, "own-mission@x.io")
        mission = _make_mission(db_session, owner_id=owner.id, project_id=None)
        resp = client.get(f"{API}/missions/{mission.id}", headers=_bearer(owner))
        assert resp.status_code == 200, resp.text

    def test_get_report_owner_ok(self, client, db_session, rbac_on):
        owner = _make_user(db_session, "own-report@x.io")
        report = _make_report(db_session, owner_id=owner.id, project_id=None)
        resp = client.get(f"{API}/reports/{report.id}", headers=_bearer(owner))
        assert resp.status_code == 200, resp.text

    def test_get_document_owner_ok(self, client, db_session, rbac_on):
        owner = _make_user(db_session, "own-doc@x.io")
        project = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        doc = _make_document(
            db_session, owner_id=owner.id, workspace_id=None, project_id=project.id
        )
        resp = client.get(f"{API}/documents/{doc.id}", headers=_bearer(owner))
        assert resp.status_code == 200, resp.text


class TestAllowedForSpaceMember:
    """flag ON + caller is a member of the resource's effective Space -> 200."""

    def test_get_project_space_member_ok(self, client, db_session, rbac_on):
        member = _make_user(db_session, "mem-proj@x.io")
        space = _make_space(db_session, "proj-space")
        _grant(db_session, space.id, member.id)
        proj = _make_project(db_session, owner_id=uuid4(), workspace_id=space.id)
        resp = client.get(f"{API}/projects/{proj.id}", headers=_bearer(member))
        assert resp.status_code == 200, resp.text

    def test_get_mission_inherits_project_space_ok(self, client, db_session, rbac_on):
        """A child mission's Space is its OWNING PROJECT's Space (project_id ->
        space_id inheritance). Member of that Space is allowed."""
        member = _make_user(db_session, "mem-mission@x.io")
        space = _make_space(db_session, "mission-space")
        _grant(db_session, space.id, member.id)
        project = _make_project(db_session, owner_id=uuid4(), workspace_id=space.id)
        mission = _make_mission(
            db_session, owner_id=uuid4(), workspace_id=None, project_id=project.id
        )
        resp = client.get(f"{API}/missions/{mission.id}", headers=_bearer(member))
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Part C — flag OFF: authorization is a byte-identical no-op.
# ---------------------------------------------------------------------------


class TestAdjacentMissionReadRoutes:
    """Mission-read routes living OUTSIDE missions.py (relationships.py /related,
    quality.py /quality) — same per-id mission BOLA class, surfaced by the
    fail-open audit. flag ON: outsider -> 403, owner -> 200."""

    def test_related_forbidden_for_outsider(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "out-related@x.io")
        mission = _make_mission(db_session, owner_id=uuid4(), project_id=None)
        resp = client.get(f"{API}/missions/{mission.id}/related", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_related_ok_for_owner(self, client, db_session, rbac_on):
        # Give the mission a real project_id: RelationshipContextResponse.project_id
        # is a required UUID, so a project-less mission 500s in the service's own
        # serialization (unrelated to authz). With a project the owner clears authz
        # AND the response builds -> 200.
        owner = _make_user(db_session, "own-related@x.io")
        project = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        mission = _make_mission(
            db_session, owner_id=owner.id, project_id=project.id
        )
        resp = client.get(f"{API}/missions/{mission.id}/related", headers=_bearer(owner))
        assert resp.status_code == 200, resp.text

    def test_quality_forbidden_for_outsider(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "out-quality@x.io")
        mission = _make_mission(db_session, owner_id=uuid4(), project_id=None)
        resp = client.get(f"{API}/missions/{mission.id}/quality", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_quality_ok_for_owner(self, client, db_session, rbac_on):
        owner = _make_user(db_session, "own-quality@x.io")
        mission = _make_mission(db_session, owner_id=owner.id, project_id=None)
        resp = client.get(f"{API}/missions/{mission.id}/quality", headers=_bearer(owner))
        assert resp.status_code == 200, resp.text


class TestAuditSurfacedRoutes:
    """Routes the T46.2 fail-open audit surfaced, wired in T46.5 per the established
    patterns: GET mission logs (human read of a mission resource) and ingestion jobs
    (governed via their parent Document, since IngestionJob has no owner_id)."""

    def test_mission_logs_read_forbidden_for_outsider(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "out-logs@x.io")
        mission = _make_mission(db_session, owner_id=uuid4(), project_id=None)
        resp = client.get(f"{API}/missions/{mission.id}/logs", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_mission_logs_read_ok_for_owner(self, client, db_session, rbac_on):
        owner = _make_user(db_session, "own-logs@x.io")
        mission = _make_mission(db_session, owner_id=owner.id, project_id=None)
        resp = client.get(f"{API}/missions/{mission.id}/logs", headers=_bearer(owner))
        assert resp.status_code == 200, resp.text

    def test_mission_logs_limit_keeps_newest_window_in_chronological_order(
        self, client, db_session, rbac_on
    ):
        """A small UI limit must show the latest activity, not the oldest history."""
        owner = _make_user(db_session, "own-latest-logs@x.io")
        mission = _make_mission(db_session, owner_id=owner.id, project_id=None)
        start = datetime(2026, 8, 14, 12, 0, 0)
        for offset, message in enumerate(("oldest", "older", "newer", "newest")):
            db_session.add(
                MissionLog(
                    mission_id=mission.id,
                    level="INFO",
                    message=message,
                    logged_at=start + timedelta(minutes=offset),
                    created_at=start + timedelta(minutes=offset),
                )
            )
        db_session.commit()

        resp = client.get(
            f"{API}/missions/{mission.id}/logs?limit=2", headers=_bearer(owner)
        )

        assert resp.status_code == 200, resp.text
        assert [entry["message"] for entry in resp.json()] == ["newer", "newest"]

    def test_enqueue_job_forbidden_for_outsider(self, client, db_session, rbac_on):
        # authorize('process') on the parent Document must deny before any job is made.
        outsider = _make_user(db_session, "out-job@x.io")
        project = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        doc = _make_document(
            db_session, owner_id=uuid4(), workspace_id=None, project_id=project.id
        )
        resp = client.post(f"{API}/jobs?document_id={doc.id}", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_get_job_governed_by_parent_document(self, client, db_session, rbac_on):
        owner = _make_user(db_session, "own-job@x.io")
        outsider = _make_user(db_session, "out-job2@x.io")
        project = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        doc = _make_document(
            db_session, owner_id=owner.id, workspace_id=None, project_id=project.id
        )
        job = IngestionJob(project_id=project.id, document_id=doc.id, status="PENDING")
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)
        assert client.get(f"{API}/jobs/{job.id}", headers=_bearer(outsider)).status_code == 403
        assert client.get(f"{API}/jobs/{job.id}", headers=_bearer(owner)).status_code == 200


class TestFlagOffNoOp:
    """With rbac_enabled=False (the default) an authenticated non-owner/non-member
    is still allowed — Sprint C added enforcement behind the flag without changing
    day-one behavior. (Authentication is unchanged either way: still 401 anon.)"""

    def test_get_project_allowed_when_flag_off(self, client, db_session):
        assert settings.rbac_enabled is False
        outsider = _make_user(db_session, "off-proj@x.io")
        proj = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        resp = client.get(f"{API}/projects/{proj.id}", headers=_bearer(outsider))
        assert resp.status_code == 200, resp.text

    def test_get_mission_allowed_when_flag_off(self, client, db_session):
        assert settings.rbac_enabled is False
        outsider = _make_user(db_session, "off-mission@x.io")
        mission = _make_mission(db_session, owner_id=uuid4(), project_id=None)
        resp = client.get(f"{API}/missions/{mission.id}", headers=_bearer(outsider))
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Part D (T47.4) — POST /missions/{id}/logs is a SERVICE-gated write.
# ---------------------------------------------------------------------------

_LOG_BODY = {"logs": [{"level": "INFO", "message": "service-gate test"}]}


class TestServiceRoleLogIngest:
    """The runner log-ingest write (POST /missions/{id}/logs) is gated to a SERVICE
    principal (role 'service'), NOT per-user authorize(). This closes decision
    #260(3): with the flag ON, a human-auth token — any role, including owner —
    can no longer append/spoof logs on an arbitrary mission; only the service
    principal can. The gate respects rbac_enabled (no-op OFF) so the deployed
    runner is unaffected until the flip. Authentication is unconditional (401 anon)."""

    def test_log_ingest_requires_authentication(self, client):
        # Anon -> 401 regardless of the flag (router-level authn, flag-independent).
        resp = client.post(f"{API}/missions/{uuid4()}/logs", json=_LOG_BODY)
        assert resp.status_code == 401, resp.text

    @pytest.mark.parametrize("role", [ROLE_VIEWER, ROLE_MEMBER, ROLE_ADMIN])
    def test_log_ingest_human_jwt_forbidden(
        self, client, db_session, rbac_on, role
    ):
        human = _make_user(db_session, f"svc-{role}@x.io", role=role)
        mission = _make_mission(db_session, owner_id=uuid4(), project_id=None)
        resp = client.post(
            f"{API}/missions/{mission.id}/logs", json=_LOG_BODY, headers=_bearer(human)
        )
        assert resp.status_code == 403, resp.text

    def test_log_ingest_owner_also_forbidden(self, client, db_session, rbac_on):
        # The service gate is STRICTER than authorize(): even an owner human (who
        # would pass authorize via the privileged tier) is denied here — proving the
        # gate keys on "is a service principal", not "is privileged".
        owner = _make_user(db_session, "svc-owner@x.io", role=ROLE_OWNER)
        mission = _make_mission(db_session, owner_id=owner.id, project_id=None)
        resp = client.post(
            f"{API}/missions/{mission.id}/logs", json=_LOG_BODY, headers=_bearer(owner)
        )
        assert resp.status_code == 403, resp.text

    def test_log_ingest_service_principal_ok(self, client, db_session, rbac_on):
        service = _make_user(db_session, "svc-runner@x.io", role=ROLE_SERVICE)
        mission = _make_mission(db_session, owner_id=uuid4(), project_id=None)
        resp = client.post(
            f"{API}/missions/{mission.id}/logs", json=_LOG_BODY, headers=_bearer(service)
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["accepted"] == 1

    @pytest.mark.parametrize(
        ("role", "expected_status"),
        [
            (ROLE_VIEWER, 403),
            (ROLE_MEMBER, 403),
            (ROLE_ADMIN, 403),
            (ROLE_OWNER, 403),
            (ROLE_SERVICE, 201),
        ],
        ids=("viewer", "member", "admin", "owner", "service"),
    )
    def test_log_ingest_api_key_role_matrix(
        self, client, db_session, rbac_on, role, expected_status
    ):
        """X-API-Key preserves the strict service-only route boundary."""
        principal = _make_user(db_session, f"api-key-{role}@x.io", role=role)
        api_key = _api_key(db_session, principal)
        mission = _make_mission(db_session, owner_id=uuid4(), project_id=None)

        resp = client.post(
            f"{API}/missions/{mission.id}/logs",
            json=_LOG_BODY,
            headers={"X-API-Key": api_key},
        )

        assert resp.status_code == expected_status, resp.text
        if role == ROLE_SERVICE:
            assert resp.json()["accepted"] == 1

    def test_log_ingest_invalid_api_key_rejected(self, client, rbac_on):
        resp = client.post(
            f"{API}/missions/{uuid4()}/logs",
            json=_LOG_BODY,
            headers={"X-API-Key": "tl_" + ("x" * 32)},
        )

        assert resp.status_code == 401, resp.text

    @pytest.mark.parametrize(
        ("payload", "expected_logged_at", "expected_source"),
        [
            (
                {
                    "logs": [
                        {
                            "level": "INFO",
                            "message": "canonical payload",
                            "source": "deepsearch:running",
                            "logged_at": "2026-08-14T12:34:56Z",
                        }
                    ]
                },
                datetime(2026, 8, 14, 12, 34, 56),
                "deepsearch:running",
            ),
            (
                {
                    "entries": [
                        {
                            "level": "WARNING",
                            "message": "transitional payload",
                            "phase": "critique",
                            "ts": "2026-08-14T12:35:57Z",
                        }
                    ]
                },
                datetime(2026, 8, 14, 12, 35, 57),
                "critique",
            ),
        ],
        ids=("canonical", "deepsearch-transitional"),
    )
    def test_log_ingest_normalizes_supported_wire_shapes(
        self,
        client,
        db_session,
        rbac_on,
        payload,
        expected_logged_at,
        expected_source,
    ):
        """The receiver accepts the canonical contract during runner migration."""
        service = _make_user(db_session, f"svc-shape-{uuid4().hex[:8]}@x.io", role=ROLE_SERVICE)
        mission = _make_mission(db_session, owner_id=uuid4(), project_id=None)

        resp = client.post(
            f"{API}/missions/{mission.id}/logs",
            json=payload,
            headers=_bearer(service),
        )

        assert resp.status_code == 201, resp.text
        stored = (
            db_session.query(MissionLog)
            .filter(MissionLog.mission_id == mission.id)
            .one()
        )
        assert stored.logged_at == expected_logged_at
        assert stored.source == expected_source

    def test_log_ingest_open_when_flag_off(self, client, db_session):
        # Flip-back invariant: with the flag OFF a non-service human still succeeds,
        # so deploying this gate does NOT break the live runner before the flip.
        assert settings.rbac_enabled is False
        member = _make_user(db_session, "svc-off@x.io", role=ROLE_MEMBER)
        mission = _make_mission(db_session, owner_id=uuid4(), project_id=None)
        resp = client.post(
            f"{API}/missions/{mission.id}/logs", json=_LOG_BODY, headers=_bearer(member)
        )
        assert resp.status_code == 201, resp.text
