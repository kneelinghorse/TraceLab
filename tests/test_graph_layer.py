from __future__ import annotations

import uuid

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
from app.services.pedr.graph_layer import GraphLayerConfig, GraphLayerService, URNParser
from app.services.pedr.semantic_protocol import URNGenerator


@pytest.fixture(scope="module", autouse=True)
def graph_layer_schema():
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
        Column("id", GUID(), primary_key=True, default=uuid.uuid4),
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


def _create_document_with_chunks(db_session, project, *, chunk_count: int = 1):
    document = Document(
        project_id=project.id,
        name=f"Doc-{uuid.uuid4()}",
        content="test",
    )
    db_session.add(document)
    db_session.flush()

    chunks = []
    for index in range(chunk_count):
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=f"chunk-{index}",
        )
        db_session.add(chunk)
        chunks.append(chunk)
    db_session.commit()
    return document, chunks


def _add_edge(db_session, from_urn: str, to_urn: str, edge_type: str = "contains"):
    edge = GraphEdge(
        from_urn=from_urn,
        to_urn=to_urn,
        edge_type=edge_type,
        direction="out",
    )
    db_session.add(edge)
    db_session.commit()
    return edge


@pytest.fixture
def graph_layer(db_session):
    return GraphLayerService(session=db_session)


def test_parse_chunk_urn_valid():
    document_id = "doc-123"
    urn = f"urn:research:chunk:{document_id}-chunk-4"
    assert URNParser.parse_chunk_urn(urn) == (document_id, 4)


def test_parse_chunk_urn_invalid_type():
    urn = "urn:research:document:doc-123"
    assert URNParser.parse_chunk_urn(urn) is None


def test_parse_chunk_urn_missing_index():
    urn = "urn:research:chunk:doc-123"
    assert URNParser.parse_chunk_urn(urn) is None


def test_parse_chunk_urn_invalid_index():
    urn = "urn:research:chunk:doc-123-chunk-x"
    assert URNParser.parse_chunk_urn(urn) is None


def test_search_empty_seeds_returns_empty(graph_layer):
    result = graph_layer.search([])
    assert result.results == []


def test_bfs_respects_depth_limit(db_session, graph_layer):
    seed = "urn:research:project:proj-1"
    mid = "urn:research:document:doc-1"
    leaf = "urn:research:mission:m1"
    _add_edge(db_session, seed, mid, "contains")
    _add_edge(db_session, mid, leaf, "references")

    result = graph_layer.search([seed], config=GraphLayerConfig(max_depth=1))
    urns = {entry["urn"] for entry in result.results}

    assert mid in urns
    assert leaf not in urns


def test_decay_scoring_from_seed_score(db_session, graph_layer, project):
    document, chunks = _create_document_with_chunks(db_session, project, chunk_count=2)
    seed_urn = str(URNGenerator.for_chunk(str(document.id), 0))
    target_urn = str(URNGenerator.for_chunk(str(document.id), 1))
    _add_edge(db_session, seed_urn, target_urn, "contains")

    results = [
        {
            "document_id": str(document.id),
            "chunk_index": 0,
            "score": 0.8,
        }
    ]
    config = GraphLayerConfig(max_depth=1, decay_factor=0.5)
    layer = graph_layer.expand_from_results(results, top_k=1, config=config)

    target = next(entry for entry in layer.results if entry["urn"] == target_urn)
    assert target["score"] == pytest.approx(0.4)


def test_edge_type_filtering(db_session, graph_layer):
    seed = "urn:research:project:seed-1"
    keep = "urn:research:document:doc-1"
    skip = "urn:research:document:doc-2"
    _add_edge(db_session, seed, keep, "references")
    _add_edge(db_session, seed, skip, "contains")

    config = GraphLayerConfig(max_depth=1, allowed_edge_types=("references",))
    layer = graph_layer.search([seed], config=config)
    urns = {entry["urn"] for entry in layer.results}

    assert keep in urns
    assert skip not in urns


def test_max_candidates_caps_output(db_session, graph_layer):
    seed = "urn:research:project:seed-2"
    for idx in range(3):
        _add_edge(
            db_session,
            seed,
            f"urn:research:document:doc-{idx}",
            "contains",
        )

    config = GraphLayerConfig(max_depth=1, max_candidates=2)
    layer = graph_layer.search([seed], config=config)

    assert len(layer.results) <= 2


def test_cycle_handling(db_session, graph_layer):
    seed = "urn:research:project:seed-3"
    other = "urn:research:project:other-3"
    _add_edge(db_session, seed, other, "related_to")
    _add_edge(db_session, other, seed, "related_to")

    config = GraphLayerConfig(max_depth=3)
    layer = graph_layer.search([seed], config=config)
    urns = {entry["urn"] for entry in layer.results}

    assert other in urns
    assert seed not in urns


def test_expand_from_results_prefers_urn(db_session, graph_layer):
    seed = "urn:research:project:seed-4"
    target = "urn:research:document:doc-4"
    _add_edge(db_session, seed, target, "contains")

    results = [{"urn": seed, "score": 0.2}]
    layer = graph_layer.expand_from_results(results, top_k=1)

    assert target in {entry["urn"] for entry in layer.results}


def test_expand_from_results_builds_urn_from_document_and_chunk_index(
    db_session,
    graph_layer,
    project,
):
    document, chunks = _create_document_with_chunks(db_session, project, chunk_count=1)
    seed_urn = str(URNGenerator.for_chunk(str(document.id), 0))
    target = "urn:research:project:related-1"
    _add_edge(db_session, seed_urn, target, "references")

    results = [{"document_id": str(document.id), "chunk_index": 0, "score": 1.0}]
    layer = graph_layer.expand_from_results(results, top_k=1)

    assert target in {entry["urn"] for entry in layer.results}


def test_expand_from_results_resolves_chunk_id_to_urn(
    db_session,
    graph_layer,
    project,
):
    document, chunks = _create_document_with_chunks(db_session, project, chunk_count=1)
    seed_urn = str(URNGenerator.for_chunk(str(document.id), 0))
    target = "urn:research:project:related-2"
    _add_edge(db_session, seed_urn, target, "references")

    results = [{"chunk_id": str(chunks[0].id), "score": 0.9}]
    layer = graph_layer.expand_from_results(results, top_k=1)

    assert target in {entry["urn"] for entry in layer.results}


def test_output_includes_chunk_id_for_chunk_urn(
    db_session,
    graph_layer,
    project,
):
    document, chunks = _create_document_with_chunks(db_session, project, chunk_count=2)
    seed = "urn:research:project:seed-5"
    target_urn = str(URNGenerator.for_chunk(str(document.id), 1))
    _add_edge(db_session, seed, target_urn, "contains")

    layer = graph_layer.search([seed], config=GraphLayerConfig(max_depth=1))

    target = next(entry for entry in layer.results if entry["urn"] == target_urn)
    assert target["chunk_id"] == str(chunks[1].id)


def test_non_chunk_entities_do_not_emit_rrf_ids(db_session, graph_layer):
    seed = "urn:research:project:seed-6"
    target = "urn:research:project:related-6"
    _add_edge(db_session, seed, target, "related_to")

    layer = graph_layer.search([seed], config=GraphLayerConfig(max_depth=1))
    entry = next(item for item in layer.results if item["urn"] == target)

    assert "chunk_id" not in entry
    assert "document_id" not in entry
    assert "mission_id" not in entry
    assert "id" not in entry


def test_multiple_seeds_choose_max_score(db_session, graph_layer):
    seed_a = "urn:research:project:seed-a"
    seed_b = "urn:research:project:seed-b"
    target = "urn:research:document:doc-max"
    _add_edge(db_session, seed_a, target, "contains")
    _add_edge(db_session, seed_b, target, "contains")

    results = [
        {"urn": seed_a, "score": 0.2},
        {"urn": seed_b, "score": 0.9},
    ]
    config = GraphLayerConfig(max_depth=1, decay_factor=1.0)
    layer = graph_layer.expand_from_results(results, top_k=2, config=config)

    target_entry = next(entry for entry in layer.results if entry["urn"] == target)
    assert target_entry["score"] == pytest.approx(0.9)


def test_cache_hits_recorded(db_session, graph_layer):
    seed_a = "urn:research:project:seed-cache-a"
    seed_b = "urn:research:project:seed-cache-b"
    mid = "urn:research:document:mid-cache"
    target = "urn:research:document:target-cache"
    _add_edge(db_session, seed_a, mid, "contains")
    _add_edge(db_session, seed_b, mid, "contains")
    _add_edge(db_session, mid, target, "references")

    layer = graph_layer.search(
        [seed_a, seed_b],
        config=GraphLayerConfig(max_depth=2),
    )

    # Global visited-set traversal avoids duplicate queueing of shared nodes.
    assert layer.metadata["cache_hits"] == 0
    assert layer.metadata["cache_misses"] >= 1


def test_shared_node_traversed_once_with_global_visited_set(db_session, graph_layer):
    seed_a = "urn:research:project:seed-global-a"
    seed_b = "urn:research:project:seed-global-b"
    mid = "urn:research:document:mid-global"
    leaf = "urn:research:document:leaf-global"
    _add_edge(db_session, seed_a, mid, "contains")
    _add_edge(db_session, seed_b, mid, "contains")
    _add_edge(db_session, mid, leaf, "references")

    layer = graph_layer.search([seed_a, seed_b], config=GraphLayerConfig(max_depth=2))

    edge_usage = layer.metadata["edge_type_usage"]
    assert edge_usage["contains"] == 2
    assert edge_usage["references"] == 1


def test_metadata_includes_depth_stats_edge_usage_and_seed_scores(db_session, graph_layer):
    seed = "urn:research:project:seed-metrics"
    mid = "urn:research:document:doc-metrics-mid"
    leaf = "urn:research:document:doc-metrics-leaf"
    _add_edge(db_session, seed, mid, "contains")
    _add_edge(db_session, mid, leaf, "references")

    layer = graph_layer.search(
        [seed],
        config=GraphLayerConfig(max_depth=2, decay_factor=0.7),
    )

    depth_stats = layer.metadata["depth_stats"]
    assert depth_stats["1"]["count"] == 1
    assert depth_stats["2"]["count"] == 1
    assert depth_stats["1"]["score_stats"]["min"] == pytest.approx(0.7)

    edge_usage = layer.metadata["edge_type_usage"]
    assert edge_usage["contains"] == 1
    assert edge_usage["references"] == 1

    seed_stats = layer.metadata["seed_score_stats"]
    assert seed_stats["count"] == 1
    assert seed_stats["score_stats"]["min"] == pytest.approx(1.0)


def test_seed_score_fallback_combined_score(db_session, graph_layer):
    seed = "urn:research:project:seed-combined"
    target = "urn:research:document:doc-combined"
    _add_edge(db_session, seed, target, "contains")

    results = [{"urn": seed, "combined_score": 0.6}]
    config = GraphLayerConfig(max_depth=1, decay_factor=0.5)
    layer = graph_layer.expand_from_results(results, top_k=1, config=config)

    entry = next(item for item in layer.results if item["urn"] == target)
    assert entry["score"] == pytest.approx(0.3)


def test_seed_score_fallback_rrf_score(db_session, graph_layer):
    seed = "urn:research:project:seed-rrf"
    target = "urn:research:document:doc-rrf"
    _add_edge(db_session, seed, target, "contains")

    results = [{"urn": seed, "rrf_score": 0.4}]
    config = GraphLayerConfig(max_depth=1, decay_factor=0.5)
    layer = graph_layer.expand_from_results(results, top_k=1, config=config)

    entry = next(item for item in layer.results if item["urn"] == target)
    assert entry["score"] == pytest.approx(0.2)


def test_expand_from_results_skips_unresolvable_seeds(graph_layer):
    layer = graph_layer.expand_from_results([{"content": "no ids"}], top_k=1)
    assert layer.results == []


def test_expand_from_results_top_k_limit(db_session, graph_layer):
    seed_a = "urn:research:project:seed-topk-a"
    seed_b = "urn:research:project:seed-topk-b"
    target_a = "urn:research:document:doc-topk-a"
    target_b = "urn:research:document:doc-topk-b"
    _add_edge(db_session, seed_a, target_a, "contains")
    _add_edge(db_session, seed_b, target_b, "contains")

    results = [{"urn": seed_a, "score": 0.2}, {"urn": seed_b, "score": 0.9}]
    layer = graph_layer.expand_from_results(results, top_k=1)

    urns = {entry["urn"] for entry in layer.results}
    assert target_a in urns
    assert target_b not in urns
