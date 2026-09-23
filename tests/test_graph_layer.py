from __future__ import annotations

import uuid
from unittest.mock import MagicMock

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
    event,
)

from app.core.database import engine
from app.models import Document, DocumentChunk, GraphEdge, Mission, Project, Report
from app.models.types import GUID
from app.services.pedr.graph_layer import GraphLayerConfig, GraphLayerService, URNParser
from app.services.pedr.search_orchestrator import PEDRSearchOrchestrator
from app.services.pedr.semantic_protocol import URNGenerator


@pytest.fixture(scope="module", autouse=True)
def graph_layer_schema():
    metadata = MetaData()

    Project.__table__.to_metadata(metadata)
    Report.__table__.to_metadata(metadata)

    mission_table = Mission.__table__.to_metadata(metadata)
    for constraint in list(mission_table.constraints):
        if isinstance(constraint, CheckConstraint) and "jsonb_array_length" in str(
            constraint.sqltext
        ):
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
        UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_index"
        ),
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


@pytest.mark.parametrize("max_depth", [1, 2])
def test_depth_boundary_keeps_candidates_without_reading_their_edges(
    db_session, graph_layer, max_depth
):
    """Depth limits bound database work as well as the returned graph horizon."""
    seed = "urn:research:project:boundary-seed"
    mids = [f"urn:research:document:boundary-mid-{index}" for index in range(201)]
    leaves = [f"urn:research:document:boundary-leaf-{index}" for index in range(201)]
    outside = [f"urn:research:document:boundary-outside-{index}" for index in range(201)]
    db_session.add_all(
        GraphEdge(from_urn=source, to_urn=target, edge_type="contains", direction="out")
        for sources, targets in [([seed] * 201, mids), (mids, leaves), (leaves, outside)]
        for source, target in zip(sources, targets, strict=True)
    )
    db_session.commit()
    adjacency_reads = []

    def capture_adjacency_reads(conn, cursor, statement, parameters, context, executemany):
        if "FROM graph_edges" in statement and statement.lstrip().startswith("SELECT"):
            adjacency_reads.append(parameters)

    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", capture_adjacency_reads)
    try:
        layer = graph_layer.search(
            [seed],
            config=GraphLayerConfig(max_depth=max_depth, max_candidates=1000),
        )
    finally:
        event.remove(bind, "before_cursor_execute", capture_adjacency_reads)

    expected = set(mids) | (set(leaves) if max_depth == 2 else set())
    # The seed leads the ranking (RAG-4); every other result was reached from it.
    seed_entry, *reached = layer.results
    assert (seed_entry["urn"], seed_entry["depth"]) == (seed, 0)
    assert {entry["urn"] for entry in reached} == expected
    for entry in reached:
        depth = 1 if entry["urn"] in mids else 2
        assert entry["depth"] == depth
        assert entry["score"] == pytest.approx(0.7**depth)
        assert entry["seed_urn"] == seed
    # A frontier larger than one batch must never fetch terminal adjacency.
    queried_urns = {urn for parameters in adjacency_reads for urn in parameters}
    assert queried_urns == {seed} | (set(mids) if max_depth == 2 else set())
    assert len(adjacency_reads) <= (3 if max_depth == 2 else 1)
    assert layer.metadata["total_candidates"] == len(expected)
    assert layer.metadata["edge_type_usage"] == {"contains": len(expected)}


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
    # The cycle back does not add the seed again as a reached candidate: it
    # appears once, at depth 0 with its own score (RAG-4 ranks seeds first).
    seed_entries = [entry for entry in layer.results if entry["urn"] == seed]
    assert [(entry["depth"], entry["score"]) for entry in seed_entries] == [(0, 1.0)]


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


def test_metadata_includes_depth_stats_edge_usage_and_seed_scores(
    db_session, graph_layer
):
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


def test_seeds_lead_the_ranking_in_retrieval_order(db_session, graph_layer, project):
    """Seeds rank first in the order retrieval gave them, not by score (RAG-4).

    Seed scores mix scales: a lexical seed carries ts_rank_cd and a semantic seed
    a cosine. Ranked by score, the semantic seed's neighbour (0.66 x 0.7) would
    pass the lexical seed (0.05) that retrieval put first.
    """
    document, chunks = _create_document_with_chunks(db_session, project, chunk_count=3)
    lexical_seed, semantic_seed, neighbour = (
        str(URNGenerator.for_chunk(str(document.id), index)) for index in range(3)
    )
    _add_edge(db_session, semantic_seed, neighbour, "related_to")

    results = [
        {"document_id": str(document.id), "chunk_index": 0, "score": 0.05},
        {"document_id": str(document.id), "chunk_index": 1, "score": 0.66},
    ]
    layer = graph_layer.expand_from_results(
        results, top_k=2, config=GraphLayerConfig(max_depth=1)
    )

    assert [(entry["urn"], entry["depth"]) for entry in layer.results] == [
        (lexical_seed, 0),
        (semantic_seed, 0),
        (neighbour, 1),
    ]
    assert [entry["chunk_id"] for entry in layer.results] == [
        str(chunk.id) for chunk in chunks
    ]
    # Seeds are ranked, not reached: the metadata still counts reached chunks only.
    assert layer.metadata["total_candidates"] == 1


def test_best_match_keeps_first_place_over_its_graph_neighbours(db_session, project):
    """RAG-4, in the production shape: the best match ranks first with the graph on.

    On production the chunk that answers a question was semantic rank 1 and came
    15th with the graph layer on, because the layer never ranked its seeds: their
    neighbours (semantic rank 11 and worse, graph rank 2 or 3) took a graph share
    on top of their semantic one and the seed took none. Here the best match links
    to a neighbour at semantic rank 11, which that ranking put at graph rank 2
    (behind a semantic-rank-23 neighbour whose URN sorts first), and so first.
    """
    main = Document(
        id=uuid.UUID("b0000000-0000-0000-0000-000000000000"),
        project_id=project.id,
        name="Main",
        content="test",
    )
    side = Document(
        id=uuid.UUID("a0000000-0000-0000-0000-000000000000"),
        project_id=project.id,
        name="Side",
        content="test",
    )
    db_session.add_all([main, side])
    db_session.flush()
    # Semantic ranks 1-22 are chunks 0-21 of Main, rank 23 is chunk 0 of Side.
    placed = [(main, index) for index in range(22)] + [(side, 0)]
    rows = [
        DocumentChunk(document_id=document.id, chunk_index=index, content=f"text {rank}")
        for rank, (document, index) in enumerate(placed, start=1)
    ]
    db_session.add_all(rows)
    db_session.commit()
    semantic = [
        {
            "chunk_id": str(row.id),
            "content": row.content,
            "document_id": str(row.document_id),
            "project_id": str(project.id),
            "chunk_index": row.chunk_index,
            # Production cosines: 0.664 at rank 1, falling below 0.45 by rank 23.
            "score": round(0.664 - 0.01 * (rank - 1), 3),
        }
        for rank, row in enumerate(rows, start=1)
    ]
    best, neighbour, far = rows[0], rows[10], rows[22]
    for target in (neighbour, far):
        _add_edge(
            db_session,
            str(URNGenerator.for_chunk(str(best.document_id), best.chunk_index)),
            str(URNGenerator.for_chunk(str(target.document_id), target.chunk_index)),
            "related_to",
        )

    orchestrator = PEDRSearchOrchestrator(
        lexical_search=MagicMock(return_value=[]),
        semantic_search=MagicMock(return_value=semantic),
        graph_service=GraphLayerService(session=db_session),
        telemetry_enabled=False,
    )
    response = orchestrator.search(
        query="rag-4 best match keeps first place", top_k=23, enable_graph=True
    )

    ranked = {result.chunk_id: result for result in response.results}
    top = [
        (result.layer_ranks.get("semantic"), result.layer_ranks.get("graph"))
        for result in response.results[:3]
    ]
    assert response.results[0].chunk_id == str(best.id), (
        f"(semantic rank, graph rank) of the top three: {top}"
    )
    assert ranked[str(best.id)].layer_ranks == {"semantic": 1, "graph": 1}
    # The ten seeds hold the top ten in semantic order; the neighbour was reached
    # and ranks below every one of them.
    assert [result.chunk_id for result in response.results[:10]] == [
        str(row.id) for row in rows[:10]
    ]
    assert ranked[str(neighbour.id)].layer_ranks["semantic"] == 11
    assert "graph" in ranked[str(neighbour.id)].layer_ranks
    assert response.metadata.graph_candidates_expanded == 2
