"""Graph neighborhoods preserve read boundaries before traversal and counting."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token, generate_api_key, get_key_prefix, hash_api_key
from app.main import app
from app.models.api_key import APIKey
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.collection_document import CollectionDocument
from app.models.document import Document
from app.models.evidence_ledger import LedgerEntry, LedgerSource
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace

API = "/api/v1/graph/neighborhood"
_HASH = "unused-test-hash"
ROUTES = {kind: f"/api/v1/{plural}" for kind, plural in (
    ("project", "projects"), ("document", "documents"), ("collection", "collections"),
    ("mission", "missions"), ("report", "reports"), ("evidence", "evidence"),
)}


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def actor(db, role="member"):
    user = User(email=f"{uuid4()}@example.test", display_name="Graph reader", password_hash=_HASH, role=role)
    db.add(user)
    db.flush()
    return user


def credentials(db, user, kind="jwt"):
    if kind == "jwt":
        return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    key = generate_api_key()
    db.add(APIKey(user_id=user.id, name="Graph contract", key_hash=hash_api_key(key), key_prefix=get_key_prefix(key)))
    db.flush()
    return {"X-API-Key": key}


def entry(db, project, owner, *, mission=None, claim="A persisted finding", url="https://example.test/finding"):
    source = LedgerSource(project_id=project.id, source_url=url, source_url_hash=uuid4().hex * 2)
    db.add(source)
    db.flush()
    row = LedgerEntry(project_id=project.id, owner_id=owner.id, source_id=source.id,
                      source_url=url, claim=claim, session_key="graph", disposition="supporting",
                      mission_id=mission.id if mission else None)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def graph(db_session):
    db = db_session
    owner = actor(db)
    space = Workspace(name="Research Space")
    db.add(space)
    db.flush()
    project = Project(name="Research", owner_id=owner.id, workspace_id=space.id)
    collection = Collection(name="Collected research", owner_id=owner.id, workspace_id=space.id)
    db.add_all([project, collection])
    db.flush()
    report = Report(title="Finding report", content="Finding https://example.test/finding", project_id=project.id, owner_id=owner.id)
    mission = Mission(mission_id=uuid4().hex, title="Find evidence", objective="Find evidence", success_criteria=["Sourced finding"], project_id=project.id, owner_id=owner.id)
    db.add_all([report, mission])
    db.flush()
    document = Document(name="Source document", project_id=project.id, owner_id=owner.id,
                        source_mission_id=mission.id, source_report_id=report.id)
    db.add(document)
    db.flush()
    mission.result_report_id = report.id
    mission.result_document_ids = [str(document.id)]
    evidence = entry(db, project, owner, mission=mission)
    chunk = DocumentChunk(document_id=document.id, chunk_index=0, content="The source finding", token_count=4)
    db.add(chunk)
    db.flush()
    db.add_all([
        CollectionDocument(collection_id=collection.id, document_id=document.id),
        CollectionItem(collection_id=collection.id, chunk_id=chunk.id),
        ReportSource(report_id=report.id, source_type="collection", source_id=collection.id),
        ReportSource(report_id=report.id, source_type="ledger_entry", source_id=evidence.id),
    ])
    db.commit()
    return {"owner": owner, "space": space, "project": project, "document": document,
            "collection": collection, "mission": mission, "report": report, "evidence": evidence}


def neighborhood(client, graph, headers, kind="project", **params):
    return client.get(API, params={"root_type": kind, "root_id": str(graph[kind].id), **params}, headers=headers)


def group(payload, kind, row, relation):
    return next(g for g in payload["groups"] if g["from_key"] == f"{kind}:{row.id}" and g["relation"] == relation)


@pytest.mark.parametrize("rbac", [True, False])
@pytest.mark.parametrize("credential", ["jwt", "api_key"])
@pytest.mark.parametrize("role", ["resource_owner", "space_member", "non_member", "admin", "service"])
def test_all_root_statuses_match_canonical_details_and_service_is_denied(client, db_session, graph, monkeypatch, rbac, credential, role):
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    user = graph["owner"] if role == "resource_owner" else actor(db_session, role if role in {"admin", "service"} else "member")
    if role == "space_member":
        db_session.add(SpaceMember(user_id=user.id, workspace_id=graph["space"].id, role="member"))
    headers = credentials(db_session, user, credential)
    db_session.commit()
    observations = []
    for kind, route in ROUTES.items():
        detail = client.get(f"{route}/{graph[kind].id}", headers=headers)
        response = neighborhood(client, graph, headers, kind)
        expected = 403 if role == "service" else detail.status_code
        assert expected in {200, 403, 404}, detail.text
        assert response.status_code == expected, (kind, role, detail.text, response.text)
        if role != "service":
            assert response.headers["cache-control"] == "private, no-store"
        observations.append({"root_type": kind, "detail_status": detail.status_code, "graph_status": response.status_code})
        if expected == 200:
            payload = response.json()
            assert payload["root"]["key"] == f"{kind}:{graph[kind].id}"
            assert response.headers["cache-control"] == "private, no-store"
            assert all(node["href"] == f"{ROUTES[node['type']].removeprefix('/api/v1')}/{node['id']}" for node in payload["nodes"])
    if output := os.getenv("GRAPH1_MATRIX_OUTPUT_DIR"):
        directory = Path(output)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{role}-{credential}-{rbac}.json").write_text(json.dumps({"role": role, "credential": credential, "rbac": rbac, "observations": observations}, indent=2) + "\n")


def test_auth_and_input_bounds_are_mounted_before_repository_access(client, db_session, graph):
    assert neighborhood(client, graph, {}).status_code == 401
    headers = credentials(db_session, graph["owner"])
    for params in ({"root_type": "chunk"}, {"root_id": "not-a-uuid"}, {"depth": 0}, {"depth": 3},
                   {"per_relation_limit": 0}, {"per_relation_limit": 51}, {"max_nodes": 0}, {"max_nodes": 151}):
        response = client.get(API, params={"root_type": "project", "root_id": str(graph["project"].id), **params}, headers=headers)
        assert response.status_code == 422, response.text


@pytest.mark.parametrize("rbac", [True, False])
def test_deleted_project_document_root_is_404_even_when_detail_allows_it(client, db_session, graph, monkeypatch, rbac):
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    graph["project"].deleted_at = datetime.utcnow()
    db_session.commit()
    headers = credentials(db_session, graph["owner"])
    detail = client.get(f"/api/v1/documents/{graph['document'].id}", headers=headers)
    assert detail.status_code == 200
    assert neighborhood(client, graph, headers, "document").status_code == 404


def test_persisted_relations_and_distinct_collection_documents(client, db_session, graph, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    headers = credentials(db_session, graph["owner"])
    expected = {
        "project": {"documents": "document", "missions": "mission", "reports": "report", "evidence": "evidence"},
        "mission": {"result_report": "report", "result_documents": "document", "source_documents": "document", "evidence": "evidence"},
        "document": {"source_mission": "mission", "source_report": "report", "evidence": "evidence"},
        "report": {"source_documents": "document", "collections": "collection", "evidence": "evidence"},
        "collection": {"documents": "document"}, "evidence": {"mission": "mission"},
    }
    for kind, relations in expected.items():
        response = neighborhood(client, graph, headers, kind)
        assert response.status_code == 200, response.text
        body = response.json()
        for relation, target in relations.items():
            found = group(body, kind, graph[kind], relation)
            assert found["total"] == found["shown"] == 1, (kind, relation, body)
            assert any(e["from"] == f"{kind}:{graph[kind].id}" and e["to"] == f"{target}:{graph[target].id}" and e["relation"] == relation and e["basis"] for e in body["edges"])
        for node in body["nodes"]:
            if node["type"] == "document":
                assert node["attributes"]["chunk_count"] == 1
        assert not any(node["type"] == "chunk" for node in body["nodes"])


def test_caps_keep_server_totals_and_expand_only_shown_nodes(client, db_session, graph):
    headers = credentials(db_session, graph["owner"])
    db_session.add_all([Document(name=f"More {i}", project_id=graph["project"].id, owner_id=graph["owner"].id) for i in range(8)])
    db_session.commit()
    response = neighborhood(client, graph, headers, depth=2, per_relation_limit=2, max_nodes=3)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["nodes"]) == 3 and body["truncated"] is True
    assert group(body, "project", graph["project"], "documents")["total"] == 9
    keys = {n["key"] for n in body["nodes"]}
    assert all(e["from"] in keys and e["to"] in keys for e in body["edges"])
    assert all(g["from_key"] in keys and g["shown"] <= g["total"] for g in body["groups"])


@pytest.mark.parametrize("rbac", [True, False])
def test_invalid_members_never_contribute_nodes_edges_or_totals(client, db_session, graph, monkeypatch, rbac):
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    owner = graph["owner"]
    other_space = Workspace(name="Other Space")
    db_session.add(other_space)
    db_session.flush()
    other_project = Project(name="Other project", owner_id=owner.id, workspace_id=other_space.id)
    deleted_project = Project(name="Deleted project", owner_id=owner.id, deleted_at=datetime.utcnow())
    db_session.add_all([other_project, deleted_project])
    db_session.flush()
    foreign = Document(name="Foreign result", owner_id=owner.id, project_id=other_project.id)
    orphaned = Document(name="Deleted parent result", owner_id=owner.id, project_id=deleted_project.id)
    deleted = Document(name="Deleted result", owner_id=owner.id, project_id=graph["project"].id, deleted_at=datetime.utcnow())
    db_session.add_all([foreign, orphaned, deleted])
    db_session.flush()
    invalid = [foreign, orphaned, deleted]
    graph["mission"].result_document_ids = [str(d.id) for d in [graph["document"], *invalid]]
    db_session.add_all([CollectionDocument(collection_id=graph["collection"].id, document_id=d.id) for d in invalid])
    db_session.commit()
    headers = credentials(db_session, owner)
    for kind, relation in (("mission", "result_documents"), ("collection", "documents")):
        response = neighborhood(client, graph, headers, kind, depth=2)
        assert response.status_code == 200, response.text
        body = response.json()
        assert group(body, kind, graph[kind], relation)["total"] == 1
        assert all(str(d.id) not in response.text for d in invalid)


def test_denied_intermediate_document_cannot_reveal_its_owned_source(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    caller, other = actor(db_session), actor(db_session)
    project = Project(name="Other parent", owner_id=other.id)
    db_session.add(project)
    db_session.flush()
    source = Report(title="Do not discover this via denied document", content="Result", owner_id=caller.id, project_id=project.id)
    mission = Mission(mission_id=uuid4().hex, title="Readable root", objective="Read", success_criteria=["Safe"], owner_id=caller.id, project_id=project.id)
    db_session.add_all([source, mission])
    db_session.flush()
    denied = Document(name="Private intermediary", project_id=project.id, owner_id=other.id, source_report_id=source.id)
    db_session.add(denied)
    db_session.flush()
    mission.result_document_ids = [str(denied.id)]
    db_session.commit()
    response = neighborhood(client, {"mission": mission}, credentials(db_session, caller), "mission", depth=2)
    assert response.status_code == 200, response.text
    assert str(denied.id) not in response.text and str(source.id) not in response.text
    assert group(response.json(), "mission", mission, "result_documents")["total"] == 0


def test_revocation_is_visible_on_next_call_even_with_a_reused_repository(client, db_session, graph, monkeypatch):
    from app.adapters.repositories.sqlalchemy_graph_neighborhood_repo import SQLAlchemyGraphNeighborhoodRepository
    from app.dependencies import get_graph_neighborhood_repository

    monkeypatch.setattr(settings, "rbac_enabled", True)
    caller = actor(db_session)
    membership = SpaceMember(user_id=caller.id, workspace_id=graph["space"].id, role="member")
    db_session.add(membership)
    graph["collection"].owner_id = caller.id
    db_session.commit()
    headers = credentials(db_session, caller)
    repository = SQLAlchemyGraphNeighborhoodRepository()
    app.dependency_overrides[get_graph_neighborhood_repository] = lambda: repository
    try:
        first = neighborhood(client, graph, headers, "collection", depth=2)
        assert first.status_code == 200 and str(graph["document"].id) in first.text
        db_session.delete(membership)
        db_session.commit()
        second = neighborhood(client, graph, headers, "collection", depth=2)
        assert second.status_code == 200, second.text
        assert str(graph["document"].id) not in second.text
        assert group(second.json(), "collection", graph["collection"], "documents")["total"] == 0
    finally:
        app.dependency_overrides.pop(get_graph_neighborhood_repository, None)


@pytest.mark.parametrize("rbac", [True, False])
def test_totals_equal_canonical_aggregates_and_citation_filters(client, db_session, graph, monkeypatch, rbac):
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    owner, project = graph["owner"], graph["project"]
    entry(db_session, project, owner, claim="Citation-only finding")
    entry(db_session, project, owner, claim="Document URL finding", url="https://example.test/document")
    graph["document"].document_metadata = {"original_url": "https://example.test/document"}
    db_session.add_all([Document(name=f"Other {i}", project_id=project.id, owner_id=owner.id) for i in range(5)])
    db_session.add(Document(name="Deleted", project_id=project.id, owner_id=owner.id, deleted_at=datetime.utcnow()))
    db_session.commit()
    headers = credentials(db_session, owner)
    project_graph = neighborhood(client, graph, headers, per_relation_limit=1).json()
    stats = client.get(f"/api/v1/projects/{project.id}/stats", headers=headers)
    assert stats.status_code == 200, stats.text
    for relation, field in (("documents", "document_count"), ("reports", "report_count")):
        assert group(project_graph, "project", project, relation)["total"] == stats.json()[field]
    missions = client.get("/api/v1/missions", params={"project_id": str(project.id), "page_size": 1}, headers=headers)
    assert missions.status_code == 200, missions.text
    assert group(project_graph, "project", project, "missions")["total"] == missions.json()["pagination"]["total"]
    for kind in ("project", "report", "document", "mission"):
        params = {"project_id": str(project.id), "page_size": 1}
        if kind != "project":
            params[f"{kind}_id"] = str(graph[kind].id)
        evidence = client.get("/api/v1/evidence", params=params, headers=headers)
        assert evidence.status_code == 200, evidence.text
        response = neighborhood(client, graph, headers, kind, per_relation_limit=1)
        assert response.status_code == 200, response.text
        total = group(response.json(), kind, graph[kind], "evidence")["total"]
        assert total == evidence.json()["entry_total"]
        assert total == {"project": 3, "report": 2, "document": 3, "mission": 1}[kind]


@pytest.mark.parametrize("rbac", [True, False])
def test_evidence_root_preserves_entry_then_parent_authorization(client, db_session, monkeypatch, rbac):
    monkeypatch.setattr(settings, "rbac_enabled", rbac)
    caller, other = actor(db_session), actor(db_session)
    project = Project(name="Private parent", owner_id=other.id)
    db_session.add(project)
    db_session.flush()
    evidence = entry(db_session, project, caller)
    db_session.commit()
    headers = credentials(db_session, caller)
    for deleted in (False, True):
        if deleted:
            project.deleted_at = datetime.utcnow()
            db_session.commit()
        detail = client.get(f"/api/v1/evidence/{evidence.id}", headers=headers)
        response = neighborhood(client, {"evidence": evidence}, headers, "evidence")
        assert response.status_code == detail.status_code == (404 if deleted else 403 if rbac else 200)


def test_parent_reports_and_duplicate_provenance_are_truthful(client, db_session, graph):
    parent = Report(title="Previous report", content="Old", project_id=graph["project"].id, owner_id=graph["owner"].id)
    db_session.add(parent)
    db_session.flush()
    graph["report"].parent_id = parent.id
    graph["mission"].result_document_ids = ["malformed", str(graph["document"].id), str(graph["document"].id).upper()]
    db_session.add(ReportSource(report_id=graph["report"].id, source_type="collection", source_id=graph["collection"].id))
    db_session.commit()
    headers = credentials(db_session, graph["owner"])
    report = neighborhood(client, graph, headers, "report")
    assert report.status_code == 200, report.text
    assert group(report.json(), "report", graph["report"], "parent_report")["total"] == 1
    assert group(report.json(), "report", graph["report"], "collections")["total"] == 1
    mission = neighborhood(client, graph, headers, "mission")
    assert mission.status_code == 200, mission.text
    assert group(mission.json(), "mission", graph["mission"], "result_documents")["total"] == 1


def test_missing_roots_are_not_empty_graphs_and_stats_route_requires_credentials(client, db_session, graph):
    headers = credentials(db_session, graph["owner"])
    for kind in ROUTES:
        response = client.get(API, params={"root_type": kind, "root_id": str(uuid4())}, headers=headers)
        assert response.status_code == 404, response.text
    # /graph/stats now requires credentials; see the SEC-3 tests below for its contract.
    assert client.get("/api/v1/graph/stats").status_code == 401


def test_graph_does_not_use_cache_manager_or_emit_ambiguous_local_times(client, db_session, graph, monkeypatch):
    from app.services.cache_manager import CacheManager

    def forbidden(*_args, **_kwargs):
        pytest.fail("Graph reads must not use CacheManager")

    for method in ("cached_value", "get_value", "set_value"):
        monkeypatch.setattr(CacheManager, method, forbidden)
    response = neighborhood(client, graph, credentials(db_session, graph["owner"]), depth=2)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    for node in response.json()["nodes"]:
        assert datetime.fromisoformat(node["attributes"]["updated_at"]).utcoffset().total_seconds() == 0


def test_graph_stats_refuses_anonymous_callers(client):
    """It lived on the PUBLIC health router and served corpus counts to anyone (SEC-3).

    Reverting it there would restore a credential-free disclosure of how much research
    the instance holds, so the anonymous case is asserted on its own.
    """
    assert client.get("/api/v1/graph/stats").status_code == 401


def test_graph_stats_counts_only_the_callers_own_projects(client, db_session, graph):
    """A member sees their own corpus, not the whole instance's."""
    settings.rbac_enabled = True
    try:
        outsider = actor(db_session)
        foreign = Project(name="Someone else's research", owner_id=outsider.id)
        db_session.add(foreign)
        db_session.flush()
        foreign_doc = Document(name="Private source", project_id=foreign.id, owner_id=outsider.id)
        db_session.add(foreign_doc)
        db_session.flush()
        db_session.add(DocumentChunk(document_id=foreign_doc.id, chunk_index=0, content="Private text"))
        db_session.commit()

        owner_view = client.get("/api/v1/graph/stats", headers=credentials(db_session, graph["owner"]))
        outsider_view = client.get("/api/v1/graph/stats", headers=credentials(db_session, outsider))

        assert owner_view.status_code == 200, owner_view.text
        assert set(owner_view.json()) == {"edge_counts", "total_edges", "document_count", "chunk_count"}
        # Each caller counts their own document, never the other's.
        assert owner_view.json()["document_count"] == 1
        assert outsider_view.json()["document_count"] == 1
        # Corpus-wide edge totals are withheld from a scoped caller rather than disclosed.
        assert outsider_view.json()["edge_counts"] == {}
        assert outsider_view.json()["total_edges"] == 0
    finally:
        settings.rbac_enabled = False


def test_graph_stats_excludes_soft_deleted_documents(client, db_session, graph):
    """A deleted document must stop being counted, like every other read path."""
    headers = credentials(db_session, graph["owner"])
    before = client.get("/api/v1/graph/stats", headers=headers).json()["document_count"]
    graph["document"].deleted_at = datetime.now(UTC)
    db_session.commit()

    after = client.get("/api/v1/graph/stats", headers=headers).json()["document_count"]

    assert after == before - 1
