"""The palette must find every readable object without leaking names or bodies."""

from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.config import settings
from app.core.security import create_access_token, generate_api_key, get_key_prefix, hash_api_key
from app.main import app
from app.models.api_key import APIKey
from app.models.collection import Collection
from app.models.document import Document
from app.models.evidence_ledger import LedgerEntry, LedgerSource
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace

API = f"{settings.api_v1_prefix}/navigation/search"
KINDS = ("project", "document", "mission", "report", "collection", "evidence")
_HASH = "placeholder-not-a-real-hash"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def actor(db, role="member", credential="jwt"):
    user = User(email=f"{uuid4()}@example.test", display_name="Palette reader", password_hash=_HASH, role=role)
    db.add(user)
    db.flush()
    if credential == "jwt":
        return user, {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    plain = generate_api_key()
    db.add(APIKey(user_id=user.id, name="Palette contract", key_hash=hash_api_key(plain), key_prefix=get_key_prefix(plain)))
    return user, {"X-API-Key": plain}


def object_row(db, kind, title, *, owner_id=None, workspace_id=None, project_id=None):
    common = {"owner_id": owner_id, "workspace_id": workspace_id}
    if kind == "project":
        row = Project(name=title, **common)
    elif kind == "collection":
        row = Collection(name=title, instructions="Private body, never a search summary", **common)
    elif kind == "document":
        row = Document(name=title, project_id=project_id, content="Private body", **common)
    elif kind == "mission":
        row = Mission(mission_id=uuid4().hex, title=title, objective="Private body", success_criteria=["Find the name"], project_id=project_id, **common)
    elif kind == "report":
        row = Report(title=title, content="Private body", project_id=project_id, **common)
    else:
        source = LedgerSource(project_id=project_id, source_url="https://example.test/source", source_url_hash=uuid4().hex * 2)
        db.add(source)
        db.flush()
        row = LedgerEntry(claim=title, project_id=project_id, source_id=source.id, source_url=source.source_url, session_key="palette", disposition="supporting", snippet="Private body", **common)
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize("kind", KINDS)
def test_each_entity_is_scoped_before_counting_and_reachable_beyond_100(client, db_session, monkeypatch, kind):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user, headers = actor(db_session)
    other, _ = actor(db_session)
    project = Project(name="Parent bundle", owner_id=user.id)
    db_session.add(project)
    db_session.flush()
    rows = [object_row(db_session, kind, f"Needle {i:03}", owner_id=user.id, project_id=project.id) for i in range(113)]
    hidden_project = project.id
    # Evidence in an owned project is readable even when its child owner differs.
    if kind == "evidence":
        private = Project(name="Private parent", owner_id=other.id)
        db_session.add(private)
        db_session.flush()
        hidden_project = private.id
    hidden = object_row(db_session, kind, "Needle 000 hidden", owner_id=other.id, project_id=hidden_project)
    db_session.commit()
    seen = []
    for page in range(1, 4):
        response = client.get(API, params={"q": " nEeDlE ", "entity_type": kind, "page": page, "page_size": 50}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        payload = response.json()
        assert payload["query"] == "nEeDlE"
        assert len(payload["groups"]) == 1
        group = payload["groups"][0]
        assert (group["entity_type"], group["total"], group["page"], group["page_size"]) == (kind, 113, page, 50)
        assert len(group["items"]) == (50 if page < 3 else 13)
        assert all(set(item) == {"id", "title", "href"} for item in group["items"])
        assert str(hidden.id) not in response.text and "Private body" not in response.text
        seen.extend(item["id"] for item in group["items"])
        prefix = "evidence" if kind == "evidence" else kind + "s"
        assert all(item["href"] == f"/{prefix}/{item['id']}" for item in group["items"])
    assert seen == [str(row.id) for row in rows]


def test_groups_follow_effective_parent_space_and_keep_owned_orphans(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user, headers = actor(db_session)
    other, _ = actor(db_session)
    shared, private = Workspace(name="Shared"), Workspace(name="Private")
    db_session.add_all([shared, private])
    db_session.flush()
    db_session.add(SpaceMember(user_id=user.id, workspace_id=shared.id))
    visible_parent = Project(name="Parent", workspace_id=shared.id, owner_id=other.id)
    hidden_parent = Project(name="Parent", workspace_id=private.id, owner_id=other.id)
    db_session.add_all([visible_parent, hidden_parent])
    db_session.flush()
    visible_ids = {}
    for kind in KINDS:
        top_level = kind in {"project", "collection"}
        visible = object_row(db_session, kind, "Reachable object", owner_id=other.id, project_id=visible_parent.id, workspace_id=shared.id if top_level else private.id)
        object_row(db_session, kind, "Reachable secret", owner_id=other.id, project_id=hidden_parent.id, workspace_id=private.id if top_level else shared.id)
        visible_ids[kind] = [str(visible.id)]
    for kind in ("mission", "report"):
        orphan = object_row(db_session, kind, "Reachable owned orphan", owner_id=user.id, workspace_id=private.id)
        visible_ids[kind].append(str(orphan.id))
    db_session.commit()
    response = client.get(API, params={"q": "reachable"}, headers=headers)
    assert response.status_code == 200, response.text
    assert [g["entity_type"] for g in response.json()["groups"]] == list(KINDS)
    for group in response.json()["groups"]:
        assert group["total"] == len(visible_ids[group["entity_type"]])
        assert [r["id"] for r in group["items"]] == visible_ids[group["entity_type"]]
    assert "Reachable secret" not in response.text


def test_evidence_needs_its_parent_even_when_owned_and_deleted_objects_stay_hidden(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user, headers = actor(db_session)
    other, _ = actor(db_session)
    projects = [Project(name="Needle parent", owner_id=owner, deleted_at=deleted) for owner, deleted in [(user.id, None), (other.id, None), (user.id, datetime.utcnow())]]
    db_session.add_all(projects)
    db_session.flush()
    allowed = object_row(db_session, "evidence", "Needle claim", project_id=projects[0].id, owner_id=other.id)
    object_row(db_session, "evidence", "Needle private parent", project_id=projects[1].id, owner_id=user.id)
    object_row(db_session, "evidence", "Needle deleted parent", project_id=projects[2].id, owner_id=user.id)
    deleted_doc = object_row(db_session, "document", "Needle deleted document", project_id=projects[0].id, owner_id=user.id)
    deleted_doc.deleted_at = datetime.utcnow()
    db_session.commit()
    response = client.get(API, params={"q": "Needle"}, headers=headers)
    assert response.status_code == 200, response.text
    groups = {g["entity_type"]: g for g in response.json()["groups"]}
    assert [r["id"] for r in groups["evidence"]["items"]] == [str(allowed.id)]
    assert groups["project"]["total"] == 1
    assert groups["document"]["total"] == 0


@pytest.mark.parametrize("query", ["%", "_", "\\", "' OR 1=1"])
def test_name_queries_are_literal_and_do_not_hydrate_collection_content(client, db_session, query):
    user, headers = actor(db_session, "admin")
    target = object_row(db_session, "collection", f"Find {query} literally", owner_id=user.id)
    object_row(db_session, "collection", "A different name", owner_id=user.id)
    db_session.commit()
    statements = []
    engine = db_session.get_bind()

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        response = client.get(API, params={"q": query, "entity_type": "collection"}, headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert response.status_code == 200, response.text
    group = response.json()["groups"][0]
    assert group["total"] == 1 and group["items"][0]["id"] == str(target.id)
    assert not any("collection_items" in statement for statement in statements)


@pytest.mark.parametrize("rbac", [True, False])
@pytest.mark.parametrize("credential", ["jwt", "api_key"])
def test_mounted_auth_gate_and_legacy_visibility(client, db_session, monkeypatch, rbac, credential):
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    _, member = actor(db_session, credential=credential)
    _, service = actor(db_session, "service", credential)
    object_row(db_session, "collection", "Unowned legacy collection")
    db_session.commit()
    assert client.get(API, params={"q": "legacy"}).status_code == 401
    assert client.get(API, params={"q": "legacy"}, headers=service).status_code == 403
    response = client.get(API, params={"q": "legacy", "entity_type": "collection"}, headers=member)
    assert response.status_code == 200, response.text
    assert response.json()["groups"][0]["total"] == (0 if rbac else 1)


@pytest.mark.parametrize("params", [{"q": " "}, {"q": "a" * 201}, {"q": "a", "entity_type": "user"}, {"q": "a", "page": 0}, {"q": "a", "page_size": 51}])
def test_invalid_search_never_becomes_an_unbounded_catalog(client, db_session, params):
    _, headers = actor(db_session)
    db_session.commit()
    assert client.get(API, params=params, headers=headers).status_code == 422
