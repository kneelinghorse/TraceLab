"""Regression coverage for database performance safeguards."""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.document import Document
from app.services.document_query_service import DocumentQueryService


def test_indexes_exist_for_hot_tables(db_session):
    """Ensure critical indexes for high-traffic queries are defined."""
    inspector = inspect(db_session.bind)

    def index_names(table: str) -> set[str]:
        return {entry["name"] for entry in inspector.get_indexes(table)}

    assert "idx_documents_project_id" in index_names("documents")
    assert "idx_document_chunks_document_id" in index_names("document_chunks")
    assert "idx_document_chunks_embedding_id" in index_names("document_chunks")
    assert "idx_insights_project_id" in index_names("insights")
    assert "idx_insight_sources_chunk_id" in index_names("insight_sources")
    assert "idx_missions_project_status" in index_names("missions")


def test_document_listing_defers_large_columns(db_session, project):
    """List endpoint should not hydrate heavyweight document payloads."""
    document = Document(
        project_id=project.id,
        name="Extremely Long Report",
        content="x" * 1024,
        raw_content=b"y" * 2048,
    )
    db_session.add(document)
    db_session.commit()
    db_session.expire_all()

    service = DocumentQueryService()
    documents, meta = service.list_documents(
        db_session,
        page=1,
        page_size=10,
        project_id=project.id,
    )

    assert meta.total == 1
    assert len(documents) == 1

    state = inspect(documents[0])
    assert "content" in state.unloaded
    assert "raw_content" in state.unloaded
