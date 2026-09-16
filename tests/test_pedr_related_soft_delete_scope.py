"""Soft-deleted documents and projects must not surface through graph traversal.

A soft delete is the only delete a user can perform, so a row that still appears as a
"related entity" has not been deleted from that user's point of view. The traversal
authorizes the SOURCE entity and scopes by project, but most neighbour lookups loaded
Document and Project rows by id with no deleted_at filter (SEC-3, Sprint 52 deferral).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models import Document, DocumentChunk, Insight, Mission, Project, Report
from app.services.pedr.relational import EntityType, RelationalService


def _seed(db):
    """A project holding a document, its chunk, and a mission/insight/report pointing at them."""
    project = Project(name=f"Soft delete {uuid4().hex[:6]}")
    db.add(project)
    db.flush()
    document = Document(project_id=project.id, name="Deleted source.pdf")
    db.add(document)
    db.flush()
    chunk = DocumentChunk(document_id=document.id, chunk_index=0, content="Chunk text")
    mission = Mission(
        project_id=project.id, mission_id=f"SEC3-{uuid4().hex[:6]}", title="Mission",
        objective="Objective", success_criteria=["ok"], result_document_ids=[str(document.id)],
    )
    insight = Insight(project_id=project.id, title="Insight", content="Content")
    report = Report(project_id=project.id, title="Report", content="Content")
    db.add_all([chunk, mission, insight, report])
    db.commit()
    return project, document, chunk, mission, insight, report


def _related(db, urn):
    return RelationalService().get_related(urn, max_depth=1, limit=50, session=db)


def _types_and_ids(result):
    return {(entity.entity_type, entity.entity_id) for entity in result.related_entities}


@pytest.mark.unit
def test_a_soft_deleted_document_is_not_a_neighbour_of_its_chunk(db_session):
    project, document, chunk, *_ = _seed(db_session)
    document.deleted_at = datetime.now(UTC)
    db_session.commit()

    result = _related(db_session, f"urn:research:chunk:{chunk.id}")

    assert (EntityType.DOCUMENT, str(document.id)) not in _types_and_ids(result)


@pytest.mark.unit
def test_a_soft_deleted_document_is_not_a_neighbour_of_its_mission(db_session):
    project, document, chunk, mission, *_ = _seed(db_session)
    document.deleted_at = datetime.now(UTC)
    db_session.commit()

    result = _related(db_session, f"urn:research:mission:{mission.id}")

    assert (EntityType.DOCUMENT, str(document.id)) not in _types_and_ids(result)


@pytest.mark.unit
@pytest.mark.parametrize("root", ["mission", "insight", "report", "document"])
def test_a_soft_deleted_project_is_not_a_neighbour_of_anything_it_owned(root, db_session):
    project, document, chunk, mission, insight, report = _seed(db_session)
    roots = {"mission": mission.id, "insight": insight.id, "report": report.id, "document": document.id}
    project.deleted_at = datetime.now(UTC)
    db_session.commit()

    result = _related(db_session, f"urn:research:{root}:{roots[root]}")

    assert (EntityType.PROJECT, str(project.id)) not in _types_and_ids(result)


@pytest.mark.unit
def test_a_live_document_is_still_a_neighbour_of_its_chunk(db_session):
    """The guard must exclude deleted rows without hiding live ones."""
    _, document, chunk, *_ = _seed(db_session)

    result = _related(db_session, f"urn:research:chunk:{chunk.id}")

    assert (EntityType.DOCUMENT, str(document.id)) in _types_and_ids(result)
