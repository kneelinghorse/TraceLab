"""Personal Spaces (PERSONAL-1, decisions #530 and #532).

Every human account gets a personal Space the moment it is created, by either
account route, so the first project a new person makes lands somewhere they own.
A personal Space never silently becomes shared, and it goes with its account.

DB-backed (not @pytest.mark.unit) so the autouse fixture seeds the admin that
``auth_headers`` authenticates as.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.database import engine
from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_SERVICE,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
)
from app.main import app
from app.models.api_key import APIKey
from app.models.invite_code import InviteCode
from app.models.project import Project
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import DEFAULT_WORKSPACE_ID, Workspace
from app.services.ownership import ensure_personal_space

_PLACEHOLDER_HASH = "placeholder-not-a-real-hash"
_REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _make_user(db, email, role=ROLE_MEMBER) -> User:
    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash=_PLACEHOLDER_HASH,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _personal_space(db, user_id) -> Workspace | None:
    db.expire_all()
    return db.query(Workspace).filter(Workspace.personal_owner_id == user_id).first()


def _member_ids(db, space_id) -> set:
    return {row.user_id for row in db.query(SpaceMember).filter(SpaceMember.workspace_id == space_id)}


def _seed_default_workspace(db) -> None:
    if db.query(Workspace).filter(Workspace.id == DEFAULT_WORKSPACE_ID).first() is None:
        db.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Default Workspace"))
        db.commit()


class TestCreatedWithTheAccount:
    def test_register_creates_the_personal_space_and_the_first_project_lands_there(
        self, client, db_session
    ):
        """The WALK-1 path end to end: an invited person registers, creates a
        project, and it lands in their own Space rather than Default Workspace."""
        _seed_default_workspace(db_session)
        admin = db_session.query(User).filter(User.role == ROLE_ADMIN).first()
        db_session.add(InviteCode(code="PERSONAL", created_by=admin.id))
        db_session.commit()

        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": "newcomer@example.com",
                "password": "supersecret123",
                "display_name": "Newcomer",
                "invite_code": "PERSONAL",
            },
        )
        assert registered.status_code == 201, registered.text
        user_id = registered.json()["user"]["user_id"]
        user = db_session.query(User).filter(User.email == "newcomer@example.com").one()
        space = _personal_space(db_session, user.id)
        assert space is not None
        assert space.name == "Newcomer's Space"
        assert _member_ids(db_session, space.id) == {user.id}

        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        created = client.post("/api/v1/projects", json={"name": "First project"}, headers=headers)
        assert created.status_code == 201, created.text
        assert created.json()["owner_id"] == user_id
        assert created.json()["workspace_id"] == str(space.id)

    def test_admin_created_member_gets_one_and_a_service_principal_does_not(
        self, client, db_session, auth_headers
    ):
        for email, role in (("made@example.com", ROLE_MEMBER), ("runner@example.com", ROLE_SERVICE)):
            resp = client.post(
                "/api/v1/admin/users",
                json={
                    "email": email,
                    "password": "supersecret123",
                    "display_name": "Made",
                    "role": role,
                },
                headers=auth_headers,
            )
            assert resp.status_code == 201, resp.text

        member = db_session.query(User).filter(User.email == "made@example.com").one()
        space = _personal_space(db_session, member.id)
        assert space is not None and space.name == "Made's Space"
        assert _member_ids(db_session, space.id) == {member.id}

        runner = db_session.query(User).filter(User.email == "runner@example.com").one()
        assert _personal_space(db_session, runner.id) is None
        assert db_session.query(SpaceMember).filter(SpaceMember.user_id == runner.id).count() == 0

    def test_the_helper_is_idempotent(self, db_session):
        user = _make_user(db_session, "twice@example.com")
        first = ensure_personal_space(db_session, user)
        db_session.commit()
        second = ensure_personal_space(db_session, user)
        db_session.commit()
        assert first is not None and second is not None
        assert second.id == first.id
        assert db_session.query(Workspace).filter(Workspace.personal_owner_id == user.id).count() == 1
        assert db_session.query(SpaceMember).filter(SpaceMember.user_id == user.id).count() == 1

    def test_only_the_two_account_routes_create_personal_spaces(self):
        """No lazy creation: a personal Space is made with the account or not at all,
        so a missing one is a visible fault (the logged fallback), never papered over."""
        app_dir = _REPO / "app"
        callers = sorted(
            str(path.relative_to(app_dir))
            for path in app_dir.rglob("*.py")
            if "ensure_personal_space(" in path.read_text()
            and path.name != "ownership.py"
        )
        assert callers == ["api/v1/admin_users.py", "api/v1/auth.py"]


class TestPersonalSpaceAdmin:
    def test_the_list_marks_personal_spaces(self, client, db_session, auth_headers):
        owner = _make_user(db_session, "listed@example.com")
        personal = ensure_personal_space(db_session, owner)
        shared = Workspace(name="Parts Town")
        db_session.add(shared)
        db_session.commit()

        listed = {row["id"]: row for row in client.get("/api/v1/admin/spaces", headers=auth_headers).json()}
        assert listed[str(personal.id)]["personal_owner_id"] == str(owner.id)
        assert listed[str(shared.id)]["personal_owner_id"] is None

    def test_adding_someone_else_to_a_personal_space_is_refused(self, client, db_session, auth_headers):
        """A personal Space can never silently become shared."""
        owner = _make_user(db_session, "mine@example.com")
        other = _make_user(db_session, "other@example.com")
        personal = ensure_personal_space(db_session, owner)
        db_session.commit()

        resp = client.post(
            f"/api/v1/admin/spaces/{personal.id}/members",
            json={"user_id": str(other.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert _member_ids(db_session, personal.id) == {owner.id}

    def test_the_owner_can_be_restored_to_their_own_space(self, client, db_session, auth_headers):
        """Removing the owner's row stays possible; putting it back must be too."""
        owner = _make_user(db_session, "restored@example.com")
        personal = ensure_personal_space(db_session, owner)
        db_session.commit()
        path = f"/api/v1/admin/spaces/{personal.id}/members"
        assert client.delete(f"{path}/{owner.id}", headers=auth_headers).status_code == 200
        resp = client.post(path, json={"user_id": str(owner.id)}, headers=auth_headers)
        assert resp.status_code == 201, resp.text

    def test_assigning_a_project_into_a_personal_space_stays_allowed(
        self, client, db_session, auth_headers
    ):
        owner = _make_user(db_session, "assignee@example.com")
        personal = ensure_personal_space(db_session, owner)
        project = Project(name="Handed over")
        db_session.add(project)
        db_session.commit()

        resp = client.patch(
            f"/api/v1/admin/projects/{project.id}/space",
            json={"space_id": str(personal.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["space_id"] == str(personal.id)

    def test_hard_delete_takes_the_personal_space_with_the_account(
        self, client, db_session, auth_headers
    ):
        """Postgres-style FKs on: the CASCADE from users leaves no orphan Space, and the
        account's projects survive, un-Spaced, as migration 030's SET NULL intends."""

        def _fk_on(dbapi_conn, _rec):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        event.listen(engine, "connect", _fk_on)
        engine.dispose()
        try:
            owner = _make_user(db_session, "leaving@example.com")
            personal = ensure_personal_space(db_session, owner)
            project = Project(name="Left behind", owner_id=owner.id, workspace_id=personal.id)
            db_session.add(project)
            db_session.commit()
            space_id, project_id = personal.id, project.id

            resp = client.delete(f"/api/v1/admin/users/{owner.id}", headers=auth_headers)
            assert resp.status_code == 200, resp.text
            db_session.expire_all()
            assert db_session.query(Workspace).filter(Workspace.id == space_id).first() is None
            assert db_session.query(SpaceMember).filter(SpaceMember.workspace_id == space_id).count() == 0
            survivor = db_session.query(Project).filter(Project.id == project_id).one()
            assert survivor.workspace_id is None
        finally:
            event.remove(engine, "connect", _fk_on)
            db_session.close()
            engine.dispose()


class TestMcpCreateInheritsPlacement:
    """The MCP tracelab_project create is the npm client's POST /api/v1/projects with
    an X-API-Key, so it reaches the same service and inherits the placement rule."""

    def test_the_npm_client_creates_through_post_projects(self):
        # Omitting workspace_id (PERSONAL-2 made it optional) is the X-API-Key case below.
        client_ts = _REPO / "packages" / "tracelab-mcp" / "src" / "api-client.ts"
        index_ts = _REPO / "packages" / "tracelab-mcp" / "src" / "index.ts"
        if not client_ts.exists():
            pytest.skip("npm MCP client source not present in this checkout")
        assert "this.request<Project>('POST', '/api/v1/projects', data)" in client_ts.read_text()
        handler = index_ts.read_text().split("async function handleCreateProject", 1)[1].split("\n}\n", 1)[0]
        assert "client.createProject({" in handler

    def test_an_api_key_create_lands_in_the_callers_personal_space(self, client, db_session):
        _seed_default_workspace(db_session)
        user = _make_user(db_session, "agent-user@example.com")
        personal = ensure_personal_space(db_session, user)
        plain = generate_api_key()
        db_session.add(
            APIKey(
                user_id=user.id,
                name="MCP",
                key_hash=hash_api_key(plain),
                key_prefix=get_key_prefix(plain),
            )
        )
        db_session.commit()

        resp = client.post(
            "/api/v1/projects",
            json={"name": "From an agent", "research_type": "strategic", "methodology": "mixed"},
            headers={"X-API-Key": plain},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["workspace_id"] == str(personal.id)
