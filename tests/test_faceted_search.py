"""Tests for faceted search filtering and facet aggregation."""

from __future__ import annotations

from datetime import date

from app.models.document import Document
from app.models.tag import DocumentTag, Tag
from app.services.faceted_search import FacetedSearchService, FacetFilters


def _seed_documents(db_session, project):
    doc1 = Document(
        project_id=project.id,
        name="Executive Interview",
        file_type="transcript",
        source_type="interview",
        collection_date=date(2025, 1, 5),
    )
    doc2 = Document(
        project_id=project.id,
        name="Design Report",
        file_type="report",
        source_type="analysis",
        collection_date=date(2025, 2, 10),
    )
    db_session.add_all([doc1, doc2])
    db_session.commit()

    exec_tag = Tag(name="executive")
    design_tag = Tag(name="design")
    db_session.add_all([exec_tag, design_tag])
    db_session.commit()

    db_session.add_all(
        [
            DocumentTag(document_id=doc1.id, tag_id=exec_tag.id),
            DocumentTag(document_id=doc2.id, tag_id=design_tag.id),
        ]
    )
    db_session.commit()
    return doc1, doc2


def test_filter_chunks_by_document_type_and_tags(db_session, project):
    doc1, doc2 = _seed_documents(db_session, project)
    service = FacetedSearchService()
    chunks = [
        {
            "chunk_id": "chunk-a",
            "content": "Executive summary transcript content.",
            "document_id": str(doc1.id),
            "project_id": str(project.id),
            "chunk_index": 0,
            "source_type": "interview",
            "score": 0.9,
        },
        {
            "chunk_id": "chunk-b",
            "content": "Design research summary.",
            "document_id": str(doc2.id),
            "project_id": str(project.id),
            "chunk_index": 0,
            "source_type": "analysis",
            "score": 0.3,
        },
    ]
    filters = FacetFilters.from_kwargs(
        project_id=str(project.id),
        document_types=["transcript"],
        tags=["executive"],
    )

    filtered = service.filter_chunks(chunks, filters)

    assert len(filtered) == 1
    only_chunk = filtered[0]
    assert only_chunk["chunk_id"] == "chunk-a"
    assert only_chunk["document_type"] == "transcript"
    assert only_chunk["source_type"] == "interview"
    assert only_chunk["tags"] == ["executive"]
    assert only_chunk["collection_date"] == doc1.collection_date.isoformat()


def test_get_facets_scoped_by_filters(db_session, project):
    doc1, _ = _seed_documents(db_session, project)
    service = FacetedSearchService()
    filters = FacetFilters.from_kwargs(
        project_id=str(project.id),
        tags=["executive"],
    )

    facets = service.get_facets(filters)

    doc_types = {item["value"]: item["count"] for item in facets["document_types"]}
    assert doc_types == {"transcript": 1}
    assert facets["projects"][0]["count"] == 1
    assert facets["date_range"]["min"] == doc1.collection_date.isoformat()
    assert facets["date_range"]["max"] == doc1.collection_date.isoformat()
