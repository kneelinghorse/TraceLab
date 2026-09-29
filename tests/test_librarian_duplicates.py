"""DUP-1: a review suggestion must never become a corpus edit or a scope grant."""

import json
import socket
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.config import settings
from app.core.database import engine
from app.core.security import AuthenticatedUser, require_authenticated_user
from app.main import app
from app.models.document import Document
from app.models.project import Project
from app.models.user import User
from app.services import librarian_duplicates as duplicates

TEXT = json.loads((Path(__file__).parent / "fixtures/librarian_duplicate_calibration.json").read_text())


@pytest.fixture
def duplicate_client(monkeypatch, auth_headers):
    monkeypatch.setattr(settings, "rbac_enabled", False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Duplicate review cannot use network/model/vector services")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    client = TestClient(app)
    client.headers.update(auth_headers)
    yield client


def add_document(db, project, content, name="Interview notes", identity=None):
    doc = Document(id=identity or uuid4(), project_id=project.id, name=name, content=content)
    db.add(doc)
    db.commit()
    return doc


def scan(client, project):
    response = client.post("/api/v1/librarian/duplicates/scan", json={"project_id": str(project.id)})
    assert response.status_code == 200, response.text
    return response.json()


def compare(client, project, pair, **overrides):
    return client.post("/api/v1/librarian/duplicates/compare", json={
        "project_id": str(project.id), "document_ids": [doc["id"] for doc in pair["documents"]],
        "candidate_id": pair["candidate_id"], **overrides,
    })


@pytest.mark.parametrize(("other", "expected"), [
    (TEXT["feedback"].upper().replace(" ", "  "), "exact_text"),
    (TEXT["feedback"].replace("confusing", "unclear").replace("second session", "later session"), "probable_overlap"),
    (TEXT["distinct"], None),
    ("Researchers interviewed participants about onboarding and collections, but found a different problem: exporting large datasets.", None),
    ("", None),
    ("   \n\u2003 ", None),
    ("Researchers described onboarding.", None),
])
def test_calibration_measures_text_not_titles_or_topics(duplicate_client, project, db_session, other, expected):
    add_document(db_session, project, TEXT["feedback"])
    add_document(db_session, project, other)  # Deliberately identical titles.
    pairs = scan(duplicate_client, project)["candidates"]
    assert [pair["kind"] for pair in pairs] == ([expected] if expected else [])
    if expected:
        pair = pairs[0]
        assert pair["evidence"] and pair["recommendation"]
        assert "probability" not in pair["basis"].lower()
        assert all(doc["href"] == f'/documents/{doc["id"]}' for doc in pair["documents"])


def test_one_shared_boilerplate_paragraph_is_not_a_near_duplicate(duplicate_client, project, db_session):
    # Most text overlaps: the paragraph-distribution guard, not just threshold,
    # must prevent a shared disclaimer from turning distinct notes into advice.
    add_document(db_session, project, TEXT["boilerplate"] + "\n\nResearchers could not find the upload button during onboarding and requested a clearer project header with a visible destination selector.")
    add_document(db_session, project, TEXT["boilerplate"] + "\n\nMechanics could not locate replacement door seals during inspections and requested an accurate warehouse inventory with regional availability and compatibility information.")
    assert scan(duplicate_client, project)["candidates"] == []


def test_nonempty_short_text_can_match_exactly_but_never_by_prefix(duplicate_client, project, db_session):
    add_document(db_session, project, "Plan: café")
    add_document(db_session, project, "PLAN: cafe\u0301")
    add_document(db_session, project, "Plan: café follow-up")
    pairs = scan(duplicate_client, project)["candidates"]
    assert len(pairs) == 1 and pairs[0]["kind"] == "exact_text"


def test_empty_and_overlong_inputs_are_excluded_without_prefix_matching(duplicate_client, project, db_session):
    for content in [None, "\n\u2003\t", "a" * 20000 + "first", "a" * 20000 + "second"]:
        add_document(db_session, project, content)
    result = scan(duplicate_client, project)
    assert result["candidates"] == []
    assert result["coverage"]["empty_documents"] == 2
    assert result["coverage"]["overlong_documents"] == 2
    assert result["coverage"]["examined_documents"] == 0


def test_explicit_review_and_compare_are_sql_read_only(duplicate_client, project, db_session):
    add_document(db_session, project, TEXT["feedback"])
    add_document(db_session, project, TEXT["feedback"])
    writes = []

    def record_write(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement.split()[0])

    event.listen(engine, "before_cursor_execute", record_write)
    try:
        result = scan(duplicate_client, project)
        assert scan(duplicate_client, project)["candidates"] == result["candidates"]
        response = compare(duplicate_client, project, result["candidates"][0])
        assert response.status_code == 200, response.text
        assert [doc["content"] for doc in response.json()["documents"]] == [TEXT["feedback"]] * 2
        assert writes == []
    finally:
        event.remove(engine, "before_cursor_execute", record_write)


def test_limits_never_turn_truncated_prefixes_into_exact_duplicates(duplicate_client, project, db_session):
    for index in range(103):
        add_document(db_session, project, "identical text", identity=UUID(int=index + 1))
    add_document(db_session, project, "x" * 20000 + "A", identity=UUID(int=0))
    result = scan(duplicate_client, project)
    coverage = result["coverage"]
    assert coverage["readable_documents"] == 104
    assert coverage["scanned_documents"] == 100
    assert coverage["overlong_documents"] == 1
    assert coverage["examined_documents"] == 99
    assert coverage["limited"] is True
    assert len(result["candidates"]) == 20
    assert coverage["candidate_count"] == 99 * 98 // 2
    assert coverage["candidates_limited"] is True
    assert all(UUID(doc["id"]).int > 0 for pair in result["candidates"] for doc in pair["documents"])


@pytest.mark.parametrize("change", ["content", "deleted", "reparent", "project_deleted"])
def test_compare_rechecks_stale_or_moved_sources(duplicate_client, project, db_session, change):
    first = add_document(db_session, project, TEXT["feedback"])
    add_document(db_session, project, TEXT["feedback"])
    pair = scan(duplicate_client, project)["candidates"][0]
    if change == "content":
        first.content += "\nA later correction."
    elif change == "deleted":
        first.deleted_at = datetime.utcnow()
    elif change == "project_deleted":
        project.deleted_at = datetime.utcnow()
    else:
        other = Project(name="Other readable project")
        db_session.add(other)
        db_session.flush()
        first.project_id = other.id
    db_session.commit()
    response = compare(duplicate_client, project, pair)
    assert response.status_code in (404, 409), response.text
    assert TEXT["feedback"] not in response.text


def test_project_scope_precedes_analysis_even_for_admin(duplicate_client, project, db_session, monkeypatch):
    owner = db_session.query(User).first()
    owner.role = "admin"
    db_session.commit()
    other = Project(name="Other")
    db_session.add(other)
    db_session.commit()
    add_document(db_session, project, TEXT["feedback"])
    secret = add_document(db_session, other, "SECRET OTHER PROJECT")
    monkeypatch.setattr(settings, "rbac_enabled", True)
    original = duplicates._prepare

    def bounded(row):
        assert row.id != secret.id, "Filtering after text analysis leaks the other project"
        return original(row)

    monkeypatch.setattr(duplicates, "_prepare", bounded)
    assert scan(duplicate_client, project)["coverage"]["readable_documents"] == 1
    response = duplicate_client.post("/api/v1/librarian/duplicates/compare", json={
        "project_id": str(project.id), "document_ids": [str(secret.id), str(uuid4())], "candidate_id": "0" * 64,
    })
    assert response.status_code == 404 and "SECRET" not in response.text


def test_member_and_service_cannot_expand_access(duplicate_client, project, db_session, monkeypatch):
    add_document(db_session, project, TEXT["feedback"])
    stranger = User(email="duplicate-stranger@example.test", display_name="Stranger", password_hash=str(uuid4()), role="member")
    db_session.add(stranger)
    db_session.commit()
    monkeypatch.setattr(settings, "rbac_enabled", True)
    principal = AuthenticatedUser(user_id=stranger.id, email=stranger.email, display_name="Stranger", role="member")
    app.dependency_overrides[require_authenticated_user] = lambda: principal
    try:
        assert duplicate_client.post("/api/v1/librarian/duplicates/scan", json={"project_id": str(project.id)}).status_code == 403
        principal = AuthenticatedUser(user_id=stranger.id, email=stranger.email, display_name="Service", role="service")
        assert duplicate_client.post("/api/v1/librarian/duplicates/scan", json={"project_id": str(project.id)}).status_code == 403
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)


def test_member_losing_project_access_cannot_reopen_cached_comparison(duplicate_client, project, db_session, monkeypatch):
    member = User(email="duplicate-member@example.test", display_name="Member", password_hash=str(uuid4()), role="member")
    db_session.add(member)
    db_session.flush()
    project.owner_id = member.id
    db_session.commit()
    add_document(db_session, project, TEXT["feedback"])
    add_document(db_session, project, TEXT["feedback"])
    principal = AuthenticatedUser(user_id=member.id, email=member.email, display_name="Member", role="member")
    monkeypatch.setattr(settings, "rbac_enabled", True)
    app.dependency_overrides[require_authenticated_user] = lambda: principal
    try:
        pair = scan(duplicate_client, project)["candidates"][0]
        project.owner_id = None
        db_session.commit()
        response = compare(duplicate_client, project, pair)
        assert response.status_code == 403
        assert TEXT["feedback"] not in response.text
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)


def test_forged_comparison_and_unrecognized_write_fields_fail_closed(duplicate_client, project, db_session):
    add_document(db_session, project, TEXT["feedback"])
    add_document(db_session, project, TEXT["feedback"])
    pair = scan(duplicate_client, project)["candidates"][0]
    assert compare(duplicate_client, project, pair, candidate_id="0" * 64).status_code == 409
    assert compare(duplicate_client, project, pair, action="delete").status_code == 422
    assert compare(duplicate_client, project, pair, document_ids=[pair["documents"][0]["id"]] * 2).status_code == 422
