"""PEDR-1C tenant boundaries for collection children."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, call
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import collections as collections_api
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import (
    ROLE_MEMBER,
    AuthenticatedUser,
    create_access_token,
)
from app.main import app
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.project import Project
from app.models.user import User
from app.schemas.collection import CollectionItemCreate
from app.services.collection import (
    CollectionChunkForbiddenError,
    CollectionService,
)

_HASH = "placeholder-not-a-real-hash"


def _principal() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=uuid4(),
        email="member@example.com",
        display_name="member",
        role=ROLE_MEMBER,
    )


class _ExplodingDB:
    def query(self, *_args, **_kwargs):
        raise AssertionError("unrestricted collection routes must not query scope")


class _LegacyShapeService:
    """Expose only the pre-PEDR method signatures to catch accidental kwargs."""

    def __init__(self) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        self.collection_id = uuid4()
        self.chunk_id = uuid4()
        self.document_id = uuid4()
        self.collection = SimpleNamespace(
            id=self.collection_id,
            name="Legacy collection",
            description=None,
            created_at=now,
            updated_at=now,
        )
        self.item = SimpleNamespace(
            id=uuid4(),
            collection_id=self.collection_id,
            chunk_id=self.chunk_id,
            notes="legacy note",
            added_at=now,
            chunk=SimpleNamespace(
                content="legacy content",
                document_id=self.document_id,
            ),
        )
        self.calls: list[tuple] = []

    def list_collections(self, access_filter=None):
        self.calls.append(("list_collections", access_filter))
        return [self.collection]

    def get(self, collection_id):
        self.calls.append(("get", collection_id))
        return self.collection

    def get_item_count(self, collection_id):
        self.calls.append(("get_item_count", collection_id))
        return 1

    def get_items(self, collection_id):
        self.calls.append(("get_items", collection_id))
        return [self.item]

    def export_markdown(self, collection_id):
        self.calls.append(("export_markdown", collection_id))
        return "# Legacy collection\n"

    def add_chunk(self, collection_id, *, chunk_id, notes):
        self.calls.append(("add_chunk", collection_id, chunk_id, notes))
        return self.item

    def remove_chunk(self, collection_id, chunk_id):
        self.calls.append(("remove_chunk", collection_id, chunk_id))
        return True


def test_unrestricted_routes_preserve_legacy_child_service_call_shapes(monkeypatch):
    """A None scope omits every new service kwarg and resolves scope once per route."""
    monkeypatch.setattr(settings, "rbac_enabled", False)
    scope_calls = []

    def _scope(user, db):
        scope_calls.append((user, db))
        return None

    monkeypatch.setattr(collections_api, "accessible_project_ids", _scope)
    principal = _principal()
    db = _ExplodingDB()
    service = _LegacyShapeService()

    listed = collections_api.list_collections(
        current_user=principal,
        db=db,
        service=service,
    )
    detail = collections_api.get_collection(
        service.collection_id,
        current_user=principal,
        service=service,
        db=db,
    )
    exported = collections_api.export_collection(
        service.collection_id,
        current_user=principal,
        service=service,
        db=db,
    )
    added = collections_api.add_chunk_to_collection(
        service.collection_id,
        CollectionItemCreate(chunk_id=service.chunk_id, notes="legacy note"),
        current_user=principal,
        service=service,
        db=db,
    )
    removed = collections_api.remove_chunk_from_collection(
        service.collection_id,
        service.chunk_id,
        current_user=principal,
        service=service,
        db=db,
    )

    assert listed.data[0].item_count == 1
    assert detail.items[0].chunk_content == "legacy content"
    assert exported.body == b"# Legacy collection\n"
    assert added.chunk_id == service.chunk_id
    assert removed.status_code == 204
    assert len(scope_calls) == 5
    assert service.calls == [
        ("list_collections", None),
        ("get_item_count", service.collection_id),
        ("get", service.collection_id),
        ("get_items", service.collection_id),
        ("get", service.collection_id),
        ("export_markdown", service.collection_id),
        ("get", service.collection_id),
        (
            "add_chunk",
            service.collection_id,
            service.chunk_id,
            "legacy note",
        ),
        ("get", service.collection_id),
        ("remove_chunk", service.collection_id, service.chunk_id),
    ]


def _chainable_query(*, one_or_none=None, count=None):
    query = MagicMock()
    query.filter.return_value = query
    query.join.return_value = query
    query.with_for_update.return_value = query
    query.one_or_none.return_value = one_or_none
    query.count.return_value = count
    return query


def test_scoped_add_locks_authoritative_parent_and_chunk_document_lookup():
    """Scoped validation and insertion share locks in the service transaction."""
    collection_id = uuid4()
    chunk_id = uuid4()
    project_id = uuid4()
    parent_query = _chainable_query(one_or_none=SimpleNamespace(id=collection_id))
    target_chunk = SimpleNamespace(id=chunk_id)
    target_query = _chainable_query(one_or_none=(target_chunk, project_id))
    count_query = _chainable_query(count=0)
    session = MagicMock()
    session.query.side_effect = [parent_query, target_query, count_query]
    service = CollectionService(session_factory=lambda: session)

    item = service.add_chunk(
        collection_id,
        chunk_id=chunk_id,
        notes="scoped note",
        accessible_project_ids=[project_id],
    )

    assert item.collection_id == str(collection_id)
    assert item.chunk_id == str(chunk_id)
    parent_query.with_for_update.assert_called_once_with(of=Collection)
    target_query.with_for_update.assert_called_once_with()
    assert session.method_calls[-4:] == [
        call.add(item),
        call.commit(),
        call.refresh(item),
        call.close(),
    ]


def test_scoped_foreign_add_rolls_back_before_any_insert():
    """A 403 verdict leaves no partial child mutation in the service transaction."""
    collection_id = uuid4()
    chunk_id = uuid4()
    allowed_project_id = uuid4()
    foreign_project_id = uuid4()
    parent_query = _chainable_query(one_or_none=SimpleNamespace(id=collection_id))
    target_query = _chainable_query(
        one_or_none=(SimpleNamespace(id=chunk_id), foreign_project_id)
    )
    session = MagicMock()
    session.query.side_effect = [parent_query, target_query]
    service = CollectionService(session_factory=lambda: session)

    with pytest.raises(CollectionChunkForbiddenError):
        service.add_chunk(
            collection_id,
            chunk_id=chunk_id,
            accessible_project_ids=[allowed_project_id],
        )

    session.rollback.assert_called_once_with()
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.close.assert_called_once_with()


def _user(db, *, email: str) -> User:
    user = User(
        email=email,
        display_name=email.split("@", maxsplit=1)[0],
        password_hash=_HASH,
        role=ROLE_MEMBER,
    )
    db.add(user)
    db.flush()
    return user


def _project(db, *, name: str, owner_id: UUID) -> Project:
    project = Project(name=name, owner_id=owner_id)
    db.add(project)
    db.flush()
    return project


def _chunk(
    db,
    *,
    project_id: UUID,
    content: str,
    deleted: bool = False,
) -> DocumentChunk:
    document = Document(
        project_id=project_id,
        name=f"{content} document",
        file_type="report",
        source_type="report",
        deleted_at=datetime.now(UTC).replace(tzinfo=None) if deleted else None,
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content=content,
    )
    db.add(chunk)
    db.flush()
    return chunk


def _item_count(collection_id: UUID) -> int:
    session = SessionLocal()
    try:
        return (
            session.query(CollectionItem)
            .filter(CollectionItem.collection_id == collection_id)
            .count()
        )
    finally:
        session.close()


def _has_item(collection_id: UUID, chunk_id: UUID) -> bool:
    session = SessionLocal()
    try:
        return (
            session.query(CollectionItem)
            .filter(
                CollectionItem.collection_id == collection_id,
                CollectionItem.chunk_id == chunk_id,
            )
            .one_or_none()
            is not None
        )
    finally:
        session.close()


@pytest.fixture
def rbac_on(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)


def test_mixed_collection_scopes_reads_exports_and_child_mutations(
    db_session,
    rbac_on,
):
    """A readable parent never grants access to foreign children it already contains."""
    caller = _user(db_session, email="collection-owner@example.com")
    other = _user(db_session, email="foreign-owner@example.com")
    allowed_project = _project(
        db_session,
        name="Allowed project",
        owner_id=caller.id,
    )
    foreign_project = _project(
        db_session,
        name="Foreign project",
        owner_id=other.id,
    )
    allowed = _chunk(
        db_session,
        project_id=allowed_project.id,
        content="allowed collection content",
    )
    allowed_candidate = _chunk(
        db_session,
        project_id=allowed_project.id,
        content="new allowed content",
    )
    foreign_legacy = _chunk(
        db_session,
        project_id=foreign_project.id,
        content="foreign legacy secret",
    )
    foreign_candidate = _chunk(
        db_session,
        project_id=foreign_project.id,
        content="foreign candidate secret",
    )
    deleted = _chunk(
        db_session,
        project_id=allowed_project.id,
        content="soft-deleted secret",
        deleted=True,
    )
    collection = Collection(name="Mixed legacy", owner_id=caller.id)
    db_session.add(collection)
    db_session.flush()
    db_session.add_all(
        [
            CollectionItem(
                collection_id=collection.id,
                chunk_id=allowed.id,
                notes="allowed note",
            ),
            CollectionItem(
                collection_id=collection.id,
                chunk_id=foreign_legacy.id,
                notes="foreign note secret",
            ),
            CollectionItem(
                collection_id=collection.id,
                chunk_id=deleted.id,
                notes="deleted note secret",
            ),
        ]
    )
    db_session.commit()

    # None is the legacy/unrestricted contract: even old foreign and deleted
    # children remain byte-for-byte visible to privileged/flag-off callers.
    service = CollectionService()
    assert service.get_item_count(collection.id) == 3
    assert {item.chunk_id for item in service.get_items(collection.id)} == {
        allowed.id,
        foreign_legacy.id,
        deleted.id,
    }
    unrestricted_export = service.export_markdown(collection.id)
    assert unrestricted_export is not None
    assert "allowed collection content" in unrestricted_export
    assert "foreign legacy secret" in unrestricted_export
    assert "soft-deleted secret" in unrestricted_export

    # Empty scope fails closed for every child read/removal while retaining parent
    # export metadata. It must not delete a legacy child as a side effect.
    assert service.get_items(collection.id, accessible_project_ids=[]) == []
    assert service.get_item_count(collection.id, accessible_project_ids=[]) == 0
    assert not service.remove_chunk(
        collection.id,
        foreign_legacy.id,
        accessible_project_ids=[],
    )
    empty_export = service.export_markdown(
        collection.id,
        accessible_project_ids=[],
    )
    assert empty_export is not None
    assert "**Total Chunks:** 0" in empty_export
    assert "foreign legacy secret" not in empty_export
    assert _has_item(collection.id, foreign_legacy.id)

    headers = {
        "Authorization": (
            f"Bearer {create_access_token(subject=str(caller.id))}"
        )
    }
    with TestClient(app) as client:
        detail_response = client.get(
            f"/api/v1/collections/{collection.id}",
            headers=headers,
        )
        list_response = client.get("/api/v1/collections", headers=headers)
        export_response = client.get(
            f"/api/v1/collections/{collection.id}/export",
            headers=headers,
        )

        foreign_add = client.post(
            f"/api/v1/collections/{collection.id}/chunks",
            json={"chunk_id": str(foreign_candidate.id)},
            headers=headers,
        )
        missing_add = client.post(
            f"/api/v1/collections/{collection.id}/chunks",
            json={"chunk_id": str(uuid4())},
            headers=headers,
        )
        deleted_add = client.post(
            f"/api/v1/collections/{collection.id}/chunks",
            json={"chunk_id": str(deleted.id)},
            headers=headers,
        )
        allowed_add = client.post(
            f"/api/v1/collections/{collection.id}/chunks",
            json={"chunk_id": str(allowed_candidate.id), "notes": "new note"},
            headers=headers,
        )
        foreign_remove = client.delete(
            f"/api/v1/collections/{collection.id}/chunks/{foreign_legacy.id}",
            headers=headers,
        )
        allowed_remove = client.delete(
            f"/api/v1/collections/{collection.id}/chunks/{allowed_candidate.id}",
            headers=headers,
        )

    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["item_count"] == 1
    assert [item["chunk_id"] for item in detail["items"]] == [str(allowed.id)]
    assert detail["items"][0]["notes"] == "allowed note"

    assert list_response.status_code == 200, list_response.text
    listed = next(
        row
        for row in list_response.json()["data"]
        if row["id"] == str(collection.id)
    )
    assert listed["item_count"] == 1

    assert export_response.status_code == 200, export_response.text
    assert "**Total Chunks:** 1" in export_response.text
    assert "allowed collection content" in export_response.text
    assert "allowed note" in export_response.text
    assert "foreign legacy secret" not in export_response.text
    assert "foreign note secret" not in export_response.text
    assert "soft-deleted secret" not in export_response.text

    assert foreign_add.status_code == 403
    assert foreign_add.json() == {"detail": "You do not have access to this chunk."}
    assert missing_add.status_code == 404
    assert missing_add.json() == {"detail": "Chunk not found."}
    assert deleted_add.status_code == 404
    assert deleted_add.json() == {"detail": "Chunk not found."}
    assert not _has_item(collection.id, foreign_candidate.id)
    assert _item_count(collection.id) == 3

    assert allowed_add.status_code == 201, allowed_add.text
    assert allowed_add.json()["chunk_id"] == str(allowed_candidate.id)
    assert foreign_remove.status_code == 404
    assert _has_item(collection.id, foreign_legacy.id)
    assert allowed_remove.status_code == 204
    assert not _has_item(collection.id, allowed_candidate.id)
    assert _item_count(collection.id) == 3
