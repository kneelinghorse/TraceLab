"""Tests for project management API endpoints (B15.7)."""

import logging
from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.schemas.project import ProjectCreate, ProjectRead, ProjectStats, ProjectUpdate


@pytest.fixture
def mock_db():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def sample_project():
    """Sample project for testing."""
    return {
        "id": str(uuid4()),
        "name": "Test Project",
        "description": "Test description",
        "research_type": "strategic",
        "methodology": "qualitative",
        "status": "active",
        "quality_score": None,
        "last_quality_check": None,
        "user_id": None,
        "mission_protocol_id": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


class TestProjectCreate:
    """Tests for POST /api/v1/projects endpoint."""

    def test_create_project_schema_validation(self):
        """Test that ProjectCreate schema accepts valid input."""
        data = ProjectCreate(
            name="My Research Project",
            description="Research on AI agents",
            research_type="strategic",
        )
        assert data.name == "My Research Project"
        assert data.description == "Research on AI agents"
        assert data.research_type == "strategic"

    def test_create_project_minimal(self):
        """Test creating project with minimal data."""
        data = ProjectCreate(name="Minimal Project")
        assert data.name == "Minimal Project"
        assert data.description is None


class TestProjectUpdate:
    """Tests for PUT /api/v1/projects/{id} endpoint."""

    def test_update_project_schema_partial(self):
        """Test that ProjectUpdate accepts partial updates."""
        data = ProjectUpdate(name="New Name")
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"name": "New Name"}

    def test_update_project_schema_full(self):
        """Test that ProjectUpdate accepts full updates."""
        data = ProjectUpdate(
            name="Updated Project",
            description="Updated description",
            status="completed",
        )
        dumped = data.model_dump(exclude_unset=True)
        assert "name" in dumped
        assert "description" in dumped
        assert "status" in dumped


class TestProjectStats:
    """Tests for GET /api/v1/projects/{id}/stats endpoint."""

    def test_project_stats_schema(self):
        """Test that ProjectStats schema works correctly."""
        stats = ProjectStats(
            project_id=uuid4(),
            name="Test Project",
            document_count=10,
            chunk_count=150,
            report_count=3,
            total_tokens=25000,
            last_updated=datetime.utcnow(),
        )
        assert stats.document_count == 10
        assert stats.chunk_count == 150
        assert stats.report_count == 3
        assert stats.total_tokens == 25000

    def test_project_stats_without_last_updated(self):
        """Test that last_updated is optional."""
        stats = ProjectStats(
            project_id=uuid4(),
            name="Test Project",
            document_count=0,
            chunk_count=0,
            report_count=0,
            total_tokens=0,
        )
        assert stats.last_updated is None

    def test_stats_are_never_served_from_another_projects_cache(self, db_session, auth_headers):
        """Stats are cached per project id, so B must never receive A's cached payload.

        Regression for the d592c92 key collision (every project shared one stats key),
        observed in production as three project ids all returning the same stats.
        """
        from fastapi.testclient import TestClient

        from app.main import app
        from app.models.project import Project

        project_a = Project(name="Stats Cache A")
        project_b = Project(name="Stats Cache B")
        db_session.add_all([project_a, project_b])
        db_session.commit()

        with TestClient(app) as client:
            first = client.get(f"/api/v1/projects/{project_a.id}/stats", headers=auth_headers)
            second = client.get(f"/api/v1/projects/{project_b.id}/stats", headers=auth_headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["project_id"] == str(project_a.id)
        assert second.json()["project_id"] == str(project_b.id)
        assert second.json()["name"] == "Stats Cache B"

    def test_project_update_invalidates_cached_stats(self, db_session, auth_headers):
        """A project rename must be visible in stats immediately, not after cache expiry."""
        from fastapi.testclient import TestClient

        from app.main import app
        from app.models.project import Project

        project = Project(name="Before Rename")
        db_session.add(project)
        db_session.commit()

        with TestClient(app) as client:
            warm = client.get(f"/api/v1/projects/{project.id}/stats", headers=auth_headers)
            assert warm.status_code == 200
            assert warm.json()["name"] == "Before Rename"

            renamed = client.put(
                f"/api/v1/projects/{project.id}",
                json={"name": "After Rename"},
                headers=auth_headers,
            )
            assert renamed.status_code == 200

            after = client.get(f"/api/v1/projects/{project.id}/stats", headers=auth_headers)

        assert after.status_code == 200
        assert after.json()["name"] == "After Rename"


class TestProjectQueryService:
    """Tests for ProjectQueryService methods."""

    def test_create_project_service(self):
        """Test project creation via service."""
        from app.services.project_query_service import ProjectQueryService

        service = ProjectQueryService()
        # Service methods exist
        assert hasattr(service, "create_project")
        assert hasattr(service, "update_project")
        assert hasattr(service, "get_project_stats")

    def test_project_stats_returns_aggregates(self):
        """Test that get_project_stats returns aggregated data."""
        from app.services.project_query_service import ProjectQueryService

        service = ProjectQueryService()
        # Method signature includes project_id parameter
        import inspect

        sig = inspect.signature(service.get_project_stats)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "project_id" in params


class TestProjectSchemaOwnership:
    """T43.4: user_id is no longer a client-settable input field."""

    def test_project_create_no_longer_accepts_user_id(self):
        assert "user_id" not in ProjectCreate.model_fields
        # An extra user_id in the payload is silently ignored, never recorded.
        data = ProjectCreate(name="x", user_id=str(uuid4()))
        assert "user_id" not in data.model_dump()

    def test_project_update_no_longer_accepts_user_id(self):
        assert "user_id" not in ProjectUpdate.model_fields
        data = ProjectUpdate(name="y", user_id=str(uuid4()))
        assert "user_id" not in data.model_dump(exclude_unset=True)

    def test_project_read_still_exposes_user_id_for_backward_compat(self):
        # Response contract is preserved (option B); the value is null for projects
        # created after T43.4. owner_id is the authoritative owner (surfaced later).
        assert "user_id" in ProjectRead.model_fields


class TestProjectOwnershipWritePath:
    """T43.4: owner_id is derived from the authenticated caller, not the body."""

    def test_create_records_owner_from_caller_and_ignores_body_user_id(self, db_session, auth_headers):
        from fastapi.testclient import TestClient

        from app.main import app
        from app.models.project import Project
        from app.models.user import User
        from app.services.ownership import bootstrap_owner_email

        seed = db_session.query(User).filter(User.email == bootstrap_owner_email()).first()
        assert seed is not None, "autouse fixture should seed the bootstrap admin"

        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/projects",
                # bogus self-asserted owner in the body — must be ignored
                json={"name": "Owned Project", "user_id": str(uuid4())},
                headers=auth_headers,
            )
        assert resp.status_code == 201, resp.text
        project_id = resp.json()["id"]

        project = db_session.query(Project).filter(Project.id == project_id).first()
        assert str(project.owner_id) == str(seed.id), "owner_id must be the authenticated caller"
        assert project.user_id is None, "client-supplied user_id must be ignored"


class TestProjectDefaultSpaceWritePath:
    """T44.4: new projects get a default Space (workspace_id) derived server-side."""

    @staticmethod
    def _seed_default_workspace(db_session):
        from app.models.workspace import DEFAULT_WORKSPACE_ID, Workspace

        # Prod seeds this via migration 030; the test DB is create_all'd and starts
        # empty, so the FK target must be created for the happy path.
        if (
            db_session.query(Workspace)
            .filter(Workspace.id == DEFAULT_WORKSPACE_ID)
            .first()
            is None
        ):
            db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Default Workspace"))
            db_session.commit()

    def test_create_assigns_default_workspace(self, db_session, auth_headers):
        from fastapi.testclient import TestClient

        from app.main import app
        from app.models.project import Project
        from app.models.workspace import DEFAULT_WORKSPACE_ID

        self._seed_default_workspace(db_session)

        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/projects",
                json={"name": "Spaced Project"},
                headers=auth_headers,
            )
        assert resp.status_code == 201, resp.text
        project_id = resp.json()["id"]

        project = db_session.query(Project).filter(Project.id == project_id).first()
        assert str(project.workspace_id) == DEFAULT_WORKSPACE_ID, (
            "new project must be assigned the Default Workspace, not left NULL"
        )

    def test_create_validates_a_client_supplied_workspace_id(self, db_session, auth_headers):
        """T44.4 made a body workspace_id something never honored; PERSONAL-2 (decision
        #533) makes it a request the route validates, never a value it trusts. A Space
        that does not exist is refused and nothing is created."""
        from fastapi.testclient import TestClient

        from app.main import app
        from app.models.project import Project

        self._seed_default_workspace(db_session)
        bogus = str(uuid4())

        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/projects",
                json={"name": "Hijack Attempt", "workspace_id": bogus},
                headers=auth_headers,
            )
        assert resp.status_code == 404, resp.text
        assert db_session.query(Project).filter(Project.name == "Hijack Attempt").count() == 0

    def test_create_degrades_to_null_when_default_workspace_absent(self, db_session):
        """No Default Workspace row -> graceful NULL Space, no FK crash (legacy
        NULL-space rows remain tolerated by the membership/inheritance path)."""
        from app.models.project import Project
        from app.services.project_query_service import ProjectQueryService

        # db_session starts empty (create_all, no seed) -> no Default Workspace.
        project = ProjectQueryService().create_project(
            db_session, ProjectCreate(name="Orphan Space"), owner_id=None
        )
        fetched = db_session.query(Project).filter(Project.id == project.id).first()
        assert fetched.workspace_id is None, "must degrade to NULL when no Default Workspace"


class TestProjectLandsInPersonalSpace:
    """PERSONAL-1 (decisions #530, #532): a human's new project lands in their own
    personal Space, so the first thing a new person does lands somewhere they own
    instead of pooling in Default Workspace, where any future Default member would
    see it. Replaces GUEST-1's sole-Space rule (decision #528, "ok for now").
    """

    @staticmethod
    def _user(db, role):
        from app.core.security import create_access_token
        from app.models.user import User

        placeholder_hash = "placeholder-not-a-real-hash"
        user = User(
            email=f"{uuid4()}@example.test",
            display_name="Guest",
            password_hash=placeholder_hash,
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user, {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}

    @staticmethod
    def _space_for(db, user, name, *, personal=False):
        from app.models.space_member import SpaceMember
        from app.models.workspace import Workspace

        space = Workspace(name=name, personal_owner_id=user.id if personal else None)
        db.add(space)
        db.commit()
        db.refresh(space)
        db.add(SpaceMember(workspace_id=space.id, user_id=user.id))
        db.commit()
        return space

    @staticmethod
    def _created_workspace(db, headers):
        from fastapi.testclient import TestClient

        from app.main import app
        from app.models.project import Project

        with TestClient(app) as client:
            resp = client.post("/api/v1/projects", json={"name": "Guest project"}, headers=headers)
        assert resp.status_code == 201, resp.text
        project = db.query(Project).filter(Project.id == resp.json()["id"]).first()
        return str(project.workspace_id)

    def test_every_human_role_creates_in_their_own_personal_space(self, db_session):
        """Derek included: "yes to both" put his own new projects in his personal Space."""
        TestProjectDefaultSpaceWritePath._seed_default_workspace(db_session)
        for role in ("owner", "admin", "member", "viewer"):
            user, headers = self._user(db_session, role)
            personal = self._space_for(db_session, user, f"{role}'s Space", personal=True)
            assert self._created_workspace(db_session, headers) == str(personal.id), role

    def test_a_shared_space_does_not_capture_the_new_project(self, db_session):
        """The GUEST-1 case: one shared Space no longer decides placement; choosing a
        shared Space is PERSONAL-2's picker, never a silent default."""
        TestProjectDefaultSpaceWritePath._seed_default_workspace(db_session)
        guest, headers = self._user(db_session, "member")
        self._space_for(db_session, guest, "Walkthrough Guest")
        personal = self._space_for(db_session, guest, "Guest's Space", personal=True)
        assert self._created_workspace(db_session, headers) == str(personal.id)

    def test_the_service_principal_and_no_caller_keep_the_default(self, db_session):
        """The route refuses a service principal outright (403), so the rule is proved
        where it lives. Even a stray personal Space row cannot pull a machine
        identity's resources out of Default; the role decides."""
        from app.core.security import AuthenticatedUser
        from app.models.workspace import DEFAULT_WORKSPACE_ID
        from app.services.ownership import default_workspace_id

        TestProjectDefaultSpaceWritePath._seed_default_workspace(db_session)
        service, _headers = self._user(db_session, "service")
        self._space_for(db_session, service, "stray", personal=True)
        caller = AuthenticatedUser(
            user_id=service.id, email=service.email, display_name="DeepSearch", role="service"
        )
        assert str(default_workspace_id(db_session, caller)) == DEFAULT_WORKSPACE_ID
        assert str(default_workspace_id(db_session)) == DEFAULT_WORKSPACE_ID

    def test_a_human_without_a_personal_space_gets_the_default_and_a_warning(
        self, db_session, caplog
    ):
        """Never a NULL Space: a missing row degrades to Default, loudly."""
        from app.models.workspace import DEFAULT_WORKSPACE_ID

        TestProjectDefaultSpaceWritePath._seed_default_workspace(db_session)
        loner, headers = self._user(db_session, "member")
        with caplog.at_level(logging.WARNING, logger="app.services.ownership"):
            assert self._created_workspace(db_session, headers) == DEFAULT_WORKSPACE_ID
        assert f"No personal Space for user {loner.id}" in caplog.text
