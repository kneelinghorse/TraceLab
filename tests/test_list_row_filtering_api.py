"""End-to-end wiring tests for list-endpoint row-filtering (Sprint 47 T47.3).

The accessible_filter logic is unit-tested in test_accessible_filter.py; THIS suite
proves each list ENDPOINT actually applies it (gated by rbac_enabled) and — for the
cached projects list — that one tenant's filtered page is never served to another
from cache (a cache cross-tenant leak would be a breach).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import ROLE_MEMBER, ROLE_OWNER, create_access_token
from app.main import app
from app.models.collection import Collection
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.models.project import Project
from app.models.report import Report
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace

_HASH = "placeholder-not-a-real-hash"
API = settings.api_v1_prefix


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_cache():
    # The project-list cache is an in-process singleton that survives the DB reset,
    # so a prior test's scope="all" entry would otherwise bleed into the next.
    from app.services.cache_manager import get_cache_manager

    get_cache_manager().clear()
    yield


@pytest.fixture
def rbac_on(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)


def _user(db, role=ROLE_MEMBER):
    u = User(email=f"{uuid4().hex[:8]}@x.io", display_name="u", password_hash=_HASH, role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _bearer(user):
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


def _project(db, *, owner_id=None, workspace_id=None):
    p = Project(name=f"p-{uuid4().hex[:6]}", owner_id=owner_id, workspace_id=workspace_id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _project_ids(resp):
    return {row["id"] for row in resp.json()["data"]}


class TestListProjectsRowFiltering:
    def test_member_sees_only_own_projects(self, client, db_session, rbac_on):
        me = _user(db_session)
        mine = _project(db_session, owner_id=me.id)
        _theirs = _project(db_session, owner_id=uuid4())
        resp = client.get(f"{API}/projects", headers=_bearer(me))
        assert resp.status_code == 200, resp.text
        ids = _project_ids(resp)
        assert str(mine.id) in ids
        assert str(_theirs.id) not in ids

    def test_cache_does_not_leak_across_tenants(self, client, db_session, rbac_on):
        # Two members, each owning one project. If the per-scope cache key were
        # wrong, B's request could be served A's cached list.
        a = _user(db_session)
        b = _user(db_session)
        pa = _project(db_session, owner_id=a.id)
        pb = _project(db_session, owner_id=b.id)
        resp_a = client.get(f"{API}/projects", headers=_bearer(a))
        resp_b = client.get(f"{API}/projects", headers=_bearer(b))
        ids_a, ids_b = _project_ids(resp_a), _project_ids(resp_b)
        assert str(pa.id) in ids_a and str(pb.id) not in ids_a
        assert str(pb.id) in ids_b and str(pa.id) not in ids_b

    def test_privileged_owner_sees_all(self, client, db_session, rbac_on):
        owner = _user(db_session, ROLE_OWNER)
        p1 = _project(db_session, owner_id=uuid4())
        p2 = _project(db_session, owner_id=uuid4())
        resp = client.get(f"{API}/projects", headers=_bearer(owner))
        ids = _project_ids(resp)
        assert {str(p1.id), str(p2.id)} <= ids

    def test_flag_off_sees_all(self, client, db_session):
        assert settings.rbac_enabled is False
        me = _user(db_session)
        theirs = _project(db_session, owner_id=uuid4())
        resp = client.get(f"{API}/projects", headers=_bearer(me))
        assert str(theirs.id) in _project_ids(resp)  # byte-identical: no filtering


class TestListJobsRowFiltering:
    """GET /onboarding/jobs — IngestionJob governed via parent project's Space."""

    def _job_in(self, db, project):
        doc = Document(name="f.pdf", project_id=project.id, owner_id=uuid4(), workspace_id=None)
        db.add(doc)
        db.commit()
        db.refresh(doc)
        job = IngestionJob(project_id=project.id, document_id=doc.id, status="PENDING")
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def test_member_sees_only_jobs_in_their_space(self, client, db_session, rbac_on):
        me = _user(db_session)
        space = Workspace(name="S")
        db_session.add(space)
        db_session.commit()
        db_session.add(SpaceMember(workspace_id=space.id, user_id=me.id))
        db_session.commit()
        mine = self._job_in(db_session, _project(db_session, owner_id=uuid4(), workspace_id=space.id))
        hidden = self._job_in(db_session, _project(db_session, owner_id=uuid4(), workspace_id=None))

        resp = client.get("/api/v1/jobs", headers=_bearer(me))
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()}
        assert str(mine.id) in ids
        assert str(hidden.id) not in ids

    def test_flag_off_sees_all_jobs(self, client, db_session):
        assert settings.rbac_enabled is False
        me = _user(db_session)
        job = self._job_in(db_session, _project(db_session, owner_id=uuid4()))
        resp = client.get("/api/v1/jobs", headers=_bearer(me))
        assert str(job.id) in {row["id"] for row in resp.json()}


class TestListReportsRowFiltering:
    def test_member_sees_only_own_reports(self, client, db_session, rbac_on):
        me = _user(db_session)
        mine = Report(title="mine", content="c", owner_id=me.id, project_id=None)
        theirs = Report(title="theirs", content="c", owner_id=uuid4(), project_id=None)
        db_session.add_all([mine, theirs])
        db_session.commit()
        db_session.refresh(mine)
        db_session.refresh(theirs)
        resp = client.get(f"{API}/reports", headers=_bearer(me))
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()["items"]}
        assert str(mine.id) in ids
        assert str(theirs.id) not in ids


class TestListDocumentsRowFiltering:
    """Document is a child via NOT-NULL project_id — governed via parent project Space."""

    def _doc(self, db, project_id):
        d = Document(name="d.pdf", project_id=project_id, owner_id=uuid4(), workspace_id=None)
        db.add(d)
        db.commit()
        db.refresh(d)
        return d

    def test_member_sees_only_docs_in_their_space(self, client, db_session, rbac_on):
        me = _user(db_session)
        space = Workspace(name="S")
        db_session.add(space)
        db_session.commit()
        db_session.add(SpaceMember(workspace_id=space.id, user_id=me.id))
        db_session.commit()
        mine = self._doc(db_session, _project(db_session, owner_id=uuid4(), workspace_id=space.id).id)
        hidden = self._doc(db_session, _project(db_session, owner_id=uuid4(), workspace_id=None).id)
        resp = client.get(f"{API}/documents", headers=_bearer(me))
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()["data"]}
        assert str(mine.id) in ids
        assert str(hidden.id) not in ids

    def test_flag_off_sees_all_docs(self, client, db_session):
        assert settings.rbac_enabled is False
        me = _user(db_session)
        doc = self._doc(db_session, _project(db_session, owner_id=uuid4()).id)
        resp = client.get(f"{API}/documents", headers=_bearer(me))
        assert str(doc.id) in {row["id"] for row in resp.json()["data"]}


class TestListCollectionsRowFiltering:
    def test_member_sees_only_owned_collections(self, client, db_session, rbac_on):
        me = _user(db_session)
        mine = Collection(name="mine", owner_id=me.id, workspace_id=None)
        theirs = Collection(name="theirs", owner_id=uuid4(), workspace_id=None)
        db_session.add_all([mine, theirs])
        db_session.commit()
        db_session.refresh(mine)
        db_session.refresh(theirs)
        resp = client.get(f"{API}/collections", headers=_bearer(me))
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()["data"]}
        assert str(mine.id) in ids
        assert str(theirs.id) not in ids

    def test_flag_off_sees_all_collections(self, client, db_session):
        assert settings.rbac_enabled is False
        me = _user(db_session)
        coll = Collection(name="c", owner_id=uuid4(), workspace_id=None)
        db_session.add(coll)
        db_session.commit()
        db_session.refresh(coll)
        resp = client.get(f"{API}/collections", headers=_bearer(me))
        assert str(coll.id) in {row["id"] for row in resp.json()["data"]}


class TestMembershipCacheInvalidation:
    """A Space membership change must bust the cached project/document lists, else a
    revoked member keeps seeing stale rows (and a new member misses theirs) for the
    cache TTL (T47.3 review finding)."""

    def test_adding_member_to_space_busts_stale_project_list(self, client, db_session, rbac_on):
        owner = _user(db_session, ROLE_OWNER)  # to call the admin spaces API
        me = _user(db_session)
        space = Workspace(name="S")
        db_session.add(space)
        db_session.commit()
        db_session.refresh(space)
        proj = _project(db_session, owner_id=uuid4(), workspace_id=space.id)

        # Not a member yet -> sees nothing; this CACHES the empty list under scope=me.
        r1 = client.get(f"{API}/projects", headers=_bearer(me))
        assert str(proj.id) not in _project_ids(r1)

        # Admin grants membership -> must invalidate the cached list.
        add = client.post(
            f"{API}/admin/spaces/{space.id}/members",
            json={"user_id": str(me.id), "role": "member"},
            headers=_bearer(owner),
        )
        assert add.status_code == 201, add.text

        # Without invalidation the stale empty list would persist; with it, the
        # project now appears.
        r2 = client.get(f"{API}/projects", headers=_bearer(me))
        assert str(proj.id) in _project_ids(r2)
