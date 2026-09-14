"""Unit tests for authorization.accessible_filter — the query-level row filter that
closes the cross-tenant list read-leak (Sprint 47 T47.3).

It must mirror authorize()'s read policy exactly, but as a SQLAlchemy filter applied
inside the list query (so pagination is correct). Covered: flag-off + privileged ->
no filter (all rows); non-privileged sees only own + Space-member rows; orphan child
fail-closed; child governed via the OWNING project's Space; a model with no owner_id
and no resolvable Space (governed via parent project_id) — IngestionJob.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from app.core.authorization import accessible_filter
from app.core.config import settings
from app.core.security import ROLE_ADMIN, ROLE_MEMBER, ROLE_OWNER, ROLE_SERVICE, AuthenticatedUser
from app.models.collection import Collection
from app.models.document import Document
from app.models.evidence_ledger import LedgerEntry, LedgerSource
from app.models.ingestion_job import IngestionJob
from app.models.insight import Insight
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
from app.models.space_member import SpaceMember
from app.models.workspace import Workspace


@pytest.fixture
def rbac_on(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)


def _principal(user_id, role=ROLE_MEMBER) -> AuthenticatedUser:
    return AuthenticatedUser(user_id=user_id, email="p@x.io", display_name="p", role=role)


def _apply(db, model, principal):
    af = accessible_filter(principal, model, db)
    query = db.query(model)
    if af is not None:
        query = query.filter(af)
    return af, query.all()


def _space(db, name="S"):
    s = Workspace(name=name)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _project(db, *, owner_id=None, workspace_id=None, name="P"):
    p = Project(name=name, owner_id=owner_id, workspace_id=workspace_id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _mission(db, *, owner_id=None, project_id=None):
    m = Mission(
        mission_id=f"T-{uuid4().hex[:8]}",
        title="row-filter fixture mission",
        objective="exercise the row filter",
        success_criteria=["c"],
        owner_id=owner_id,
        project_id=project_id,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


class TestNoFilterPaths:
    def test_flag_off_returns_none(self, db_session):
        assert settings.rbac_enabled is False
        af = accessible_filter(_principal(uuid4()), Project, db_session)
        assert af is None  # byte-identical: list returns every row

    def test_privileged_owner_returns_none(self, db_session, rbac_on):
        af = accessible_filter(_principal(uuid4(), ROLE_OWNER), Project, db_session)
        assert af is None

    def test_privileged_admin_returns_none(self, db_session, rbac_on):
        af = accessible_filter(_principal(uuid4(), ROLE_ADMIN), Project, db_session)
        assert af is None


class TestTopLevelProjects:
    def test_member_sees_only_owned_and_space_projects(self, db_session, rbac_on):
        me = uuid4()
        space = _space(db_session)
        db_session.add(SpaceMember(workspace_id=space.id, user_id=me))
        db_session.commit()

        mine = _project(db_session, owner_id=me, name="mine")
        in_my_space = _project(db_session, owner_id=uuid4(), workspace_id=space.id, name="space")
        other = _project(db_session, owner_id=uuid4(), workspace_id=None, name="other")
        other_space = _project(db_session, owner_id=uuid4(), workspace_id=_space(db_session, "T").id, name="othersp")

        _af, rows = _apply(db_session, Project, _principal(me))
        ids = {r.id for r in rows}
        assert mine.id in ids
        assert in_my_space.id in ids
        assert other.id not in ids  # not owner, not in its (no) space
        assert other_space.id not in ids  # space the member is not in

    def test_outsider_sees_nothing(self, db_session, rbac_on):
        _project(db_session, owner_id=uuid4(), name="a")
        _project(db_session, owner_id=uuid4(), workspace_id=_space(db_session).id, name="b")
        _af, rows = _apply(db_session, Project, _principal(uuid4()))
        assert rows == []


class TestChildMissions:
    def test_member_sees_missions_in_their_space_via_owning_project(self, db_session, rbac_on):
        me = uuid4()
        space = _space(db_session)
        db_session.add(SpaceMember(workspace_id=space.id, user_id=me))
        db_session.commit()
        proj = _project(db_session, owner_id=uuid4(), workspace_id=space.id)
        mine = _mission(db_session, owner_id=uuid4(), project_id=proj.id)

        other_proj = _project(db_session, owner_id=uuid4(), workspace_id=None)
        hidden = _mission(db_session, owner_id=uuid4(), project_id=other_proj.id)

        _af, rows = _apply(db_session, Mission, _principal(me))
        ids = {r.id for r in rows}
        assert mine.id in ids
        assert hidden.id not in ids

    def test_orphan_mission_fail_closed_unless_owned(self, db_session, rbac_on):
        me = uuid4()
        orphan_other = _mission(db_session, owner_id=uuid4(), project_id=None)
        orphan_mine = _mission(db_session, owner_id=me, project_id=None)

        _af, rows = _apply(db_session, Mission, _principal(me))
        ids = {r.id for r in rows}
        assert orphan_other.id not in ids  # orphan, not owned -> fail closed (#260b)
        assert orphan_mine.id in ids  # owned -> owner_id allow path


class TestIngestionJobParentGoverned:
    """IngestionJob has NO owner_id and a NOT-NULL project_id — governed via the
    parent project's Space (the model-parity policy, no migration)."""

    def _doc(self, db, project_id):
        d = Document(name="f.pdf", project_id=project_id, owner_id=uuid4(), workspace_id=None)
        db.add(d)
        db.commit()
        db.refresh(d)
        return d

    def _job(self, db, project_id, document_id):
        j = IngestionJob(project_id=project_id, document_id=document_id, status="PENDING")
        db.add(j)
        db.commit()
        db.refresh(j)
        return j

    def test_member_sees_jobs_in_their_space_only(self, db_session, rbac_on):
        me = uuid4()
        space = _space(db_session)
        db_session.add(SpaceMember(workspace_id=space.id, user_id=me))
        db_session.commit()

        in_proj = _project(db_session, owner_id=uuid4(), workspace_id=space.id)
        in_doc = self._doc(db_session, in_proj.id)
        visible = self._job(db_session, in_proj.id, in_doc.id)

        out_proj = _project(db_session, owner_id=uuid4(), workspace_id=None)
        out_doc = self._doc(db_session, out_proj.id)
        hidden = self._job(db_session, out_proj.id, out_doc.id)

        _af, rows = _apply(db_session, IngestionJob, _principal(me))
        ids = {r.id for r in rows}
        assert visible.id in ids
        assert hidden.id not in ids

    def test_outsider_sees_no_jobs(self, db_session, rbac_on):
        proj = _project(db_session, owner_id=uuid4(), workspace_id=_space(db_session).id)
        doc = self._doc(db_session, proj.id)
        self._job(db_session, proj.id, doc.id)
        af, rows = _apply(db_session, IngestionJob, _principal(uuid4()))
        # no owner_id column + not in the space -> false() -> nothing
        assert rows == []


@pytest.mark.parametrize("model", [Document, IngestionJob])
@pytest.mark.parametrize("role", [ROLE_MEMBER, ROLE_SERVICE])
def test_live_project_owner_reads_document_and_job_without_space(db_session, rbac_on, model, role):
    """Job lists must agree with the parent-document read gate without a Space grant."""
    me = uuid4()
    projects = [
        Project(name="Live owned", owner_id=me),
        Project(name="Deleted owned", owner_id=me, deleted_at=datetime.utcnow()),
        Project(name="Foreign", owner_id=uuid4()),
    ]
    db_session.add_all(projects)
    db_session.flush()
    documents = [Document(name=p.name, project_id=p.id, owner_id=uuid4()) for p in projects]
    db_session.add_all(documents)
    db_session.flush()
    jobs = [IngestionJob(project_id=d.project_id, document_id=d.id) for d in documents]
    db_session.add_all(jobs)
    db_session.commit()
    assert db_session.query(SpaceMember).filter_by(user_id=me).count() == 0
    _, rows = _apply(db_session, model, _principal(me, role))
    expected = (documents if model is Document else jobs)[0].id
    assert {row.id for row in rows} == ({expected} if role == ROLE_MEMBER else set())


@pytest.mark.parametrize("model", [Project, Collection, Mission, Report, Insight, LedgerEntry])
def test_project_ownership_does_not_widen_other_model_filters(db_session, rbac_on, model):
    """Owning a project must not expose other-owned reports, missions or ledger rows."""
    me, other = uuid4(), uuid4()
    project = _project(db_session, owner_id=me)
    if model is Project:
        row = Project(name="Foreign", owner_id=other)
    elif model is Collection:
        row = Collection(name="Foreign", owner_id=other)
    elif model is Mission:
        row = Mission(mission_id=uuid4().hex, title="Foreign", objective="Private", success_criteria=["Private"], project_id=project.id, owner_id=other)
    elif model is Report:
        row = Report(title="Foreign", content="Private", project_id=project.id, owner_id=other)
    elif model is Insight:
        row = Insight(title="Foreign", content="Private", project_id=project.id)
    else:
        source = LedgerSource(project_id=project.id, source_url="https://example.test/source", source_url_hash=uuid4().hex * 2)
        db_session.add(source)
        db_session.flush()
        row = LedgerEntry(project_id=project.id, source_id=source.id, source_url=source.source_url, session_key="scope", claim="Private", disposition="supporting", owner_id=other)
    db_session.add(row)
    db_session.commit()
    _, rows = _apply(db_session, model, _principal(me))
    assert row.id not in {item.id for item in rows}
    if model is Project:
        assert {item.id for item in rows} == {project.id}
    else:
        assert rows == []
