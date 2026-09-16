"""Postgres enforces what SQLite ignores: removing a collected chunk must lock only the item row.

CollectionItem.chunk is eager-loaded through a LEFT OUTER JOIN, so this is the same defect class
that took mission notifications down in production on 2026-09-15 (see
test_notifications_postgres.py). SQLite silently ignores FOR UPDATE, and the unit coverage in
tests/test_pedr_collection_scope.py asserts against a mocked query, so neither can see it.
Revert the ``of=CollectionItem`` in CollectionService.remove_chunk and this test fails with
``FeatureNotSupported: FOR UPDATE cannot be applied to the nullable side of an outer join``.
"""

from uuid import uuid4

from sqlalchemy.orm import sessionmaker

from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.project import Project
from app.services.collection import CollectionService


def test_removing_a_scoped_chunk_locks_only_the_item_row_on_postgres(db_session):
    project = Project(name=f"Locking {uuid4().hex[:6]}")
    db_session.add(project)
    db_session.flush()
    document = Document(project_id=project.id, name="source.pdf")
    db_session.add(document)
    db_session.flush()
    chunk = DocumentChunk(document_id=document.id, chunk_index=0, content="The evidence")
    collection = Collection(name=f"Evidence {uuid4().hex[:6]}")
    db_session.add_all([chunk, collection])
    db_session.flush()
    db_session.add(CollectionItem(collection_id=collection.id, chunk_id=chunk.id))
    db_session.commit()

    # Share the test's connection so the service's own commits stay inside the rolled-back
    # transaction, exactly as the API fixture does.
    service = CollectionService(
        session_factory=sessionmaker(
            bind=db_session.get_bind(), join_transaction_mode="create_savepoint"
        )
    )

    removed = service.remove_chunk(
        collection.id, chunk.id, accessible_project_ids=[project.id]
    )

    assert removed is True
    assert (
        db_session.query(CollectionItem)
        .filter(CollectionItem.collection_id == collection.id)
        .count()
        == 0
    )
