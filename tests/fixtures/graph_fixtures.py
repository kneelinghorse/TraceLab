from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.models import Document, DocumentChunk, GraphEdge
from app.services.pedr.semantic_protocol import URNGenerator


@dataclass(frozen=True)
class SeededGraph:
    project_id: str
    project_urn: str
    documents: dict[str, Document]
    chunks: dict[str, DocumentChunk]
    urns: dict[str, str]
    edges: list[GraphEdge]


def _create_document_with_chunks(
    db_session, project_id: str, *, name: str, chunks: list[str]
):
    document = Document(
        project_id=project_id,
        name=name,
        content=" ".join(chunks),
    )
    db_session.add(document)
    db_session.flush()

    created_chunks: list[DocumentChunk] = []
    for index, content in enumerate(chunks):
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=content,
        )
        db_session.add(chunk)
        created_chunks.append(chunk)

    db_session.commit()
    return document, created_chunks


@pytest.fixture
def seeded_graph(db_session, project) -> SeededGraph:
    doc1, doc1_chunks = _create_document_with_chunks(
        db_session,
        str(project.id),
        name="Graph Fixture Doc 1",
        chunks=["Chunk one content", "Chunk two content"],
    )
    doc2, doc2_chunks = _create_document_with_chunks(
        db_session,
        str(project.id),
        name="Graph Fixture Doc 2",
        chunks=["Chunk three content"],
    )

    project_urn = str(URNGenerator.for_project(str(project.id)))
    doc1_urn = str(URNGenerator.for_document(str(doc1.id)))
    doc2_urn = str(URNGenerator.for_document(str(doc2.id)))
    chunk1_urn = str(URNGenerator.for_chunk(str(doc1.id), 0))
    chunk2_urn = str(URNGenerator.for_chunk(str(doc1.id), 1))
    chunk3_urn = str(URNGenerator.for_chunk(str(doc2.id), 0))

    edges = [
        GraphEdge.from_semantic_edge("contains", project_urn, doc1_urn),
        GraphEdge.from_semantic_edge("contains", project_urn, doc2_urn),
        GraphEdge.from_semantic_edge("contains", doc1_urn, chunk1_urn),
        GraphEdge.from_semantic_edge("contains", doc1_urn, chunk2_urn),
        GraphEdge.from_semantic_edge("contains", doc2_urn, chunk3_urn),
        GraphEdge.from_semantic_edge("related_to", chunk1_urn, chunk2_urn),
        GraphEdge.from_semantic_edge("related_to", chunk2_urn, chunk3_urn),
        GraphEdge.from_semantic_edge("references", chunk1_urn, chunk3_urn),
    ]
    db_session.add_all(edges)
    db_session.commit()

    return SeededGraph(
        project_id=str(project.id),
        project_urn=project_urn,
        documents={"doc1": doc1, "doc2": doc2},
        chunks={
            "chunk1": doc1_chunks[0],
            "chunk2": doc1_chunks[1],
            "chunk3": doc2_chunks[0],
        },
        urns={
            "project": project_urn,
            "doc1": doc1_urn,
            "doc2": doc2_urn,
            "chunk1": chunk1_urn,
            "chunk2": chunk2_urn,
            "chunk3": chunk3_urn,
        },
        edges=edges,
    )
