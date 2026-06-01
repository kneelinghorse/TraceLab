"""T46.6 — rbac_enabled flip-safety regression (Sprint C culmination).

The flip is ENV-DRIVEN: set RBAC_ENABLED=true in the deploy env (pydantic Settings
reads it). The code default stays False so dev/CI/local are byte-identical and the
flip is reversible. This suite proves the holistic guarantees that make flipping ON
safe — asserted with the flag monkeypatched ON unless a test says otherwise:

  * the OWNER is never locked out (owner role reaches a resource it doesn't own)
  * the admin tier is unaffected
  * a bootstrapped owner (bootstrap-owner-FIRST) has full access
  * existing users keep access via Space membership
  * cross-user access is denied (BOLA/IDOR closed)
  * an orphan mission (project_id NULL) is owner+admin only (fail-closed)
  * a disabled user is blocked
  * MCP + webhook trusted-origin paths CANNOT be gated by the flag (structural)
  * the service-write carve-out (POST .../logs) is explicit + cannot silently widen (T47.4)
  * flipping back to False is a clean no-op (same request: 403 ON -> 200 OFF)
"""

from __future__ import annotations

import pathlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    create_access_token,
)
from app.main import app
from app.models.mission import Mission
from app.models.project import Project
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace
from app.services.ownership import bootstrap_owner_email, ensure_owner_bootstrap

_HASH = "placeholder-not-a-real-hash"
API = settings.api_v1_prefix


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def rbac_on(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)


def _make_user(db, email, role=ROLE_MEMBER) -> User:
    u = User(email=email, display_name=email.split("@")[0], password_hash=_HASH, role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_project(db, *, owner_id=None, workspace_id=None) -> Project:
    p = Project(name="p", owner_id=owner_id, workspace_id=workspace_id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_space(db) -> Workspace:
    w = Workspace(name="space")
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


def _grant(db, space_id, user_id) -> None:
    db.add(SpaceMember(workspace_id=space_id, user_id=user_id))
    db.commit()


def _make_mission(db, *, owner_id=None, project_id=None) -> Mission:
    m = Mission(
        mission_id=f"T-{uuid4().hex[:8]}",
        title="flip-regression fixture mission",
        objective="o",
        success_criteria=["c"],
        owner_id=owner_id,
        project_id=project_id,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _bearer(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


class TestOwnerNeverLockedOut:
    def test_owner_role_reaches_a_project_it_does_not_own(self, client, db_session, rbac_on):
        owner = _make_user(db_session, "global-owner@x.io", ROLE_OWNER)
        someone_elses = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        resp = client.get(f"{API}/projects/{someone_elses.id}", headers=_bearer(owner))
        assert resp.status_code == 200, resp.text

    def test_admin_tier_unaffected(self, client, db_session, rbac_on):
        admin = _make_user(db_session, "an-admin@x.io", ROLE_ADMIN)
        someone_elses = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        resp = client.get(f"{API}/projects/{someone_elses.id}", headers=_bearer(admin))
        assert resp.status_code == 200, resp.text

    def test_bootstrapped_owner_has_access(self, client, db_session, rbac_on):
        # bootstrap-owner-FIRST: promote the seed user, then prove it can administer.
        assert ensure_owner_bootstrap(db_session) is True
        owner = db_session.query(User).filter(User.email == bootstrap_owner_email()).first()
        assert owner is not None and owner.role == ROLE_OWNER
        someone_elses = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        resp = client.get(f"{API}/projects/{someone_elses.id}", headers=_bearer(owner))
        assert resp.status_code == 200, resp.text


class TestEnforcementWhenOn:
    def test_existing_user_keeps_access_via_space_membership(self, client, db_session, rbac_on):
        member = _make_user(db_session, "member-keeps@x.io")
        space = _make_space(db_session)
        _grant(db_session, space.id, member.id)
        project = _make_project(db_session, owner_id=uuid4(), workspace_id=space.id)
        resp = client.get(f"{API}/projects/{project.id}", headers=_bearer(member))
        assert resp.status_code == 200, resp.text

    def test_cross_user_access_denied(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "cross-user@x.io")
        project = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        resp = client.get(f"{API}/projects/{project.id}", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_orphan_mission_is_owner_admin_only(self, client, db_session, rbac_on):
        outsider = _make_user(db_session, "orphan-outsider@x.io")
        orphan = _make_mission(db_session, owner_id=uuid4(), project_id=None)
        resp = client.get(f"{API}/missions/{orphan.id}", headers=_bearer(outsider))
        assert resp.status_code == 403, resp.text

    def test_disabled_user_blocked(self, client, db_session, rbac_on):
        user = _make_user(db_session, "disabled-flip@x.io")
        headers = _bearer(user)
        user.is_active = False
        db_session.commit()
        resp = client.get(f"{API}/auth/me", headers=headers)
        assert resp.status_code == 403, resp.text


class TestTrustedOriginPathsUnaffected:
    def test_mcp_and_webhooks_never_call_authorize(self):
        # If a trusted-origin path called authorize(), the flag WOULD gate it. Prove
        # they don't — so flipping rbac_enabled cannot change MCP/webhook behavior.
        app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
        targets = list((app_dir / "mcp_server").rglob("*.py"))
        targets.append(app_dir / "api" / "v1" / "webhooks.py")
        offenders = [
            str(p)
            for p in targets
            if "authorize_or_403" in p.read_text() or "authorize(" in p.read_text()
        ]
        assert offenders == [], f"trusted-origin path calls authorize(): {offenders}"


class TestServiceCarveOutBoundary:
    """T47.4 — the service-write carve-out must stay EXPLICIT and cannot silently
    widen. POST /missions/{id}/logs is the ONE service-gated write today; any new
    service-gated write (or any other change that moves the gate) must be a
    conscious, reviewed change recorded here + in docs/authentication.md, never an
    accident. This is the "future cross-resource service write" guard the mission
    asks for, plus coverage of the published npm MCP client (the real production MCP
    surface — the in-repo app/mcp_server is production-dark)."""

    _APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"
    _REPO_DIR = pathlib.Path(__file__).resolve().parents[1]

    def test_service_gate_used_in_exactly_the_known_places(self):
        # The whole app must CALL authorize_service_or_403() in exactly one file
        # (the mission log-ingest write). A new call anywhere is a widened service
        # carve-out and fails here until it is added to this allowlist + documented.
        hits = sorted(
            str(p.relative_to(self._APP_DIR))
            for p in self._APP_DIR.rglob("*.py")
            if "authorize_service_or_403(" in p.read_text()
        )
        # core/authorization.py holds the DEFINITION (not a carve-out); exclude it.
        call_sites = [h for h in hits if not h.endswith("core/authorization.py")]
        assert call_sites == ["api/v1/missions.py"], (
            f"service-write carve-out widened or moved: {call_sites}. When you add a "
            f"service-gated write, update this allowlist AND docs/authentication.md."
        )

    def test_log_ingest_is_service_gated(self):
        # Positive: the log-ingest handler actually invokes the service gate.
        missions = (self._APP_DIR / "api" / "v1" / "missions.py").read_text()
        assert "authorize_service_or_403(user)" in missions

    def test_npm_mcp_client_authenticates_every_request(self):
        # The published MCP surface is the npm TS client; guard that it can never
        # silently become an unauthenticated caller. Assert STRUCTURALLY (not mere
        # whole-file substring presence, which stays green even if a request path
        # drops its auth): the credential is injected in the constructor, the shared
        # request() helper forwards it, the one bypass path (uploadDocument) re-copies
        # it, and NO new unguarded fetch() site has appeared. (Runtime credential
        # presence is additionally covered by the package's own vitest suite.)
        client_ts = self._REPO_DIR / "packages" / "tracelab-mcp" / "src" / "api-client.ts"
        if not client_ts.exists():
            pytest.skip("npm MCP client source not present in this checkout")
        src = client_ts.read_text()
        # 1. constructor injects the credential header (Bearer JWT or X-API-Key)
        assert "Bearer ${config.token}" in src, "lost the Bearer-JWT credential path"
        assert "this.headers['X-API-Key'] = config.apiKey" in src, "lost the API-key path"
        # 2. the shared request() helper forwards the credentialed headers
        assert "headers: this.headers" in src, "request() no longer forwards auth headers"
        # 3. the one fetch() that bypasses request() (uploadDocument) re-copies auth
        assert "headers['Authorization'] = this.headers['Authorization']" in src, (
            "uploadDocument's bypass fetch dropped its Authorization header"
        )
        # 4. no NEW unguarded request path: exactly the two known fetch() sites
        #    (request() + uploadDocument). A third fetch must be confirmed to
        #    authenticate, then this count updated — the client-side widening guard.
        n = src.count("fetch(")
        assert n == 2, (
            f"unexpected fetch() count ({n}) in api-client.ts — a new request path "
            f"must be confirmed to authenticate, then update this guard."
        )


class TestFlipBackIsCleanNoop:
    def test_same_request_403_when_on_200_when_off(self, client, db_session, monkeypatch):
        outsider = _make_user(db_session, "rollback@x.io")
        project = _make_project(db_session, owner_id=uuid4(), workspace_id=None)
        url = f"{API}/projects/{project.id}"

        monkeypatch.setattr(settings, "rbac_enabled", True)
        assert client.get(url, headers=_bearer(outsider)).status_code == 403

        # Rollback: flipping the flag back OFF restores byte-identical pre-Sprint-C
        # behaviour with no code change — the deny-by-default policy short-circuits.
        monkeypatch.setattr(settings, "rbac_enabled", False)
        assert client.get(url, headers=_bearer(outsider)).status_code == 200
