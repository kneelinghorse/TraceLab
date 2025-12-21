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
from app.services.pedr.graph_rag import GraphNode, GraphRAGHelper, GraphSubgraph
from app.services.pedr.semantic_protocol import URNGenerator


@pytest.fixture(scope="module", autouse=True)
def graph_rag_schema():
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


def test_extract_subgraph_empty_seeds_returns_empty(db_session):
    helper = GraphRAGHelper(session=db_session)
    subgraph = helper.extract_subgraph([])
    assert subgraph.nodes == []
    assert subgraph.edges == []


def test_extract_subgraph_depth_limit(db_session):
    helper = GraphRAGHelper(session=db_session)
    seed = "urn:research:project:seed-1"
    mid = "urn:research:document:doc-1"
    leaf = "urn:research:mission:leaf-1"
    _add_edge(db_session, seed, mid, "contains")
    _add_edge(db_session, mid, leaf, "references")

    subgraph = helper.extract_subgraph([seed], depth=1)
    urns = {node.urn for node in subgraph.nodes}

    assert seed in urns
    assert mid in urns
    assert leaf not in urns


def test_extract_subgraph_respects_max_nodes(db_session):
    helper = GraphRAGHelper(session=db_session)
    seed = "urn:research:project:seed-2"
    _add_edge(db_session, seed, "urn:research:document:doc-2", "contains")
    _add_edge(db_session, seed, "urn:research:document:doc-3", "contains")

    subgraph = helper.extract_subgraph([seed], depth=1, max_nodes=2)
    assert len(subgraph.nodes) <= 2


def test_extract_subgraph_includes_edges(db_session):
    helper = GraphRAGHelper(session=db_session)
    seed = "urn:research:project:seed-3"
    target = "urn:research:document:doc-4"
    _add_edge(db_session, seed, target, "contains")

    subgraph = helper.extract_subgraph([seed], depth=1)
    assert (seed, target, "contains") in subgraph.edges


def test_extract_subgraph_hydrates_chunk_content(db_session, project):
    helper = GraphRAGHelper(session=db_session)
    document, chunks = _create_document_with_chunks(db_session, project, chunk_count=1)
    chunk_urn = str(URNGenerator.for_chunk(str(document.id), 0))
    seed = "urn:research:project:seed-4"
    _add_edge(db_session, seed, chunk_urn, "contains")

    subgraph = helper.extract_subgraph([seed], depth=1)
    chunk_node = next(node for node in subgraph.nodes if node.urn == chunk_urn)
    assert chunk_node.content == "chunk-0"


def test_prune_by_relevance_prefers_overlap():
    pytest.importorskip("tiktoken")
    helper = GraphRAGHelper()
    node_relevant = GraphNode(
        urn="urn:research:document:rel-1",
        content="graph planning insights",
        entity_type="document",
        depth=1,
    )
    node_irrelevant = GraphNode(
        urn="urn:research:document:noise-1",
        content="lorem " * 500,
        entity_type="document",
        depth=2,
    )
    subgraph = GraphSubgraph(nodes=[node_relevant, node_irrelevant], edges=[])
    pruned = helper.prune_by_relevance(subgraph, query="graph planning", max_tokens=200)

    urns = {node.urn for node in pruned.nodes}
    assert "urn:research:document:rel-1" in urns
    assert "urn:research:document:noise-1" not in urns


def test_prune_by_relevance_zero_max_tokens():
    pytest.importorskip("tiktoken")
    helper = GraphRAGHelper()
    subgraph = GraphSubgraph(
        nodes=[
            GraphNode(
                urn="urn:research:document:doc-5",
                content="graph context",
                entity_type="document",
                depth=1,
            )
        ],
        edges=[],
    )
    pruned = helper.prune_by_relevance(subgraph, query="graph", max_tokens=0)
    assert pruned.nodes == []
    assert pruned.edges == []


def test_prune_by_relevance_filters_edges():
    pytest.importorskip("tiktoken")
    helper = GraphRAGHelper()
    node_a = GraphNode(
        urn="urn:research:document:doc-a",
        content="graph context",
        entity_type="document",
        depth=1,
    )
    node_b = GraphNode(
        urn="urn:research:document:doc-b",
        content="lorem " * 400,
        entity_type="document",
        depth=2,
    )
    subgraph = GraphSubgraph(
        nodes=[node_a, node_b],
        edges=[(node_a.urn, node_b.urn, "references")],
    )
    pruned = helper.prune_by_relevance(subgraph, query="graph", max_tokens=120)
    assert len(pruned.nodes) == 1
    assert pruned.edges == []


def test_linearize_includes_header_and_evidence():
    helper = GraphRAGHelper()
    document_id = str(uuid.uuid4())
    chunk_urn = str(URNGenerator.for_chunk(document_id, 0))
    node = GraphNode(
        urn=chunk_urn,
        content="BFS traversal is used for graph expansion.",
        entity_type="chunk",
        depth=1,
    )
    subgraph = GraphSubgraph(nodes=[node], edges=[])
    output = helper.linearize(subgraph)

    assert "## Related Context (via graph expansion)" in output
    assert f"Evidence from: {document_id}/chunk-0" in output
    assert "BFS traversal is used for graph expansion." in output


def test_linearize_orders_topologically():
    helper = GraphRAGHelper()
    node_a = GraphNode(
        urn="urn:research:project:alpha",
        content="Alpha",
        entity_type="project",
        depth=0,
    )
    node_b = GraphNode(
        urn="urn:research:document:beta",
        content="Beta",
        entity_type="document",
        depth=1,
    )
    subgraph = GraphSubgraph(
        nodes=[node_b, node_a],
        edges=[(node_a.urn, node_b.urn, "contains")],
    )
    output = helper.linearize(subgraph)

    index_a = output.index("### Project: Alpha")
    index_b = output.index("### Document: Beta")
    assert index_a < index_b


def test_linearize_handles_cycles():
    helper = GraphRAGHelper()
    node_a = GraphNode(
        urn="urn:research:project:cycle-a",
        content="Cycle A",
        entity_type="project",
        depth=0,
    )
    node_b = GraphNode(
        urn="urn:research:project:cycle-b",
        content="Cycle B",
        entity_type="project",
        depth=1,
    )
    subgraph = GraphSubgraph(
        nodes=[node_a, node_b],
        edges=[
            (node_a.urn, node_b.urn, "related_to"),
            (node_b.urn, node_a.urn, "related_to"),
        ],
    )
    output = helper.linearize(subgraph)

    assert "### Project: Cycle A" in output
    assert "### Project: Cycle B" in output
