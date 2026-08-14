"""Owner/workspace parity on document & collection create (Sprint 48 T48.4).

Before T48.4 every document/collection create minted NULL owner_id, so the row was
invisible to its own creator the instant rbac_enabled flipped. These tests pin:
- a MEMBER who creates a collection/document sees it in the scoped list (owner_id=caller);
- background-created docs inherit their PARENT PROJECT's owner/Space (the widened cut).

DB-backed; the autouse fixture seeds the admin bootstrap user.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import ROLE_MEMBER, create_access_token
from app.main import app
from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
from app.models.user import User
from app.schemas.mission import MissionCreate
from app.services.auto_ingest import AutoIngestService
from app.services.auto_report import create_report_from_protocol
from app.services.document_ingestion import DocumentIngestionService
from app.services.mission_service import MissionService
from app.services.ownership import project_owner_workspace
from app.services.report_promotion import ReportPromotionService

_PLACEHOLDER_HASH = "placeholder-not-a-real-hash"
COLLECTIONS_URL = "/api/v1/collections"
DOCUMENTS_URL = "/api/v1/documents"
REPORTS_URL = "/api/v1/reports"
# Onboarding's POST register-document is mounted at {api_v1_prefix}/documents.
ONBOARDING_DOCUMENTS_URL = "/api/v1/documents"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def rbac_on(monkeypatch):
    # accessible_filter() reads settings.rbac_enabled live, so flipping it here
    # exercises the real scoped-list path a non-privileged caller hits in prod.
    monkeypatch.setattr(settings, "rbac_enabled", True)


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


def _bearer(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


def _make_project(db, *, owner_id=None, workspace_id=None, name="Proj") -> Project:
    project = Project(name=name, owner_id=owner_id, workspace_id=workspace_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _make_mission(db, project, *, result_markdown=None) -> Mission:
    mission = Mission(
        project_id=project.id,
        mission_id=f"T48-{uuid4().hex[:8]}",
        title="Parity Test Mission",
        objective="owner/workspace inheritance wiring",
        success_criteria=["c"],
        status="completed",
        result_markdown=result_markdown,
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission


def _mock_ingestion() -> DocumentIngestionService:
    # Background create sites run the new doc through chunking/embedding after the
    # Document() construction; stub that so these tests pin ONLY the owner/Space wiring.
    return MagicMock(
        spec=DocumentIngestionService,
        process_document=MagicMock(return_value={"status": "completed"}),
    )


class TestUserFacingCreateVisibility:
    def test_member_sees_own_collection_in_scoped_list(self, client, db_session, rbac_on):
        member = _make_user(db_session, "coll-member@example.com")
        created = client.post(COLLECTIONS_URL, json={"name": "Mine"}, headers=_bearer(member))
        assert created.status_code == 201, created.text

        listed = client.get(COLLECTIONS_URL, headers=_bearer(member))
        assert listed.status_code == 200, listed.text
        names = [c["name"] for c in listed.json()["data"]]
        assert "Mine" in names, "member cannot see the collection they just created"

    def test_member_sees_own_uploaded_document_in_scoped_list(self, client, db_session, rbac_on):
        member = _make_user(db_session, "doc-member@example.com")
        project = _make_project(db_session, owner_id=member.id)

        files = {"file": ("notes.md", b"# hello world", "text/markdown")}
        up = client.post(
            f"{DOCUMENTS_URL}/upload?project_id={project.id}",
            files=files,
            headers=_bearer(member),
        )
        assert up.status_code == 200, up.text
        doc_id = up.json()["id"]

        listed = client.get(f"{DOCUMENTS_URL}?project_id={project.id}", headers=_bearer(member))
        assert listed.status_code == 200, listed.text
        assert doc_id in listed.text, "member cannot see the document they just uploaded"

        # Direct assertion (review hardening): the member is in NO Space, so
        # accessible_filter's project/Space branch never fires — visibility here comes
        # SOLELY from the document's own owner_id. Pin that explicitly so the test
        # can't silently pass on a different axis if the filter logic ever changes.
        persisted = db_session.query(Document).filter(Document.project_id == project.id).first()
        assert persisted is not None
        assert str(persisted.owner_id) == str(member.id), "upload did not stamp owner_id=caller"

    def test_upload_requires_authentication(self, client, db_session, rbac_on):
        # The route gained a handler-level current_user (T48.4) to attribute owner_id.
        project = _make_project(db_session)
        files = {"file": ("notes.md", b"# hi", "text/markdown")}
        resp = client.post(f"{DOCUMENTS_URL}/upload?project_id={project.id}", files=files)
        assert resp.status_code == 401, resp.text

    def test_member_sees_own_report_created_without_project(self, client, db_session, rbac_on):
        # The genuine live bug T48.4's parity left open for reports: a report created
        # WITHOUT a project has NO Space-inheritance fallback, so owner_id is the only
        # non-admin access path. Before the fix POST /reports minted NULL owner → the
        # creator 201'd a report they could not then see. Synthesis is stubbed so the
        # test pins ONLY the owner attribution, not the LLM path.
        from app.services.report_service import ReportService, get_report_service

        member = _make_user(db_session, "report-member@example.com")
        mock_synth = MagicMock()
        mock_synth.synthesize.return_value = {
            "content": "synthesized body [1]",
            "citations": [],
            "tokens_used": 1,
            "chunk_count": 1,
        }
        app.dependency_overrides[get_report_service] = lambda: ReportService(
            synthesis_service=mock_synth
        )
        try:
            created = client.post(
                REPORTS_URL,
                json={"title": "Mine", "chunk_ids": [str(uuid4())]},  # no project_id
                headers=_bearer(member),
            )
            assert created.status_code == 201, created.text
            report_id = created.json()["id"]
        finally:
            app.dependency_overrides.pop(get_report_service, None)

        listed = client.get(REPORTS_URL, headers=_bearer(member))
        assert listed.status_code == 200, listed.text
        assert report_id in listed.text, "member cannot see the project-less report they just created"

        persisted = db_session.query(Report).filter(Report.title == "Mine").first()
        assert persisted is not None
        assert persisted.project_id is None, "this test must exercise the NULL-project case"
        assert str(persisted.owner_id) == str(member.id), "create_report did not stamp owner_id=caller"


class TestBackgroundParentProjectAttribution:
    """The widened cut: background create sites (auto_ingest, report_promotion,
    onboarding) attribute owner/Space from the parent project via this helper."""

    def test_helper_returns_parent_project_owner_and_workspace(self, db_session):
        owner = _make_user(db_session, "proj-owner@example.com")
        ws_id = uuid4()
        project = _make_project(db_session, owner_id=owner.id, workspace_id=ws_id)
        assert project_owner_workspace(db_session, project.id) == (owner.id, ws_id)

    def test_helper_fails_safe_for_missing_or_null_project(self, db_session):
        assert project_owner_workspace(db_session, None) == (None, None)
        assert project_owner_workspace(db_session, uuid4()) == (None, None)


class TestBackgroundSiteWiring:
    """HIGH review finding (wf_81973711): the background create sites were tested only
    via the helper in isolation — no test drove a REAL create path and asserted the
    persisted Document carried the inherited owner/Space, so a dropped assignment would
    pass green. These drive each site end-to-end; the ingestion pipeline is stubbed so
    only the owner/Space wiring is under test."""

    def test_mission_service_inherits_project_owner_and_workspace(self, db_session):
        owner = _make_user(db_session, "mission-owner@example.com")
        ws_id = uuid4()
        project = _make_project(db_session, owner_id=owner.id, workspace_id=ws_id)

        mission = MissionService().create_mission(
            db_session,
            MissionCreate(
                project_id=project.id,
                mission_id="T48.8-owner-parity",
                title="Mission ownership parity",
                objective="Inherit ownership from the required parent project.",
                success_criteria=["Mission ownership matches its project."],
            ),
        )

        assert str(mission.owner_id) == str(owner.id)
        assert str(mission.workspace_id) == str(ws_id)

    def test_auto_report_inherits_project_owner_and_workspace(self, db_session):
        owner = _make_user(db_session, "auto-report-owner@example.com")
        ws_id = uuid4()
        project = _make_project(db_session, owner_id=owner.id, workspace_id=ws_id)
        mission = _make_mission(db_session, project)

        report = create_report_from_protocol(
            db_session,
            mission,
            {"synthesis": "Ownership follows the parent project."},
        )

        assert str(report.owner_id) == str(owner.id)
        assert str(report.workspace_id) == str(ws_id)

    def test_auto_ingest_inherits_project_owner_and_workspace(self, db_session):
        owner = _make_user(db_session, "ai-owner@example.com")
        ws_id = uuid4()
        project = _make_project(db_session, owner_id=owner.id, workspace_id=ws_id)
        mission = _make_mission(db_session, project)

        svc = AutoIngestService(ingestion_service=_mock_ingestion())
        doc = svc.auto_ingest_result(db=db_session, mission=mission, result_markdown="# result")

        assert str(doc.owner_id) == str(owner.id)
        assert str(doc.workspace_id) == str(ws_id)

    def test_promote_report_inherits_project_owner_and_workspace(self, db_session):
        owner = _make_user(db_session, "pr-owner@example.com")
        ws_id = uuid4()
        project = _make_project(db_session, owner_id=owner.id, workspace_id=ws_id)
        report = Report(title="src", content="# body", project_id=project.id)
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)
        mission = _make_mission(db_session, project)

        svc = ReportPromotionService(ingestion_service=_mock_ingestion())
        doc = svc.promote_report(db_session, mission, report)

        assert str(doc.owner_id) == str(owner.id)
        assert str(doc.workspace_id) == str(ws_id)

    def test_promote_markdown_inherits_project_owner_and_workspace(self, db_session):
        owner = _make_user(db_session, "pm-owner@example.com")
        ws_id = uuid4()
        project = _make_project(db_session, owner_id=owner.id, workspace_id=ws_id)
        mission = _make_mission(db_session, project, result_markdown="# markdown body")

        svc = ReportPromotionService(ingestion_service=_mock_ingestion())
        doc = svc.promote_markdown(db_session, mission)

        assert str(doc.owner_id) == str(owner.id)
        assert str(doc.workspace_id) == str(ws_id)

    def test_onboarding_register_inherits_project_owner_and_workspace(
        self, client, db_session, tmp_path
    ):
        # onboarding sets owner/Space directly from the parent project (not the helper);
        # drive the real route with a temp file and assert the persisted row inherits.
        owner = _make_user(db_session, "onb-owner@example.com")
        ws_id = uuid4()
        project = _make_project(db_session, owner_id=owner.id, workspace_id=ws_id)
        f = tmp_path / "reg.md"
        f.write_text("# hello")

        resp = client.post(
            ONBOARDING_DOCUMENTS_URL,
            json={
                "project_id": str(project.id),
                "name": "reg.md",
                "file_path": str(f),
                "file_type": "report",
            },
            headers=_bearer(owner),
        )
        assert resp.status_code == 201, resp.text

        persisted = db_session.query(Document).filter(Document.name == "reg.md").first()
        assert persisted is not None
        assert str(persisted.owner_id) == str(owner.id)
        assert str(persisted.workspace_id) == str(ws_id)
