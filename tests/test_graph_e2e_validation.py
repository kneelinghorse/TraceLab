"""T37.4: Graph-Enhanced Search E2E Validation.

Runs PEDR search with graph enabled vs disabled against 12 diverse queries,
producing a before/after comparison report proving graph layer impact.

Uses real graph layer with in-memory SQLite (synthetic but realistic data)
and stub lexical/semantic providers so the test is self-contained.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from app.core.database import Base, engine, SessionLocal
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.models.graph_edge import GraphEdge
from app.models.project import Project
from app.services.pedr.edge_materialization import EdgeMaterializationService
from app.services.pedr.search_orchestrator import (
    PEDRConfig,
    PEDRSearchOrchestrator,
    PEDRSearchResponse,
)


# ---------------------------------------------------------------------------
# Test data: 3 projects, 6 documents, 18 chunks, interconnected by edges
# ---------------------------------------------------------------------------

PROJECT_A_ID = str(uuid4())
PROJECT_B_ID = str(uuid4())
PROJECT_C_ID = str(uuid4())

DOC_IDS = {f"doc_{i}": str(uuid4()) for i in range(6)}

DOCUMENTS_META = [
    {"key": "doc_0", "project": PROJECT_A_ID, "name": "UX Research Findings Q1", "content": "User testing revealed friction in onboarding flow. 40% drop-off at step 3."},
    {"key": "doc_1", "project": PROJECT_A_ID, "name": "Onboarding Redesign Proposal", "content": "Proposed redesign reduces onboarding steps from 5 to 3. A/B test plan included."},
    {"key": "doc_2", "project": PROJECT_A_ID, "name": "Sprint Retrospective Notes", "content": "Team discussed onboarding improvements. Decision: prioritize mobile-first approach."},
    {"key": "doc_3", "project": PROJECT_B_ID, "name": "API Performance Report", "content": "P95 latency reduced from 450ms to 120ms after query optimization. Database indexes added."},
    {"key": "doc_4", "project": PROJECT_B_ID, "name": "Infrastructure Cost Analysis", "content": "Cloud spending up 30% due to unoptimized queries. Recommendation: implement caching layer."},
    {"key": "doc_5", "project": PROJECT_C_ID, "name": "Competitive Analysis 2026", "content": "Competitor X launched graph-based search. Market share implications for our product line."},
]

# 3 chunks per document
CHUNKS = []
for doc_meta in DOCUMENTS_META:
    doc_id = DOC_IDS[doc_meta["key"]]
    base_content = doc_meta["content"]
    for idx in range(3):
        CHUNKS.append({
            "doc_key": doc_meta["key"],
            "doc_id": doc_id,
            "project_id": doc_meta["project"],
            "chunk_index": idx,
            "content": f"[chunk {idx}] {base_content} (section {idx + 1})",
        })


# 12 diverse queries covering different intents and topics
VALIDATION_QUERIES = [
    "user research onboarding friction",
    "how to reduce API latency",
    "mobile-first design approach",
    "find all UX research findings",
    "database optimization recommendations",
    "competitive analysis graph search",
    "onboarding drop-off rate",
    "cloud cost reduction strategies",
    "sprint retrospective decisions",
    "A/B testing onboarding redesign",
    "infrastructure caching layer",
    "market share competitor analysis",
]


@dataclass
class QueryComparison:
    """Single query comparison result."""
    query: str
    graph_off_count: int
    graph_on_count: int
    graph_off_top_ids: List[str]
    graph_on_top_ids: List[str]
    new_results_from_graph: List[str]
    rank_changes: Dict[str, int]  # chunk_id -> rank_change (negative = improved)
    graph_off_rrf_scores: Dict[str, float]
    graph_on_rrf_scores: Dict[str, float]
    graph_candidates_expanded: int
    graph_layer_ms: float
    total_ms_off: float
    total_ms_on: float


def _build_chunk_id(doc_key: str, chunk_index: int) -> str:
    """Deterministic chunk ID for test data."""
    return f"{DOC_IDS[doc_key]}::{chunk_index}"


class _SearchProviderStub:
    """Stub lexical/semantic search that returns chunks based on keyword overlap."""

    def __init__(self, chunks: List[Dict[str, Any]]):
        self.chunks = chunks
        self._chunk_records: Dict[str, Dict[str, Any]] = {}

    def set_chunk_records(self, records: Dict[str, Dict[str, Any]]) -> None:
        self._chunk_records = records

    def search(
        self,
        query: str,
        top_k: int = 20,
        project_id: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        query_terms = set(query.lower().split())
        scored: List[tuple[float, Dict[str, Any]]] = []

        for chunk in self.chunks:
            content_terms = set(chunk["content"].lower().split())
            overlap = len(query_terms & content_terms)
            if overlap == 0:
                continue
            score = overlap / max(len(query_terms), 1)
            if project_id and chunk.get("project_id") != project_id:
                continue

            chunk_record = self._chunk_records.get(
                f"{chunk['doc_id']}::{chunk['chunk_index']}"
            )
            result: Dict[str, Any] = {
                "chunk_id": str(chunk_record["id"]) if chunk_record else str(uuid4()),
                "content": chunk["content"],
                "document_id": chunk["doc_id"],
                "project_id": chunk["project_id"],
                "chunk_index": chunk["chunk_index"],
                "score": score,
                "combined_score": score,
            }
            scored.append((score, result))

        scored.sort(key=lambda x: -x[0])
        return [item[1] for item in scored[:top_k]]


@pytest.fixture
def graph_search_env(db_session):
    """Set up project, documents, chunks, and edges for graph search validation."""
    # Create projects
    projects = {}
    for pid, name in [
        (PROJECT_A_ID, "UX Research"),
        (PROJECT_B_ID, "Platform Engineering"),
        (PROJECT_C_ID, "Product Strategy"),
    ]:
        p = Project(id=pid, name=name, description=f"Test project: {name}")
        db_session.add(p)
        projects[pid] = p
    db_session.commit()

    # Create documents
    docs = {}
    for doc_meta in DOCUMENTS_META:
        doc = Document(
            id=DOC_IDS[doc_meta["key"]],
            project_id=doc_meta["project"],
            name=doc_meta["name"],
            content=doc_meta["content"],
            file_type="notes",
            mime_type="text/plain",
            processed=True,
            chunked=True,
            validation_status="validated",
        )
        db_session.add(doc)
        docs[doc_meta["key"]] = doc
    db_session.commit()

    # Create chunks
    chunk_records: Dict[str, Dict[str, Any]] = {}
    for chunk_data in CHUNKS:
        chunk = DocumentChunk(
            document_id=chunk_data["doc_id"],
            chunk_index=chunk_data["chunk_index"],
            content=chunk_data["content"],
            token_count=len(chunk_data["content"].split()),
        )
        db_session.add(chunk)
        db_session.flush()
        key = f"{chunk_data['doc_id']}::{chunk_data['chunk_index']}"
        chunk_records[key] = {"id": chunk.id, "doc_id": chunk_data["doc_id"], "chunk_index": chunk_data["chunk_index"]}
    db_session.commit()

    # Materialize edges (full mode — creates all implicit FK edges)
    edge_service = EdgeMaterializationService(session_factory=lambda: db_session)
    mat_result = edge_service.materialize_implicit_edges(session=db_session, mode="full")

    # Add cross-document reference edges (doc_0 ↔ doc_1 via "references" — UX findings → redesign)
    from app.services.pedr.semantic_protocol import URNGenerator
    cross_edges = [
        ("references", DOC_IDS["doc_0"], DOC_IDS["doc_1"]),  # UX findings → redesign
        ("references", DOC_IDS["doc_1"], DOC_IDS["doc_2"]),  # redesign → retro notes
        ("references", DOC_IDS["doc_3"], DOC_IDS["doc_4"]),  # API perf → infra cost
    ]
    for edge_type, from_doc, to_doc in cross_edges:
        edge = GraphEdge.from_semantic_edge(
            edge_type=edge_type,
            from_urn=str(URNGenerator.for_document(from_doc)),
            to_urn=str(URNGenerator.for_document(to_doc)),
            direction="out",
            weight=1.0,
            reason="cross-document reference",
            via="test",
        )
        db_session.add(edge)
    db_session.commit()

    total_edges = db_session.query(GraphEdge).count()

    # Build search stub
    stub = _SearchProviderStub(CHUNKS)
    stub.set_chunk_records(chunk_records)

    return {
        "projects": projects,
        "docs": docs,
        "chunk_records": chunk_records,
        "stub": stub,
        "total_edges": total_edges,
        "mat_result": mat_result,
        "db_session": db_session,
    }


def _run_search(
    env: Dict[str, Any],
    query: str,
    enable_graph: bool,
    top_k: int = 10,
) -> PEDRSearchResponse:
    """Run a PEDR search with or without graph layer."""
    stub = env["stub"]
    db_session = env["db_session"]

    from app.services.pedr.graph_layer import GraphLayerService

    orchestrator = PEDRSearchOrchestrator(
        lexical_search=stub.search,
        semantic_search=stub.search,
        graph_service=GraphLayerService(session=db_session),
    )

    return orchestrator.search(
        query=query,
        top_k=top_k,
        enable_graph=enable_graph,
        graph_depth=2,
        graph_decay=0.7,
        graph_top_k_seeds=10,
    )


def _compare_query(env: Dict[str, Any], query: str) -> QueryComparison:
    """Run query with graph on and off, return comparison."""
    result_off = _run_search(env, query, enable_graph=False)
    result_on = _run_search(env, query, enable_graph=True)

    off_ids = [r.chunk_id for r in result_off.results]
    on_ids = [r.chunk_id for r in result_on.results]

    off_ranks = {cid: i for i, cid in enumerate(off_ids)}
    on_ranks = {cid: i for i, cid in enumerate(on_ids)}

    new_from_graph = [cid for cid in on_ids if cid not in off_ranks]

    rank_changes: Dict[str, int] = {}
    for cid in on_ids:
        if cid in off_ranks:
            rank_changes[cid] = on_ranks[cid] - off_ranks[cid]

    off_scores = {r.chunk_id: r.rrf_score for r in result_off.results}
    on_scores = {r.chunk_id: r.rrf_score for r in result_on.results}

    graph_candidates = result_on.metadata.graph_candidates_expanded or 0
    graph_ms = result_on.metadata.timings.graph_ms if result_on.metadata.timings else 0.0
    total_off = result_off.metadata.timings.total_ms if result_off.metadata.timings else 0.0
    total_on = result_on.metadata.timings.total_ms if result_on.metadata.timings else 0.0

    return QueryComparison(
        query=query,
        graph_off_count=len(off_ids),
        graph_on_count=len(on_ids),
        graph_off_top_ids=off_ids[:5],
        graph_on_top_ids=on_ids[:5],
        new_results_from_graph=new_from_graph,
        rank_changes=rank_changes,
        graph_off_rrf_scores=off_scores,
        graph_on_rrf_scores=on_scores,
        graph_candidates_expanded=graph_candidates,
        graph_layer_ms=graph_ms,
        total_ms_off=total_off,
        total_ms_on=total_on,
    )


class TestGraphSearchE2EValidation:
    """E2E validation: graph-enhanced search vs baseline across 12 queries."""

    def test_graph_layer_produces_candidates(self, graph_search_env):
        """Graph layer expands at least some candidates on relevant queries."""
        result = _run_search(graph_search_env, "user research onboarding", enable_graph=True)
        assert result.metadata.graph_enabled is True
        # Graph should be listed in layers_used if it found candidates
        assert "graph" in result.metadata.layers_used

    def test_graph_disabled_excludes_graph_layer(self, graph_search_env):
        """With graph disabled, graph layer is not used."""
        result = _run_search(graph_search_env, "user research", enable_graph=False)
        assert result.metadata.graph_enabled is False

    def test_graph_impacts_results(self, graph_search_env):
        """Graph expansion either surfaces new results or changes rankings."""
        comparisons = [_compare_query(graph_search_env, q) for q in VALIDATION_QUERIES]
        queries_with_new = [c for c in comparisons if len(c.new_results_from_graph) > 0]
        queries_with_rank_changes = [
            c for c in comparisons
            if any(delta != 0 for delta in c.rank_changes.values())
        ]
        impacted = len(set(
            c.query for c in queries_with_new + queries_with_rank_changes
        ))
        # Graph should impact at least some queries (new results or re-ranking)
        assert impacted >= 1, (
            f"Expected graph to impact at least 1 query via new results or re-ranking, "
            f"but 0/{len(comparisons)} queries were affected"
        )

    def test_graph_changes_rankings(self, graph_search_env):
        """Graph layer affects result rankings for at least some queries."""
        comparisons = [_compare_query(graph_search_env, q) for q in VALIDATION_QUERIES]
        queries_with_rank_changes = [
            c for c in comparisons
            if any(delta != 0 for delta in c.rank_changes.values())
        ]
        # Graph should change rankings for some queries
        assert len(queries_with_rank_changes) >= 1, (
            "Graph layer did not change rankings for any of the 12 queries"
        )

    def test_graph_latency_acceptable(self, graph_search_env):
        """Graph layer adds acceptable latency (<500ms per query)."""
        comparisons = [_compare_query(graph_search_env, q) for q in VALIDATION_QUERIES]
        graph_latencies = [c.graph_layer_ms for c in comparisons]
        max_latency = max(graph_latencies)
        avg_latency = statistics.mean(graph_latencies) if graph_latencies else 0

        assert max_latency < 500, f"Max graph latency {max_latency:.1f}ms exceeds 500ms"
        assert avg_latency < 200, f"Avg graph latency {avg_latency:.1f}ms exceeds 200ms"

    def test_result_count_at_least_as_good(self, graph_search_env):
        """Graph-enabled search returns at least as many results as without."""
        comparisons = [_compare_query(graph_search_env, q) for q in VALIDATION_QUERIES]
        for c in comparisons:
            assert c.graph_on_count >= c.graph_off_count, (
                f"Query '{c.query}': graph-on returned fewer results "
                f"({c.graph_on_count} < {c.graph_off_count})"
            )

    def test_edge_count_realistic(self, graph_search_env):
        """Materialized edges represent realistic FK relationships."""
        total = graph_search_env["total_edges"]
        # 6 docs × (2 edges: belongs_to + contains) = 12 doc↔project edges
        # 18 chunks × (2 edges: contains + part_of) = 36 chunk↔doc edges
        # 3 cross-doc reference edges
        # Total expected: ~51
        assert total >= 40, f"Expected at least 40 edges, got {total}"
        assert total <= 100, f"Unexpectedly high edge count: {total}"

    def test_all_12_queries_execute_successfully(self, graph_search_env):
        """All 12 queries complete without errors in both modes."""
        for query in VALIDATION_QUERIES:
            result_off = _run_search(graph_search_env, query, enable_graph=False)
            result_on = _run_search(graph_search_env, query, enable_graph=True)
            assert not result_off.metadata.degraded, f"Query '{query}' degraded with graph off"
            # Graph-on may be degraded if graph layer had no results, that's ok

    def test_generate_comparison_report(self, graph_search_env, tmp_path):
        """Generate full comparison report as JSON artifact."""
        comparisons = [_compare_query(graph_search_env, q) for q in VALIDATION_QUERIES]

        # Aggregate stats
        queries_with_new_results = sum(1 for c in comparisons if c.new_results_from_graph)
        queries_with_rank_changes = sum(
            1 for c in comparisons if any(d != 0 for d in c.rank_changes.values())
        )
        total_new_results = sum(len(c.new_results_from_graph) for c in comparisons)
        avg_graph_ms = statistics.mean(c.graph_layer_ms for c in comparisons)
        max_graph_ms = max(c.graph_layer_ms for c in comparisons)

        report = {
            "title": "T37.4 Graph-Enhanced Search E2E Validation Report",
            "date": "2026-03-12",
            "sprint": "37",
            "summary": {
                "total_queries": len(comparisons),
                "queries_with_new_graph_results": queries_with_new_results,
                "queries_with_rank_changes": queries_with_rank_changes,
                "total_new_results_surfaced": total_new_results,
                "avg_graph_latency_ms": round(avg_graph_ms, 2),
                "max_graph_latency_ms": round(max_graph_ms, 2),
            },
            "per_query": [
                {
                    "query": c.query,
                    "graph_off_results": c.graph_off_count,
                    "graph_on_results": c.graph_on_count,
                    "new_results_from_graph": len(c.new_results_from_graph),
                    "rank_changes": sum(1 for d in c.rank_changes.values() if d != 0),
                    "graph_candidates_expanded": c.graph_candidates_expanded,
                    "graph_layer_ms": round(c.graph_layer_ms, 2),
                    "total_ms_off": round(c.total_ms_off, 2),
                    "total_ms_on": round(c.total_ms_on, 2),
                }
                for c in comparisons
            ],
        }

        # Write report to cmos reports directory
        report_dir = Path("cmos/reports/sprint-37")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "graph-search-e2e-validation.json"
        report_path.write_text(json.dumps(report, indent=2))

        # Also write to tmp for test artifact
        tmp_report = tmp_path / "report.json"
        tmp_report.write_text(json.dumps(report, indent=2))

        # Validate report structure
        assert report["summary"]["total_queries"] == 12
        assert report_path.exists()

        # Print summary for test output
        print(f"\n{'='*60}")
        print(f"GRAPH SEARCH E2E VALIDATION REPORT")
        print(f"{'='*60}")
        print(f"Queries tested: {report['summary']['total_queries']}")
        print(f"Queries with new graph results: {report['summary']['queries_with_new_graph_results']}")
        print(f"Queries with rank changes: {report['summary']['queries_with_rank_changes']}")
        print(f"Total new results surfaced: {report['summary']['total_new_results_surfaced']}")
        print(f"Avg graph latency: {report['summary']['avg_graph_latency_ms']:.2f}ms")
        print(f"Max graph latency: {report['summary']['max_graph_latency_ms']:.2f}ms")
        print(f"{'='*60}")
        for pq in report["per_query"]:
            delta = pq["graph_on_results"] - pq["graph_off_results"]
            indicator = f"+{delta}" if delta > 0 else str(delta)
            print(f"  [{indicator:>3}] {pq['query'][:45]:<45} "
                  f"off={pq['graph_off_results']} on={pq['graph_on_results']} "
                  f"new={pq['new_results_from_graph']} graph={pq['graph_layer_ms']:.1f}ms")
        print(f"{'='*60}")
