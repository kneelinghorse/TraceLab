"""Real PostgreSQL proves bounded statement counts and records reverse-query plans."""

import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.adapters.repositories.sqlalchemy_graph_neighborhood_repo import SQLAlchemyGraphNeighborhoodRepository
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.chunk import DocumentChunk
from app.models.collection import Collection
from app.models.collection_document import CollectionDocument
from app.models.document import Document
from app.models.evidence_ledger import LedgerEntry, LedgerSource
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.models.user import User

pytestmark = pytest.mark.integration
_HASH = "unused-test-hash"


def seed_batch(db, project, owner, collection, offset):
    reports = [Report(title=f"Report {offset + i:04}", content=f"Finding https://example.test/graph/{offset+i}", owner_id=owner.id, project_id=project.id) for i in range(50)]
    missions = [Mission(mission_id=uuid4().hex, title=f"Mission {offset+i:04}", objective="Research", success_criteria=["Source"], owner_id=owner.id, project_id=project.id) for i in range(50)]
    sources = [LedgerSource(project_id=project.id, source_url=f"https://example.test/graph/{offset+i}", source_url_hash=uuid4().hex * 2) for i in range(50)]
    db.add_all([*reports, *missions, *sources])
    db.flush()
    documents = [Document(name=f"Document {offset * 10+i:04}", project_id=project.id, owner_id=owner.id,
                          source_report_id=reports[i % 50].id, source_mission_id=missions[i % 50].id,
                          content="Body omitted from graph" * 100) for i in range(500)]
    db.add_all(documents)
    db.flush()
    for i, mission in enumerate(missions):
        mission.result_report_id = reports[i].id
        mission.result_document_ids = [str(documents[j].id) for j in range(i, 500, 50)] + ["malformed-legacy-id"]
        reports[i].parent_id = reports[i - 1].id if i else None
    entries = [LedgerEntry(claim=f"Finding {offset * 8+i:04}", project_id=project.id, owner_id=owner.id,
                           source_id=sources[i % 50].id, source_url=sources[i % 50].source_url,
                           mission_id=missions[i % 50].id, session_key="graph-budget", disposition="supporting") for i in range(400)]
    db.add_all(entries)
    db.add_all([CollectionDocument(collection_id=collection.id, document_id=doc.id) for doc in documents])
    db.add_all([DocumentChunk(document_id=doc.id, chunk_index=0, content="Source chunk", token_count=2) for doc in documents])
    db.add_all([ReportSource(report_id=report.id, source_type="collection", source_id=collection.id) for report in reports])
    db.flush()
    return documents, missions, reports


def test_neighborhood_sql_budget_does_not_grow_with_rows_or_shown_parents(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    db = db_session
    owner = User(email=f"{uuid4()}@example.test", display_name="Graph owner", password_hash=_HASH, role="member")
    db.add(owner)
    db.flush()
    project = Project(name="Graph scale fixture", owner_id=owner.id)
    collection = Collection(name="Graph context", owner_id=owner.id)
    db.add_all([project, collection])
    db.flush()
    principal = AuthenticatedUser(user_id=owner.id, email=owner.email, display_name=owner.display_name, role=owner.role)
    repository = SQLAlchemyGraphNeighborhoodRepository()
    project_id = project.id
    samples = []
    first_rows = None
    for scale, offset in ((1, 0), (2, 50)):
        batch = seed_batch(db, project, owner, collection, offset)
        first_rows = first_rows or batch
        for limit in (3, 6, 12):
            for depth in (1, 2):
                statements = []

                def observe(_connection, _cursor, statement, _parameters, _context, _many, observed=statements):
                    observed.append(statement)

                bind = db.get_bind()
                event.listen(bind, "before_cursor_execute", observe)
                start = perf_counter()
                try:
                    result = repository.neighborhood(db, principal, root_type="project", root_id=project_id,
                                                     depth=depth, per_relation_limit=limit, max_nodes=150)
                finally:
                    elapsed = (perf_counter() - start) * 1000
                    event.remove(bind, "before_cursor_execute", observe)
                totals = {g.relation: g.total for g in result.groups if g.from_key == f"project:{project_id}"}
                assert totals == {"documents": 500 * scale, "missions": 50 * scale, "reports": 50 * scale, "evidence": 400 * scale}
                assert len(result.nodes) <= 150
                assert all("documents.raw_content" not in statement for statement in statements)
                assert len(statements) <= {1: 18, 2: 38}[depth], (depth, len(statements))
                samples.append({"scale": scale, "per_relation_limit": limit, "depth": depth,
                                "statements": len(statements), "latency_ms": elapsed,
                                "nodes": len(result.nodes), "node_types": sorted({node.type for node in result.nodes}),
                                "edges": len(result.edges), "totals": totals})
    for depth in (1, 2):
        for limit in (3, 6, 12):
            counts = {sample["statements"] for sample in samples if sample["depth"] == depth and sample["per_relation_limit"] == limit}
            assert len(counts) == 1, samples
        # Compare different parent counts with the same relation shape. At12,
        # the global cap omits collections and saves their one hydration query.
        comparable = [sample for sample in samples if sample["depth"] == depth and sample["per_relation_limit"] in {3, 6}]
        assert len({tuple(sample["node_types"]) for sample in comparable}) == 1, samples
        assert len({sample["statements"] for sample in comparable}) == 1, samples

    documents, missions, reports = first_rows
    plans = {}
    for name, sql, value in (
        ("documents.source_mission_id", "SELECT id FROM documents WHERE source_mission_id = CAST(:id AS uuid)", missions[0].id),
        ("documents.source_report_id", "SELECT id FROM documents WHERE source_report_id = CAST(:id AS uuid)", reports[0].id),
        ("missions.result_report_id", "SELECT id FROM missions WHERE result_report_id = CAST(:id AS uuid)", reports[0].id),
        ("collection_documents.document_id", "SELECT collection_id FROM collection_documents WHERE document_id = CAST(:id AS uuid)", documents[0].id),
    ):
        plans[name] = db.execute(text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"), {"id": str(value)}).scalar_one()
    evidence = {"fixture": {"projects": 1, "documents": 1000, "ledger_entries": 800, "missions": 100, "reports": 100}, "samples": samples, "reverse_lookup_explain": plans}
    print("GRAPH_NEIGHBORHOOD_POSTGRES=" + json.dumps(evidence))
    if output := os.getenv("GRAPH1_POSTGRES_OUTPUT"):
        Path(output).write_text(json.dumps(evidence, indent=2) + "\n")
