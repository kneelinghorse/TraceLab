"""ORG-1 PostgreSQL: additive migration and concurrent accepts create one artifact."""

import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.idempotency import IdempotencyRecord
from app.models.project import Project
from app.models.user import User
from app.schemas.librarian_collections import CollectionAcceptRequest
from app.services.collection import CollectionService
from app.services.librarian import LibrarianService
from app.services.librarian_collections import accept_collection, draft_collections
from app.services.librarian_model import ModelReply

pytestmark = pytest.mark.integration


def test_collection_review_migration_preserves_legacy_and_downgrades(alembic_cfg, migration_db_url):
    command.upgrade(alembic_cfg, "054_description_provenance")
    engine = create_engine(migration_db_url)
    identity = uuid4()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO collections (id,name,description) VALUES (:id,'Legacy','Human description')"), {"id": identity})
    command.upgrade(alembic_cfg, "head")
    with engine.begin() as connection:
        row = connection.execute(text("SELECT description,generation_provenance FROM collections WHERE id=:id"), {"id": identity}).one()
        assert tuple(row) == ("Human description", None)
        connection.execute(text("UPDATE collections SET generation_provenance='{}'::jsonb WHERE id=:id"), {"id": identity})
    assert "review_position" in {c["name"] for c in inspect(engine).get_columns("collection_items")}
    command.downgrade(alembic_cfg, "054_description_provenance")
    assert "generation_provenance" not in {c["name"] for c in inspect(engine).get_columns("collections")}
    assert "review_position" not in {c["name"] for c in inspect(engine).get_columns("collection_items")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT description FROM collections WHERE id=:id"), {"id": identity}).scalar() == "Human description"
    command.upgrade(alembic_cfg, "head")
    engine.dispose()


def test_concurrent_accepts_share_receipt_collection_and_reviewed_order(pg_engine, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", False)
    factory = sessionmaker(bind=pg_engine)
    with factory.begin() as db:
        user = User(email=f"{uuid4()}@example.test", display_name="Collection review", password_hash=str(uuid4()), role="member")
        db.add(user)
        db.flush()
        project = Project(name="Concurrent collection", owner_id=user.id)
        db.add(project)
        db.flush()
        doc = Document(name="Sources", project_id=project.id, owner_id=user.id)
        db.add(doc)
        db.flush()
        chunks = [DocumentChunk(document_id=doc.id, chunk_index=i, content=f"Source {i} describes onboarding navigation.") for i in range(3)]
        db.add_all(chunks)
        db.flush()
        project_id, user_id = project.id, user.id
        expected = [str(chunks[i].id) for i in (2, 0, 1)]
        principal = AuthenticatedUser(user_id=user.id, email=user.email, display_name=user.display_name, role=user.role)
    model = Mock(model_name="isolated-collection-model")
    model.complete.return_value = ModelReply(content=json.dumps({"groups": [
        {"name": "Navigation", "description": "Review source navigation", "rationale": "Sources support this theme [3] [1] [2].", "members": [3, 1, 2]},
    ]}))
    with factory() as db:
        proposal = draft_collections(db, principal, db.get(Project, project_id), "Group feedback", LibrarianService(model_factory=lambda: model))
    group = proposal["groups"][0]
    request = CollectionAcceptRequest(project_id=project_id, proposal_token=group["proposal_token"], name=group["name"], description=group["description"], member_ids=expected)
    service = CollectionService(session_factory=factory)
    def accept():
        with factory() as db:
            return accept_collection(db, principal, db.get(Project, project_id), request, service)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(accept) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert results[0] == results[1]
    assert results[0]["state"] == "saved"
    assert results[0]["completed_member_ids"] == expected
    with factory() as db:
        collection = db.query(Collection).filter(Collection.owner_id == user_id).one()
        assert collection.generation_provenance["completed_at"]
        assert db.query(CollectionItem).filter(CollectionItem.collection_id == collection.id).count() == 3
        assert db.query(IdempotencyRecord).filter(IdempotencyRecord.key.like(f"librarian-collection:{user_id}:%")).count() == 1
    assert [str(item.chunk_id) for item in service.get_items(results[0]["collection_id"], accessible_project_ids=[project_id])] == expected
    assert model.complete.call_count == 1
