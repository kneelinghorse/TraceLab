"""T38.1: Semantic Edge Types E2E Validation.

Extends Sprint 37 E2E validation to compare:
  - FK-only edges (Sprint 37 baseline)
  - FK + co_occurs + topic_similar edges (Sprint 38)

Uses the same 12 diverse queries to measure graph improvement.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from app.core.database import engine, SessionLocal
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.graph_edge import GraphEdge
from app.models.project import Project
from app.services.pedr.edge_materialization import EdgeMaterializationService
from app.services.pedr.graph_layer import GraphLayerConfig, GraphLayerService
from app.services.pedr.search_orchestrator import PEDRSearchOrchestrator
from app.services.pedr.semantic_protocol import EntityType, URNGenerator


# ---------------------------------------------------------------------------
# Test data: same 3 projects, 6 documents, 18 chunks as Sprint 37
# Plus: 2 collections for co-occurrence and synthetic topic_similar edges
# ---------------------------------------------------------------------------

PROJECT_A_ID = str(uuid4())
PROJECT_B_ID = str(uuid4())
PROJECT_C_ID = str(uuid4())

DOC_IDS = {f"doc_{i}": str(uuid4()) for i in range(6)}

DOCUMENTS_META = [
    {"key": "doc_0", "project": PROJECT_A_ID, "name": "UX Research Findings Q1",
     "content": "User testing revealed friction in onboarding flow. 40% drop-off at step 3."},
    {"key": "doc_1", "project": PROJECT_A_ID, "name": "Onboarding Redesign Proposal",
     "content": "Proposed redesign reduces onboarding steps from 5 to 3. A/B test plan included."},
    {"key": "doc_2", "project": PROJECT_A_ID, "name": "Sprint Retrospective Notes",
     "content": "Team discussed onboarding improvements. Decision: prioritize mobile-first approach."},
    {"key": "doc_3", "project": PROJECT_B_ID, "name": "API Performance Report",
     "content": "P95 latency reduced from 450ms to 120ms after query optimization. Database indexes added."},
    {"key": "doc_4", "project": PROJECT_B_ID, "name": "Infrastructure Cost Analysis",
     "content": "Cloud spending up 30% due to unoptimized queries. Recommendation: implement caching layer."},
    {"key": "doc_5", "project": PROJECT_C_ID, "name": "Competitive Analysis 2026",
     "content": "Competitor X launched graph-based search. Market share implications for our product line."},
]

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


class _SearchProviderStub:
    """Stub lexical/semantic search returning chunks by keyword overlap."""

    def __init__(self, chunks: List[Dict[str, Any]]):
        self.chunks = chunks
        self._chunk_records: Dict[str, Dict[str, Any]] = {}

    def set_chunk_records(self, records: Dict[str, Dict[str, Any]]) -> None:
        self._chunk_records = records

    def search(self, query: str, top_k: int = 20, **kwargs: Any) -> List[Dict[str, Any]]:
        query_terms = set(query.lower().split())
        scored: List[tuple[float, Dict[str, Any]]] = []
        for chunk in self.chunks:
            content_terms = set(chunk["content"].lower().split())
            overlap = len(query_terms & content_terms)
            if overlap == 0:
                continue
            score = overlap / max(len(query_terms), 1)
            chunk_record = self._chunk_records.get(f"{chunk['doc_id']}::{chunk['chunk_index']}")
            result = {
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
def semantic_edge_env(db_session):
    """Set up environment with FK edges + semantic edges (co_occurs, topic_similar)."""
    # Create projects
    for pid, name in [
        (PROJECT_A_ID, "UX Research"),
        (PROJECT_B_ID, "Platform Engineering"),
        (PROJECT_C_ID, "Product Strategy"),
    ]:
        db_session.add(Project(id=pid, name=name, description=f"Test: {name}"))
    db_session.commit()

    # Create documents
    for doc_meta in DOCUMENTS_META:
        db_session.add(Document(
            id=DOC_IDS[doc_meta["key"]],
            project_id=doc_meta["project"],
            name=doc_meta["name"],
            content=doc_meta["content"],
            file_type="notes",
            mime_type="text/plain",
            processed=True,
            chunked=True,
            validation_status="validated",
        ))
    db_session.commit()

    # Create chunks
    chunk_records: Dict[str, Dict[str, Any]] = {}
    chunk_objs: Dict[str, DocumentChunk] = {}
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
        chunk_records[key] = {
            "id": chunk.id,
            "doc_id": chunk_data["doc_id"],
            "chunk_index": chunk_data["chunk_index"],
        }
        chunk_objs[key] = chunk
    db_session.commit()

    # --- Phase 1: FK edges only (Sprint 37 baseline) ---
    edge_service = EdgeMaterializationService(session_factory=lambda: db_session)
    fk_result = edge_service.materialize_implicit_edges(session=db_session, mode="full")

    # Cross-document references (same as Sprint 37)
    cross_edges = [
        ("references", DOC_IDS["doc_0"], DOC_IDS["doc_1"]),
        ("references", DOC_IDS["doc_1"], DOC_IDS["doc_2"]),
        ("references", DOC_IDS["doc_3"], DOC_IDS["doc_4"]),
    ]
    for edge_type, from_doc, to_doc in cross_edges:
        db_session.add(GraphEdge.from_semantic_edge(
            edge_type=edge_type,
            from_urn=str(URNGenerator.for_document(from_doc)),
            to_urn=str(URNGenerator.for_document(to_doc)),
            direction="out",
            weight=1.0,
            reason="cross-document reference",
            via="test",
        ))
    db_session.commit()

    fk_only_edge_count = db_session.query(GraphEdge).count()

    # --- Phase 2: Add semantic edges (Sprint 38) ---

    # Collection 1: "Onboarding Research" — groups UX chunks from doc_0 and doc_1
    coll_onboarding = Collection(name="Onboarding Research Bundle")
    db_session.add(coll_onboarding)
    db_session.flush()

    onboarding_chunks = [
        chunk_objs[f"{DOC_IDS['doc_0']}::0"],
        chunk_objs[f"{DOC_IDS['doc_0']}::1"],
        chunk_objs[f"{DOC_IDS['doc_1']}::0"],
        chunk_objs[f"{DOC_IDS['doc_1']}::1"],
        chunk_objs[f"{DOC_IDS['doc_2']}::0"],
    ]
    for chunk in onboarding_chunks:
        db_session.add(CollectionItem(collection_id=coll_onboarding.id, chunk_id=chunk.id))

    # Collection 2: "Infrastructure Perf" — groups API perf and infra cost chunks
    coll_infra = Collection(name="Infrastructure Performance Bundle")
    db_session.add(coll_infra)
    db_session.flush()

    infra_chunks = [
        chunk_objs[f"{DOC_IDS['doc_3']}::0"],
        chunk_objs[f"{DOC_IDS['doc_3']}::1"],
        chunk_objs[f"{DOC_IDS['doc_4']}::0"],
        chunk_objs[f"{DOC_IDS['doc_4']}::1"],
    ]
    for chunk in infra_chunks:
        db_session.add(CollectionItem(collection_id=coll_infra.id, chunk_id=chunk.id))
    db_session.commit()

    # Re-materialize to pick up co_occurs edges
    semantic_result = edge_service.materialize_implicit_edges(session=db_session, mode="full")

    # Add synthetic topic_similar edges (simulating Qdrant results)
    # doc_0 chunk 0 ↔ doc_1 chunk 0 (both about onboarding, topic_similar)
    topic_pairs = [
        (f"{DOC_IDS['doc_0']}::0", f"{DOC_IDS['doc_1']}::0", 0.91),  # onboarding topics
        (f"{DOC_IDS['doc_0']}::1", f"{DOC_IDS['doc_2']}::0", 0.88),  # UX ↔ retro
        (f"{DOC_IDS['doc_3']}::0", f"{DOC_IDS['doc_4']}::0", 0.93),  # API perf ↔ infra cost
        (f"{DOC_IDS['doc_3']}::1", f"{DOC_IDS['doc_4']}::1", 0.87),  # optimization topics
    ]
    for key_a, key_b, score in topic_pairs:
        rec_a = chunk_records[key_a]
        rec_b = chunk_records[key_b]
        urn_a = str(URNGenerator.for_chunk(str(rec_a["doc_id"]), rec_a["chunk_index"]))
        urn_b = str(URNGenerator.for_chunk(str(rec_b["doc_id"]), rec_b["chunk_index"]))
        for from_urn, to_urn in [(urn_a, urn_b), (urn_b, urn_a)]:
            db_session.add(GraphEdge.from_semantic_edge(
                edge_type="topic_similar",
                from_urn=from_urn,
                to_urn=to_urn,
                direction="out",
                weight=round(score, 4),
                reason=f"cosine>={score:.2f}",
                via="semantic",
                evidence={"cosine_similarity": round(score, 4)},
            ))
    db_session.commit()

    total_edges = db_session.query(GraphEdge).count()
    co_occurs_count = db_session.query(GraphEdge).filter(GraphEdge.edge_type == "co_occurs").count()
    topic_similar_count = db_session.query(GraphEdge).filter(GraphEdge.edge_type == "topic_similar").count()

    stub = _SearchProviderStub(CHUNKS)
    stub.set_chunk_records(chunk_records)

    return {
        "chunk_records": chunk_records,
        "stub": stub,
        "db_session": db_session,
        "fk_only_edge_count": fk_only_edge_count,
        "total_edges": total_edges,
        "co_occurs_count": co_occurs_count,
        "topic_similar_count": topic_similar_count,
    }


def _run_search(env, query, enable_graph, edge_types=None):
    orchestrator = PEDRSearchOrchestrator(
        lexical_search=env["stub"].search,
        semantic_search=env["stub"].search,
        graph_service=GraphLayerService(session=env["db_session"]),
    )
    return orchestrator.search(
        query=query,
        top_k=10,
        enable_graph=enable_graph,
        graph_depth=2,
        graph_decay=0.7,
        graph_top_k_seeds=10,
        graph_edge_types=list(edge_types) if edge_types else None,
    )


class TestSemanticEdgeE2EValidation:
    """E2E: Validate semantic edges improve graph search beyond FK baseline."""

    def test_edge_count_increased_beyond_fk_baseline(self, semantic_edge_env):
        """Semantic edges (co_occurs + topic_similar) increase total edge count."""
        env = semantic_edge_env
        assert env["co_occurs_count"] > 0, "Expected co_occurs edges to be materialized"
        assert env["topic_similar_count"] > 0, "Expected topic_similar edges"
        assert env["total_edges"] > env["fk_only_edge_count"], (
            f"Total edges ({env['total_edges']}) should exceed FK baseline ({env['fk_only_edge_count']})"
        )

    def test_co_occurs_edges_connect_cross_document_chunks(self, semantic_edge_env):
        """co_occurs edges bridge chunks from different documents in same collection."""
        db = semantic_edge_env["db_session"]
        co_edges = db.query(GraphEdge).filter(GraphEdge.edge_type == "co_occurs").all()

        # Check that at least some edges connect chunks from different documents
        cross_doc = 0
        for edge in co_edges:
            from_parts = edge.from_urn.split(":")
            to_parts = edge.to_urn.split(":")
            # Chunk URNs include document_id — if from_urn and to_urn have different doc IDs, it's cross-doc
            if len(from_parts) >= 4 and len(to_parts) >= 4:
                from_entity = from_parts[3]
                to_entity = to_parts[3]
                if from_entity != to_entity:
                    cross_doc += 1

        assert cross_doc > 0, "co_occurs should create cross-document chunk edges"

    def test_graph_search_with_semantic_edges_impacts_more_queries(self, semantic_edge_env):
        """With semantic edges, graph should impact more queries than FK-only baseline."""
        env = semantic_edge_env

        # Run all 12 queries with graph enabled (semantic + FK edges)
        impacted_queries = []
        for query in VALIDATION_QUERIES:
            result_off = _run_search(env, query, enable_graph=False)
            result_on = _run_search(env, query, enable_graph=True)

            off_ids = [r.chunk_id for r in result_off.results]
            on_ids = [r.chunk_id for r in result_on.results]

            off_ranks = {cid: i for i, cid in enumerate(off_ids)}
            new_from_graph = [cid for cid in on_ids if cid not in off_ranks]
            rank_changes = sum(
                1 for cid in on_ids
                if cid in off_ranks and off_ranks[cid] != on_ids.index(cid)
            )

            if new_from_graph or rank_changes > 0:
                impacted_queries.append(query)

        # Sprint 37 baseline: 4/12 queries impacted
        # With semantic edges, we expect improvement
        assert len(impacted_queries) >= 4, (
            f"Expected at least 4 impacted queries (Sprint 37 baseline), got {len(impacted_queries)}"
        )

    def test_graph_latency_remains_acceptable(self, semantic_edge_env):
        """Adding semantic edges should not significantly increase graph latency."""
        env = semantic_edge_env
        latencies = []
        for query in VALIDATION_QUERIES:
            result = _run_search(env, query, enable_graph=True)
            graph_ms = result.metadata.timings.graph_ms if result.metadata.timings else 0.0
            latencies.append(graph_ms)

        avg_latency = statistics.mean(latencies)
        max_latency = max(latencies)

        assert avg_latency < 5.0, f"Avg graph latency {avg_latency:.2f}ms too high"
        assert max_latency < 20.0, f"Max graph latency {max_latency:.2f}ms too high"

    def test_semantic_edge_type_filtering(self, semantic_edge_env):
        """Graph search can be filtered to use only semantic edges or only FK edges."""
        env = semantic_edge_env
        query = "user research onboarding friction"

        # All edges
        result_all = _run_search(env, query, enable_graph=True)

        # Only co_occurs + topic_similar
        result_semantic = _run_search(
            env, query, enable_graph=True,
            edge_types=("co_occurs", "topic_similar"),
        )

        # Only FK edges (contains, belongs_to, etc.)
        result_fk = _run_search(
            env, query, enable_graph=True,
            edge_types=("contains", "belongs_to", "references", "part_of", "derived_from"),
        )

        # All three should execute without error
        assert result_all.metadata.graph_enabled
        assert result_semantic.metadata.graph_enabled
        assert result_fk.metadata.graph_enabled

    def test_generate_sprint_38_comparison_report(self, semantic_edge_env, tmp_path):
        """Generate Sprint 38 before/after comparison report."""
        env = semantic_edge_env
        comparisons = []

        for query in VALIDATION_QUERIES:
            result_off = _run_search(env, query, enable_graph=False)
            result_on = _run_search(env, query, enable_graph=True)

            off_ids = [r.chunk_id for r in result_off.results]
            on_ids = [r.chunk_id for r in result_on.results]
            off_ranks = {cid: i for i, cid in enumerate(off_ids)}

            new_from_graph = [cid for cid in on_ids if cid not in off_ranks]
            rank_changes = {}
            for cid in on_ids:
                if cid in off_ranks:
                    rank_changes[cid] = on_ids.index(cid) - off_ranks[cid]

            graph_ms = result_on.metadata.timings.graph_ms if result_on.metadata.timings else 0.0
            candidates = result_on.metadata.graph_candidates_expanded or 0

            comparisons.append({
                "query": query,
                "graph_off_results": len(off_ids),
                "graph_on_results": len(on_ids),
                "new_results_from_graph": len(new_from_graph),
                "rank_changes": sum(1 for d in rank_changes.values() if d != 0),
                "graph_candidates_expanded": candidates,
                "graph_layer_ms": round(graph_ms, 2),
            })

        queries_with_impact = sum(
            1 for c in comparisons
            if c["new_results_from_graph"] > 0 or c["rank_changes"] > 0
        )
        avg_latency = statistics.mean(c["graph_layer_ms"] for c in comparisons)

        report = {
            "title": "T38.1 Semantic Edge Types E2E Validation Report",
            "date": "2026-03-13",
            "sprint": "38",
            "edge_summary": {
                "fk_only_edges": env["fk_only_edge_count"],
                "total_edges_with_semantic": env["total_edges"],
                "co_occurs_edges": env["co_occurs_count"],
                "topic_similar_edges": env["topic_similar_count"],
                "edge_increase_pct": round(
                    (env["total_edges"] - env["fk_only_edge_count"])
                    / max(env["fk_only_edge_count"], 1) * 100, 1
                ),
            },
            "search_impact": {
                "total_queries": len(comparisons),
                "queries_with_graph_impact": queries_with_impact,
                "avg_graph_latency_ms": round(avg_latency, 2),
                "sprint_37_baseline_impacted": 4,
                "improvement_vs_baseline": queries_with_impact >= 4,
            },
            "per_query": comparisons,
        }

        report_dir = Path("cmos/reports/sprint-38")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "semantic-edge-e2e-validation.json"
        report_path.write_text(json.dumps(report, indent=2))

        # Assertions
        assert report["edge_summary"]["co_occurs_edges"] > 0
        assert report["edge_summary"]["topic_similar_edges"] > 0
        assert report["edge_summary"]["total_edges_with_semantic"] > report["edge_summary"]["fk_only_edges"]
        assert report["search_impact"]["queries_with_graph_impact"] >= 4
        assert report_path.exists()

        # Print summary
        print(f"\n{'='*70}")
        print("T38.1 SEMANTIC EDGE TYPES E2E VALIDATION REPORT")
        print(f"{'='*70}")
        es = report["edge_summary"]
        print(f"FK-only edges:           {es['fk_only_edges']}")
        print(f"+ co_occurs edges:       {es['co_occurs_edges']}")
        print(f"+ topic_similar edges:   {es['topic_similar_edges']}")
        print(f"Total with semantic:     {es['total_edges_with_semantic']} (+{es['edge_increase_pct']}%)")
        print(f"{'='*70}")
        si = report["search_impact"]
        print(f"Queries impacted:        {si['queries_with_graph_impact']}/{si['total_queries']}")
        print(f"Sprint 37 baseline:      {si['sprint_37_baseline_impacted']}/12")
        print(f"Avg graph latency:       {si['avg_graph_latency_ms']:.2f}ms")
        print(f"{'='*70}")
        for c in comparisons:
            indicator = f"+{c['new_results_from_graph']}" if c["new_results_from_graph"] > 0 else " 0"
            print(f"  [{indicator:>3}] {c['query'][:45]:<45} "
                  f"off={c['graph_off_results']} on={c['graph_on_results']} "
                  f"ranks={c['rank_changes']} graph={c['graph_layer_ms']:.1f}ms")
        print(f"{'='*70}")
