"""A mission's evidence payload must not become a read primitive for other projects.

Mission.context["evidence"] is author-controlled JSON carrying chunk ids, and the
relationship builder loaded those chunks by id with no project or soft-delete filter.
So a caller who can write a mission could name ANY chunk uuid in the instance and read
back its document name — and, at depth 2, a preview of its text — through
GET /missions/{id}/related, a route that authorizes only the mission itself (SEC-3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.authorization import accessible_project_ids
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User
from app.services.cache_manager import get_cache_manager
from app.services.relationship_service import RelationshipService

_HASH = "unused-test-hash"


@pytest.fixture(autouse=True)
def _clear_cache():
    get_cache_manager().invalidate_relationship_context()
    yield
    get_cache_manager().invalidate_relationship_context()


def _user(db, role="member"):
    user = User(email=f"{uuid4()}@example.test", display_name="Reader", password_hash=_HASH, role=role)
    db.add(user)
    db.flush()
    return AuthenticatedUser(user_id=user.id, email=user.email, display_name=user.display_name, role=role), user


def _chunk_in_its_own_project(db, owner, name):
    project = Project(name=f"{name} {uuid4().hex[:6]}", owner_id=owner.id)
    db.add(project)
    db.flush()
    document = Document(project_id=project.id, name=f"{name} source.pdf", owner_id=owner.id)
    db.add(document)
    db.flush()
    chunk = DocumentChunk(document_id=document.id, chunk_index=0, content=f"{name} secret text")
    db.add(chunk)
    db.flush()
    return project, document, chunk


def _mission_citing(db, project, owner, chunk):
    mission = Mission(
        project_id=project.id, mission_id=f"SCOPE-{uuid4().hex[:6]}", title="Mission",
        objective="Objective", success_criteria=["ok"], owner_id=owner.id,
        context={"evidence": [{"evidence_id": "EV-1", "chunk_id": str(chunk.id),
                               "summary": "cited", "source": "s", "relevance_score": 0.9}]},
    )
    db.add(mission)
    db.commit()
    return mission


def _names(context):
    return {doc.name for doc in context.documents}


@pytest.mark.unit
def test_evidence_cannot_reach_a_chunk_in_a_project_the_caller_cannot_read(db_session):
    settings.rbac_enabled = True
    try:
        attacker_auth, attacker = _user(db_session)
        victim_auth, victim = _user(db_session)
        _, victim_doc, victim_chunk = _chunk_in_its_own_project(db_session, victim, "Victim")
        attacker_project = Project(name="Attacker research", owner_id=attacker.id)
        db_session.add(attacker_project)
        db_session.flush()
        mission = _mission_citing(db_session, attacker_project, attacker, victim_chunk)

        context = RelationshipService().get_relationship_context(
            db_session, mission.id, depth=2,
            allowed_project_ids=accessible_project_ids(attacker_auth, db_session),
        )

        assert victim_doc.name not in _names(context)
        assert all(chunk.document_id != victim_doc.id for chunk in context.chunks)
    finally:
        settings.rbac_enabled = False


@pytest.mark.unit
def test_evidence_does_not_resurrect_a_soft_deleted_document(db_session):
    settings.rbac_enabled = True
    try:
        auth, owner = _user(db_session)
        project, document, chunk = _chunk_in_its_own_project(db_session, owner, "Own")
        mission = _mission_citing(db_session, project, owner, chunk)
        document.deleted_at = datetime.now(UTC)
        db_session.commit()

        context = RelationshipService().get_relationship_context(
            db_session, mission.id, depth=2,
            allowed_project_ids=accessible_project_ids(auth, db_session),
        )

        assert document.name not in _names(context)
    finally:
        settings.rbac_enabled = False


@pytest.mark.unit
def test_two_callers_do_not_share_one_cached_relationship_context(db_session):
    """The cache is keyed by mission and filters. If scope is not in the key, the first
    caller's results are replayed to the second, silently undoing the scoping above."""
    settings.rbac_enabled = True
    try:
        owner_auth, owner = _user(db_session)
        outsider_auth, _ = _user(db_session)
        project, document, chunk = _chunk_in_its_own_project(db_session, owner, "Owned")
        mission = _mission_citing(db_session, project, owner, chunk)

        service = RelationshipService()
        owner_view = service.get_relationship_context(
            db_session, mission.id, depth=2,
            allowed_project_ids=accessible_project_ids(owner_auth, db_session),
        )
        outsider_view = service.get_relationship_context(
            db_session, mission.id, depth=2,
            allowed_project_ids=accessible_project_ids(outsider_auth, db_session),
        )

        assert document.name in _names(owner_view)
        assert document.name not in _names(outsider_view)
    finally:
        settings.rbac_enabled = False


@pytest.mark.unit
def test_an_accessible_chunk_is_still_returned(db_session):
    """Scoping must not empty the endpoint for the caller who legitimately owns the data."""
    settings.rbac_enabled = True
    try:
        auth, owner = _user(db_session)
        project, document, chunk = _chunk_in_its_own_project(db_session, owner, "Own")
        mission = _mission_citing(db_session, project, owner, chunk)

        context = RelationshipService().get_relationship_context(
            db_session, mission.id, depth=2,
            allowed_project_ids=accessible_project_ids(auth, db_session),
        )

        assert document.name in _names(context)
    finally:
        settings.rbac_enabled = False
