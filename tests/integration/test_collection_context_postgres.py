"""Collection document context survives real PostgreSQL migration and paging."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command
from app.adapters.repositories.sqlalchemy_collection_context_repo import SQLAlchemyCollectionContextRepository
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.collection import Collection
from app.models.collection_document import CollectionDocument
from app.models.document import Document
from app.models.project import Project
from app.models.user import User
from app.services.collection_context import CollectionContextService

pytestmark = pytest.mark.integration
_HASH = "placeholder-not-a-real-hash"


def test_collection_context_migration_roundtrip(alembic_cfg, migration_db_url):
    engine = create_engine(migration_db_url)
    try:
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(engine)
        assert "instructions" in {column["name"] for column in inspector.get_columns("collections")}
        assert set(inspector.get_pk_constraint("collection_documents")["constrained_columns"]) == {"collection_id", "document_id"}
        assert {(fk["referred_table"], fk["options"]["ondelete"]) for fk in inspector.get_foreign_keys("collection_documents")} == {("collections", "CASCADE"), ("documents", "CASCADE")}
        command.downgrade(alembic_cfg, "045_user_favorites")
        assert "collection_documents" not in inspect(engine).get_table_names()
        assert "instructions" not in {column["name"] for column in inspect(engine).get_columns("collections")}
        command.upgrade(alembic_cfg, "head")
        assert "collection_documents" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_complete_scoped_context_and_cascade_on_postgres(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = User(email=f"{uuid4()}@example.test", display_name="Context author", password_hash=_HASH, role="member")
    other = User(email=f"{uuid4()}@example.test", display_name="Other author", password_hash=_HASH, role="member")
    db_session.add_all([user, other])
    db_session.flush()
    project = Project(name="Research sources", owner_id=user.id)
    collection = Collection(name="Source context", instructions="Preserve conflicting findings.", owner_id=user.id)
    db_session.add_all([project, collection])
    db_session.flush()
    documents = [Document(name=f"Source {index:03}", project_id=project.id, owner_id=user.id if index < 120 else other.id) for index in range(121)]
    db_session.add_all(documents)
    db_session.flush()
    db_session.add_all([CollectionDocument(collection_id=collection.id, document_id=doc.id) for doc in documents])
    db_session.commit()
    principal = AuthenticatedUser(user_id=user.id, email=user.email, display_name=user.display_name, role=user.role)
    repository = SQLAlchemyCollectionContextRepository()
    first = repository.documents(db_session, principal, collection.id, page=1, page_size=100)
    second = repository.documents(db_session, principal, collection.id, page=2, page_size=100)
    assert first.total == second.total == 121
    assert len(first.items) == 100 and len(second.items) == 21
    assert not ({doc.id for doc in first.items} & {doc.id for doc in second.items})
    seed = CollectionContextService(repository).seed(db_session, principal, collection.id)
    assert len(seed.references) == 121
    assert str(documents[-1].id) in seed.context["document_ids"]
    assert seed.background.startswith(collection.instructions)
    # Project ownership retains sibling reads; a move to a foreign project revokes them.
    private = Project(name="Private parent", owner_id=other.id)
    db_session.add(private)
    db_session.flush()
    documents[-1].project_id = private.id
    db_session.commit()
    seed = CollectionContextService(repository).seed(db_session, principal, collection.id)
    assert len(seed.references) == 120
    assert str(documents[-1].id) not in seed.context["document_ids"]
    repository.attach(db_session, principal, collection.id, documents[0].id)
    assert repository.documents(db_session, principal, collection.id, page=1, page_size=20).total == 120
    collection_id = collection.id
    db_session.delete(collection)
    db_session.commit()
    assert db_session.query(CollectionDocument).filter_by(collection_id=collection_id).count() == 0
    assert db_session.query(Document).filter_by(project_id=project.id).count() == 120
    assert db_session.query(Document).filter_by(project_id=private.id).count() == 1
