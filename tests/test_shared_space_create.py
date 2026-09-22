"""Creating inside a shared Space (PERSONAL-2, decision #533).

Without this, a member of a shared Space can only create into their personal Space
and colleagues in the shared Space never see the project. With it, a member picks
one of their own Spaces, and nobody can place a project in a Space they do not
belong to: that would push content into other people's view.

DB-backed (not @pytest.mark.unit) so the autouse fixture seeds the admin that
``auth_headers`` authenticates as.
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
    ROLE_SERVICE,
    create_access_token,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
)
from app.main import app
from app.models.api_key import APIKey
from app.models.project import Project
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import DEFAULT_WORKSPACE_ID, Workspace
from app.services.ownership import ensure_personal_space

_HASH = "placeholder-not-a-real-hash"
_REPO = pathlib.Path(__file__).resolve().parents[1]
SPACES_URL = "/api/v1/spaces"
PROJECTS_URL = "/api/v1/projects"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clear_cache():
    # The project-list cache is an in-process singleton that survives the DB reset.
    from app.services.cache_manager import get_cache_manager

    get_cache_manager().clear()
    yield


@pytest.fixture
def rbac_on(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)


def _user(db, name, role=ROLE_MEMBER, *, personal=True) -> User:
    user = User(email=f"{uuid4().hex[:8]}@example.com", display_name=name, password_hash=_HASH, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    if personal:
        ensure_personal_space(db, user)
        db.commit()
    return user


def _shared(db, name, *members) -> Workspace:
    space = Workspace(name=name)
    db.add(space)
    db.commit()
    for member in members:
        db.add(SpaceMember(workspace_id=space.id, user_id=member.id))
    db.commit()
    db.refresh(space)
    return space


def _bearer(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


def _personal_id(db, user) -> str:
    return str(db.query(Workspace).filter(Workspace.personal_owner_id == user.id).one().id)


def _seed_default(db) -> None:
    if db.query(Workspace).filter(Workspace.id == DEFAULT_WORKSPACE_ID).first() is None:
        db.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Default Workspace"))
        db.commit()


class TestListMySpaces:
    def test_a_member_sees_their_own_spaces_personal_first(self, client, db_session):
        syndy = _user(db_session, "Syndy")
        stranger = _user(db_session, "Stranger")
        parts = _shared(db_session, "Parts Town", syndy)
        _shared(db_session, "Elsewhere", stranger)

        resp = client.get(SPACES_URL, headers=_bearer(syndy))
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert [row["id"] for row in rows] == [_personal_id(db_session, syndy), str(parts.id)]
        assert rows[0]["personal_owner_id"] == str(syndy.id)
        assert rows[1]["personal_owner_id"] is None

    def test_owner_and_admin_see_every_space(self, client, db_session):
        birch = _user(db_session, "Birch", ROLE_ADMIN)
        derek = _user(db_session, "Derek", ROLE_OWNER)
        guest = _user(db_session, "Guest")
        shared = _shared(db_session, "Parts Town", guest)

        for caller in (birch, derek):
            rows = client.get(SPACES_URL, headers=_bearer(caller)).json()
            ids = [row["id"] for row in rows]
            others = {_personal_id(db_session, u) for u in (birch, derek, guest) if u is not caller}
            assert ids[0] == _personal_id(db_session, caller)
            assert str(shared.id) in ids
            assert others <= set(ids)
            # Own personal Space, then shared, then other people's personal Spaces.
            assert ids.index(str(shared.id)) < min(ids.index(space) for space in others)

    def test_a_service_principal_is_refused(self, client, db_session):
        runner = _user(db_session, "DeepSearch", ROLE_SERVICE, personal=False)
        assert client.get(SPACES_URL, headers=_bearer(runner)).status_code == 403


class TestCreateInASpace:
    def test_a_member_creates_in_a_shared_space_and_a_colleague_sees_it(
        self, client, db_session, rbac_on
    ):
        """Derek's reason for PERSONAL-2: colleagues in the shared Space see the project."""
        syndy = _user(db_session, "Syndy")
        colleague = _user(db_session, "Colleague")
        outsider = _user(db_session, "Outsider")
        parts = _shared(db_session, "Parts Town", syndy, colleague)

        created = client.post(
            PROJECTS_URL,
            json={"name": "Catalog audit", "workspace_id": str(parts.id)},
            headers=_bearer(syndy),
        )
        assert created.status_code == 201, created.text
        assert created.json()["workspace_id"] == str(parts.id)
        assert created.json()["owner_id"] == str(syndy.id)

        def listed(user):
            resp = client.get(f"{PROJECTS_URL}?page_size=100", headers=_bearer(user))
            assert resp.status_code == 200, resp.text
            return {row["id"] for row in resp.json()["data"]}

        assert created.json()["id"] in listed(colleague)
        assert created.json()["id"] not in listed(outsider)

    def test_a_non_member_cannot_place_a_project_in_someone_elses_space(self, client, db_session):
        member = _user(db_session, "Member")
        other = _user(db_session, "Other")
        theirs = _shared(db_session, "Theirs", other)
        before = db_session.query(Project).count()

        for target in (str(theirs.id), _personal_id(db_session, other), str(uuid4())):
            resp = client.post(
                PROJECTS_URL,
                json={"name": "Pushed in", "workspace_id": target},
                headers=_bearer(member),
            )
            # 403 whether or not the Space exists, so ids cannot be probed.
            assert resp.status_code == 403, (target, resp.text)
        assert db_session.query(Project).count() == before

    def test_owner_and_admin_may_name_any_existing_space(self, client, db_session):
        derek = _user(db_session, "Derek", ROLE_OWNER)
        birch = _user(db_session, "Birch", ROLE_ADMIN)
        guest = _user(db_session, "Guest")
        target = _personal_id(db_session, guest)

        for caller in (derek, birch):
            resp = client.post(
                PROJECTS_URL,
                json={"name": "Handed over", "workspace_id": target},
                headers=_bearer(caller),
            )
            assert resp.status_code == 201, resp.text
            assert resp.json()["workspace_id"] == target
            missing = client.post(
                PROJECTS_URL,
                json={"name": "Nowhere", "workspace_id": str(uuid4())},
                headers=_bearer(caller),
            )
            assert missing.status_code == 404, missing.text

    def test_absent_means_the_personal_space_and_owner_id_is_never_taken_from_the_body(
        self, client, db_session
    ):
        _seed_default(db_session)
        member = _user(db_session, "Member")
        someone = _user(db_session, "Someone")
        resp = client.post(
            PROJECTS_URL,
            json={"name": "Mine", "owner_id": str(someone.id)},
            headers=_bearer(member),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["owner_id"] == str(member.id)
        assert resp.json()["workspace_id"] == _personal_id(db_session, member)


class TestMcpCreateInASpace:
    """tracelab_project create sends POST /api/v1/projects with an X-API-Key; the
    optional workspace_id goes through the same route check as the UI's picker."""

    def test_the_npm_client_passes_workspace_id_through(self):
        index_ts = _REPO / "packages" / "tracelab-mcp" / "src" / "index.ts"
        if not index_ts.exists():
            pytest.skip("npm MCP client source not present in this checkout")
        source = index_ts.read_text()
        handler = source.split("async function handleCreateProject", 1)[1].split("\n}\n", 1)[0]
        assert "workspace_id: input.workspace_id" in handler
        schema = source.split("const CreateProjectInput = z.object({", 1)[1].split("});", 1)[0]
        assert "workspace_id: z.string().uuid().optional()" in schema

    def test_an_api_key_create_is_held_to_membership(self, client, db_session):
        member = _user(db_session, "Agent owner")
        other = _user(db_session, "Other")
        mine = _shared(db_session, "Mine", member)
        theirs = _shared(db_session, "Theirs", other)
        plain = generate_api_key()
        db_session.add(
            APIKey(user_id=member.id, name="MCP", key_hash=hash_api_key(plain), key_prefix=get_key_prefix(plain))
        )
        db_session.commit()
        headers = {"X-API-Key": plain}

        ok = client.post(PROJECTS_URL, json={"name": "From an agent", "workspace_id": str(mine.id)}, headers=headers)
        assert ok.status_code == 201, ok.text
        assert ok.json()["workspace_id"] == str(mine.id)
        refused = client.post(
            PROJECTS_URL, json={"name": "Pushed in", "workspace_id": str(theirs.id)}, headers=headers
        )
        assert refused.status_code == 403, refused.text
