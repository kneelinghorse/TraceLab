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
