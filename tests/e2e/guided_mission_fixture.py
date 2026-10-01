"""Explicit production-browser acceptance: no provider or deployed data is used.

Build/start frontend on loopback, then run:
UI_BASE=http://127.0.0.1:3100 pytest -q tests/e2e/guided_mission_fixture.py
This explicit fixture is outside default test discovery because it requires that build.
"""

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import app.api.v1.librarian as librarian_api
import app.core.authorization as authorization
import app.core.security as security
from app.core.database import get_db
from app.core.rate_limit import register_rate_limiter
from app.main import app
from app.models.invite_code import InviteCode
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace
from app.services.librarian import LibrarianService
from app.services.librarian_model import ModelReply


class PlanningModel:
    """The model seam is scripted; auth, projects, preview and saves are real."""

    model_name = "guided-browser-fixture"

    def __init__(self):
        self.turns = 0
        self.drafts = 0

    def complete(self, messages, *, tools=None, json_mode=False, max_tokens=1500):
        if json_mode:
            self.drafts += 1
            payload = {
                "mission_id": f"GUIDED-{self.drafts}",
                "title": "Compare onboarding needs",
                "objective": "Compare onboarding needs for new research teams using primary sources.",
                "success_criteria": ["Cite two primary sources", "Separate findings from uncertainty"],
                "constraints": ["Keep the report between 300 and 500 words"],
                "deliverables": ["A short evidence-backed comparison"],
                "deliverable_format": "Markdown report",
            }
        else:
            self.turns += 1
            payload = {"segments": [{"kind": "prose", "text": "Who is the audience for this research?", "citations": []}], "suggested_action": "draft_mission"}
        return ModelReply(content=json.dumps(payload), usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20})


def test_real_member_guided_planning(db_session, tmp_path, monkeypatch):
    ui = os.environ["UI_BASE"]
    assert urlparse(ui).hostname in {"localhost", "127.0.0.1"}
    monkeypatch.setattr(authorization.settings, "rbac_enabled", True)
    # Separate file-backed connections avoid sharing a SQLite transaction across
    # concurrent browser requests. The normal pytest fixture owns/reset this DB.
    engine = create_engine(db_session.get_bind().url, poolclass=NullPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def functions(connection, _record):
        connection.create_function("jsonb_array_length", 1, lambda value: len(json.loads(value)) if value else 0)

    sessions = sessionmaker(bind=engine)

    def database():
        with sessions() as session:
            yield session

    monkeypatch.setattr(security, "SessionLocal", sessions)
    app.dependency_overrides[get_db] = database
    model = PlanningModel()
    app.dependency_overrides[librarian_api.get_librarian_service] = lambda: LibrarianService(model_factory=lambda: model)
    server = None
    sock = socket.socket()
    try:
        client = TestClient(app)
        admin = db_session.query(User).filter(User.role == "admin").one()
        fixtures = []
        for index in range(12):
            code = f"GUID{index:04d}"
            db_session.add(InviteCode(code=code, created_by=admin.id))
            db_session.commit()
            register_rate_limiter.reset()
            response = client.post("/api/v1/auth/register", json={"email": f"guided{index}@example.test", "password": "test-browser-password", "display_name": f"Guided member {index}", "invite_code": code})
            assert response.status_code == 201, response.status_code
            data = response.json()
            headers = {"Authorization": f"Bearer {data['access_token']}"}
            assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "member"
            assert client.get("/api/v1/projects", headers=headers).json()["pagination"]["total"] == 0
            fixtures.append({"token": data["access_token"], **data["user"]})
        # Ephemeral test JWTs stay in pytest's private temporary directory.
        auth_file = tmp_path / "browser-auth.json"
        auth_file.write_text(json.dumps(fixtures))
        auth_file.chmod(0o600)
        sock.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, lifespan="off", access_log=False, log_level="critical"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        root = Path(__file__).resolve().parents[2]
        subprocess.run(["node", "scripts/guided-mission-live.mjs"], cwd=root / "frontend", env={**os.environ, "GUIDED_API": origin, "GUIDED_AUTH_FILE": str(auth_file)}, check=True, timeout=240)  # noqa: S603,S607
        db_session.expire_all()
        projects = db_session.query(Project).all()
        missions = db_session.query(Mission).all()
        assert len(projects) == len(missions) == 12
        for project in projects:
            user = db_session.get(User, project.owner_id)
            space = db_session.get(Workspace, project.workspace_id)
            assert user.role == "member" and space.personal_owner_id == user.id
            mission = next(item for item in missions if item.project_id == project.id)
            assert mission.status == "draft" and mission.queued_at is None and mission.started_at is None
            assert mission.created_by == "librarian"
        assert model.turns == model.drafts == 12
    finally:
        if server:
            server.should_exit = True
            thread.join(timeout=5)
        sock.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(librarian_api.get_librarian_service, None)
        engine.dispose()
