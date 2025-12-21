from __future__ import annotations

import pytest
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from app.core.database import engine
from app.models import Document, DocumentChunk, GraphEdge, Mission, Project, Report
from app.models.types import GUID
from app.services.pedr.cache import get_pedr_cache
from app.services.pedr.graph_layer import GraphLayerConfig, GraphLayerService
from app.services.pedr.search_orchestrator import PEDRSearchOrchestrator
from tests.fixtures.graph_fixtures import SeededGraph


pytest_plugins = ("tests.fixtures.graph_fixtures",)


@pytest.fixture(scope="module", autouse=True)
def graph_search_schema():
    metadata = MetaData()

    Project.__table__.to_metadata(metadata)
    Report.__table__.to_metadata(metadata)

    mission_table = Mission.__table__.to_metadata(metadata)
    for constraint in list(mission_table.constraints):
        if isinstance(constraint, CheckConstraint) and "jsonb_array_length" in str(constraint.sqltext):
            mission_table.constraints.remove(constraint)

    Document.__table__.to_metadata(metadata)
    Table(
        "document_chunks",
        metadata,
        Column("id", GUID(), primary_key=True),
        Column(
            "document_id",
            GUID(),
            ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("chunk_index", Integer, nullable=False),
        Column("content", Text, nullable=False),
        Column("content_tsv", Text, nullable=True),
        Column("embedding_id", String),
        Column("token_count", Integer),
        Column("start_char", Integer),
        Column("end_char", Integer),
        Column("prev_chunk_id", GUID(), ForeignKey("document_chunks.id")),
        Column("next_chunk_id", GUID(), ForeignKey("document_chunks.id")),
        Column("created_at", DateTime, nullable=True),
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
    )
    GraphEdge.__table__.to_metadata(metadata)

    metadata.create_all(engine, checkfirst=True)
    yield


@pytest.fixture(autouse=True)
def clean_graph_tables(db_session):
    db_session.query(GraphEdge).delete()
    db_session.query(DocumentChunk).delete()
    db_session.query(Document).delete()
    db_session.query(Mission).delete()
    db_session.query(Report).delete()
    db_session.query(Project).delete()
    db_session.commit()
    yield


class _StubSearch:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.results)


def _make_chunk_result(chunk, document, score: float):
    return {
        "chunk_id": str(chunk.id),
        "chunk_index": int(chunk.chunk_index),
        "document_id": str(document.id),
        "project_id": str(document.project_id),
        "content": chunk.content,
        "score": score,
    }


@pytest.fixture
def graph_orchestrator(db_session, seeded_graph: SeededGraph):
    doc1 = seeded_graph.documents["doc1"]
    doc2 = seeded_graph.documents["doc2"]
    chunk1 = seeded_graph.chunks["chunk1"]
    chunk2 = seeded_graph.chunks["chunk2"]
    chunk3 = seeded_graph.chunks["chunk3"]

    lexical = _StubSearch(
        [
            _make_chunk_result(chunk1, doc1, 0.92),
            _make_chunk_result(chunk2, doc1, 0.87),
        ]
    )
    semantic = _StubSearch([_make_chunk_result(chunk3, doc2, 0.89)])

    orchestrator = PEDRSearchOrchestrator(
        lexical_search=lexical,
        semantic_search=semantic,
        graph_service=GraphLayerService(session=db_session),
    )
    return orchestrator, lexical, semantic


@pytest.fixture
def pedr_cache():
    cache = get_pedr_cache()
    cache.invalidate_all()
    cache.reset_stats()
    return cache


@pytest.fixture
def disable_pedr_cache(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "pedr_cache_enabled", False, raising=False)


@pytest.fixture
def enable_pedr_cache(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "pedr_cache_enabled", True, raising=False)


def test_graph_expands_project_seed_to_expected_chunks(db_session, seeded_graph: SeededGraph):
    service = GraphLayerService(session=db_session)
    result = service.search(
        [seeded_graph.project_urn],
        config=GraphLayerConfig(max_depth=2),
    )

    urns = {entry["urn"] for entry in result.results}
    assert seeded_graph.urns["chunk1"] in urns
    assert seeded_graph.urns["chunk2"] in urns
    assert seeded_graph.urns["chunk3"] in urns


def test_graph_depth_limit_excludes_chunks(db_session, seeded_graph: SeededGraph):
    service = GraphLayerService(session=db_session)
    result = service.search(
        [seeded_graph.project_urn],
        config=GraphLayerConfig(max_depth=1),
    )

    urns = {entry["urn"] for entry in result.results}
    assert seeded_graph.urns["doc1"] in urns
    assert seeded_graph.urns["doc2"] in urns
    assert seeded_graph.urns["chunk1"] not in urns


def test_graph_layer_maps_chunk_ids(db_session, seeded_graph: SeededGraph):
    service = GraphLayerService(session=db_session)
    result = service.search(
        [seeded_graph.project_urn],
        config=GraphLayerConfig(max_depth=2),
    )

    entry = next(item for item in result.results if item["urn"] == seeded_graph.urns["chunk1"])
    assert entry["chunk_id"] == str(seeded_graph.chunks["chunk1"].id)


def test_graph_layer_includes_edge_types(db_session, seeded_graph: SeededGraph):
    service = GraphLayerService(session=db_session)
    result = service.search(
        [seeded_graph.project_urn],
        config=GraphLayerConfig(max_depth=2),
    )

    entry = next(item for item in result.results if item["urn"] == seeded_graph.urns["chunk1"])
    assert entry["edge_type"] == "contains"


def test_graph_layer_handles_empty_seeds(db_session):
    service = GraphLayerService(session=db_session)
    result = service.search([])
    assert result.results == []


def test_graph_layer_respects_allowed_edge_types(db_session, seeded_graph: SeededGraph):
    service = GraphLayerService(session=db_session)
    result = service.search(
        [seeded_graph.urns["chunk1"]],
        config=GraphLayerConfig(max_depth=1, allowed_edge_types=("references",)),
    )

    urns = {entry["urn"] for entry in result.results}
    assert seeded_graph.urns["chunk3"] in urns
    assert seeded_graph.urns["chunk2"] not in urns


def test_graph_layer_respects_max_candidates(db_session, seeded_graph: SeededGraph):
    service = GraphLayerService(session=db_session)
    result = service.search(
        [seeded_graph.project_urn],
        config=GraphLayerConfig(max_depth=2, max_candidates=1),
    )
    assert len(result.results) <= 1


def test_orchestrator_includes_graph_layer(graph_orchestrator, disable_pedr_cache):
    orchestrator, _, _ = graph_orchestrator
    response = orchestrator.search(
        query="graph integration",
        enable_graph=True,
        graph_top_k_seeds=1,
        graph_depth=2,
    )

    assert response.metadata.graph_enabled is True
    assert "graph" in response.metadata.layers_used


def test_orchestrator_skips_graph_layer_when_disabled(graph_orchestrator, disable_pedr_cache):
    orchestrator, _, _ = graph_orchestrator
    response = orchestrator.search(
        query="graph disabled",
        enable_graph=False,
    )

    assert response.metadata.graph_enabled is False
    assert "graph" not in response.metadata.layers_used


def test_orchestrator_graph_metadata_includes_graph_ms(graph_orchestrator, disable_pedr_cache):
    orchestrator, _, _ = graph_orchestrator
    response = orchestrator.search(
        query="graph timings",
        enable_graph=True,
        graph_top_k_seeds=1,
    )

    assert response.metadata.timings.graph_ms >= 0.0


def test_orchestrator_graph_candidates_expanded(graph_orchestrator, disable_pedr_cache):
    orchestrator, _, _ = graph_orchestrator
    response = orchestrator.search(
        query="graph candidates",
        enable_graph=True,
        graph_top_k_seeds=1,
        graph_depth=2,
    )

    assert response.metadata.graph_candidates_expanded == 2


def test_orchestrator_e2e_returns_results_with_graph_enabled(graph_orchestrator, disable_pedr_cache):
    orchestrator, _, _ = graph_orchestrator
    response = orchestrator.search(
        query="graph e2e",
        enable_graph=True,
        graph_top_k_seeds=1,
        graph_depth=2,
    )

    assert response.results
    assert response.results[0].urn is not None


def test_ranking_stability_across_runs(graph_orchestrator, disable_pedr_cache):
    orchestrator, _, _ = graph_orchestrator
    baseline = None
    for _ in range(5):
        response = orchestrator.search(
            query="stable ranking",
            enable_graph=True,
            graph_top_k_seeds=1,
            graph_depth=2,
        )
        ordering = [result.chunk_id for result in response.results]
        if baseline is None:
            baseline = ordering
        else:
            assert ordering == baseline


def test_cache_invalidated_on_edge_insert(
    db_session,
    graph_orchestrator,
    seeded_graph: SeededGraph,
    pedr_cache,
    enable_pedr_cache,
):
    orchestrator, _, _ = graph_orchestrator
    response = orchestrator.search(
        query="cache insert",
        enable_graph=True,
        graph_top_k_seeds=1,
        graph_depth=2,
    )
    assert response.results
    assert pedr_cache.get_stats().cache_size > 0

    new_edge = GraphEdge.from_semantic_edge(
        "related_to",
        seeded_graph.urns["chunk1"],
        "urn:research:document:cache-node",
    )
    db_session.add(new_edge)
    db_session.commit()

    stats = pedr_cache.get_stats()
    assert stats.cache_size == 0
    assert stats.invalidations >= 1


def test_cache_invalidated_on_edge_delete(
    db_session,
    graph_orchestrator,
    seeded_graph: SeededGraph,
    pedr_cache,
    enable_pedr_cache,
):
    edge = GraphEdge.from_semantic_edge(
        "related_to",
        seeded_graph.urns["chunk2"],
        "urn:research:document:cache-delete",
    )
    db_session.add(edge)
    db_session.commit()

    orchestrator, _, _ = graph_orchestrator
    response = orchestrator.search(
        query="cache delete",
        enable_graph=True,
        graph_top_k_seeds=1,
        graph_depth=2,
    )
    assert response.results
    assert pedr_cache.get_stats().cache_size > 0

    db_session.delete(edge)
    db_session.commit()

    stats = pedr_cache.get_stats()
    assert stats.cache_size == 0
    assert stats.invalidations >= 1


def test_graph_layer_depth2_performance_under_200ms(db_session):
    seed_urn = "urn:research:project:perf-seed"
    edges = []
    for idx in range(500):
        mid = f"urn:research:document:perf-mid-{idx}"
        leaf = f"urn:research:document:perf-leaf-{idx}"
        edges.append(GraphEdge.from_semantic_edge("contains", seed_urn, mid))
        edges.append(GraphEdge.from_semantic_edge("contains", mid, leaf))

    db_session.add_all(edges)
    db_session.commit()

    service = GraphLayerService(session=db_session)
    result = service.search(
        [seed_urn],
        config=GraphLayerConfig(max_depth=2, max_candidates=2000),
    )

    assert result.latency_ms is not None
    assert result.latency_ms < 200
