"""PostgreSQL regressions for scoped collection-child mutation atomicity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from queue import Queue
from threading import Event, Thread, current_thread
from time import monotonic, sleep
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import sessionmaker

from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.project import Project
from app.services.collection import (
    CollectionChunkForbiddenError,
    CollectionChunkNotFoundError,
    CollectionService,
)

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class _ScopedAddRows:
    allowed_project_id: UUID
    foreign_project_id: UUID
    race_collection_id: UUID
    rejection_collection_id: UUID
    first_chunk_id: UUID
    second_chunk_id: UUID
    foreign_chunk_id: UUID
    deleted_chunk_id: UUID


def _add_chunk_row(
    session,
    *,
    project_id: UUID,
    content: str,
    deleted: bool = False,
) -> UUID:
    document = Document(
        project_id=project_id,
        name=f"{content} document",
        file_type="report",
        source_type="report",
        deleted_at=datetime.now(UTC).replace(tzinfo=None) if deleted else None,
    )
    session.add(document)
    session.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content=content,
    )
    session.add(chunk)
    session.flush()
    return chunk.id


@pytest.fixture
def scoped_add_rows(pg_engine):
    """Commit isolated rows so independent service transactions can race."""
    session_factory = sessionmaker(bind=pg_engine)
    session = session_factory()
    allowed_project = Project(name=f"Allowed race project {uuid4()}")
    foreign_project = Project(name=f"Foreign race project {uuid4()}")
    race_collection = Collection(name=f"Race collection {uuid4()}")
    rejection_collection = Collection(name=f"Rejection collection {uuid4()}")
    session.add_all(
        [
            allowed_project,
            foreign_project,
            race_collection,
            rejection_collection,
        ]
    )
    session.flush()
    rows = _ScopedAddRows(
        allowed_project_id=allowed_project.id,
        foreign_project_id=foreign_project.id,
        race_collection_id=race_collection.id,
        rejection_collection_id=rejection_collection.id,
        first_chunk_id=_add_chunk_row(
            session,
            project_id=allowed_project.id,
            content="first allowed race chunk",
        ),
        second_chunk_id=_add_chunk_row(
            session,
            project_id=allowed_project.id,
            content="second allowed race chunk",
        ),
        foreign_chunk_id=_add_chunk_row(
            session,
            project_id=foreign_project.id,
            content="foreign race secret",
        ),
        deleted_chunk_id=_add_chunk_row(
            session,
            project_id=allowed_project.id,
            content="deleted race secret",
            deleted=True,
        ),
    )
    session.commit()
    session.close()

    try:
        yield rows
    finally:
        cleanup = session_factory()
        try:
            cleanup.query(Collection).filter(
                Collection.id.in_(
                    [rows.race_collection_id, rows.rejection_collection_id]
                )
            ).delete(synchronize_session=False)
            cleanup.query(Project).filter(
                Project.id.in_([rows.allowed_project_id, rows.foreign_project_id])
            ).delete(synchronize_session=False)
            cleanup.commit()
        except Exception:
            cleanup.rollback()
            raise
        finally:
            cleanup.close()


def _is_collection_parent_lock(statement: str) -> bool:
    normalized = " ".join(statement.lower().split())
    return "from collections" in normalized and "for update of collections" in normalized


def _wait_for_postgres_lock(pg_engine, backend_pid: int, *, timeout: float) -> dict[str, Any]:
    """Wait until PostgreSQL reports the second service transaction as lock-blocked."""
    deadline = monotonic() + timeout
    last_state: dict[str, Any] = {}
    while monotonic() < deadline:
        with pg_engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT state, wait_event_type, wait_event, query
                        FROM pg_stat_activity
                        WHERE pid = :backend_pid
                        """
                    ),
                    {"backend_pid": backend_pid},
                )
                .mappings()
                .one_or_none()
            )
        if row is not None:
            last_state = dict(row)
            if row["wait_event_type"] == "Lock":
                return last_state
        sleep(0.01)
    pytest.fail(
        "second scoped add never blocked on the collection parent lock; "
        f"last pg_stat_activity state={last_state!r}"
    )


def test_scoped_add_serializes_limit_check_and_insert(
    pg_engine,
    scoped_add_rows: _ScopedAddRows,
):
    """The parent lock makes a one-slot collection admit exactly one raced child."""
    session_factory = sessionmaker(bind=pg_engine)
    service = CollectionService(
        session_factory=session_factory,
        max_chunks_per_collection=1,
    )
    first_locked = Event()
    release_first = Event()
    second_attempted = Event()
    second_backend_pid: dict[str, int] = {}
    outcomes: Queue[tuple[str, str, Any]] = Queue()
    thread_suffix = uuid4().hex
    first_name = f"collection-add-first-{thread_suffix}"
    second_name = f"collection-add-second-{thread_suffix}"

    def before_cursor_execute(
        _connection,
        cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if current_thread().name == second_name and _is_collection_parent_lock(
            statement
        ):
            second_backend_pid["value"] = cursor.connection.get_backend_pid()
            second_attempted.set()

    def after_cursor_execute(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if current_thread().name == first_name and _is_collection_parent_lock(
            statement
        ):
            first_locked.set()
            if not release_first.wait(timeout=10):
                raise AssertionError("test did not release the first collection lock")

    def add_chunk(label: str, chunk_id: UUID) -> None:
        try:
            item = service.add_chunk(
                scoped_add_rows.race_collection_id,
                chunk_id=chunk_id,
                accessible_project_ids=[scoped_add_rows.allowed_project_id],
            )
        except Exception as error:
            outcomes.put((label, "error", error))
        else:
            outcomes.put(
                (
                    label,
                    "ok",
                    {"id": item.id, "chunk_id": item.chunk_id},
                )
            )

    first = Thread(
        target=add_chunk,
        args=("first", scoped_add_rows.first_chunk_id),
        name=first_name,
    )
    second = Thread(
        target=add_chunk,
        args=("second", scoped_add_rows.second_chunk_id),
        name=second_name,
    )
    event.listen(pg_engine, "before_cursor_execute", before_cursor_execute)
    event.listen(pg_engine, "after_cursor_execute", after_cursor_execute)
    try:
        first.start()
        assert first_locked.wait(timeout=10), "first add never acquired the parent lock"

        second.start()
        assert second_attempted.wait(timeout=10), "second add never attempted the parent lock"
        blocked = _wait_for_postgres_lock(
            pg_engine,
            second_backend_pid["value"],
            timeout=10,
        )
        assert "for update of collections" in blocked["query"].lower()

        release_first.set()
        first.join(timeout=10)
        second.join(timeout=10)
        assert not first.is_alive()
        assert not second.is_alive()
    finally:
        release_first.set()
        first.join(timeout=10)
        second.join(timeout=10)
        event.remove(pg_engine, "before_cursor_execute", before_cursor_execute)
        event.remove(pg_engine, "after_cursor_execute", after_cursor_execute)

    results = {label: (status, value) for label, status, value in outcomes.queue}
    assert results["first"][0] == "ok"
    assert results["first"][1]["chunk_id"] == scoped_add_rows.first_chunk_id
    assert results["second"][0] == "error"
    assert isinstance(results["second"][1], ValueError)
    assert str(results["second"][1]) == (
        "Collection has reached the maximum of 1 chunks."
    )

    verify = session_factory()
    try:
        items = (
            verify.query(CollectionItem)
            .filter(
                CollectionItem.collection_id == scoped_add_rows.race_collection_id
            )
            .all()
        )
        assert [item.chunk_id for item in items] == [scoped_add_rows.first_chunk_id]
    finally:
        verify.close()


def test_scoped_add_rejects_foreign_and_deleted_chunks_without_partial_rows(
    pg_engine,
    scoped_add_rows: _ScopedAddRows,
):
    """Authoritative live-document scope checks fail before either invalid insert."""
    session_factory = sessionmaker(bind=pg_engine)
    service = CollectionService(
        session_factory=session_factory,
        max_chunks_per_collection=1,
    )

    with pytest.raises(
        CollectionChunkForbiddenError,
        match="You do not have access to this chunk",
    ):
        service.add_chunk(
            scoped_add_rows.rejection_collection_id,
            chunk_id=scoped_add_rows.foreign_chunk_id,
            accessible_project_ids=[scoped_add_rows.allowed_project_id],
        )

    with pytest.raises(CollectionChunkNotFoundError, match="Chunk not found"):
        service.add_chunk(
            scoped_add_rows.rejection_collection_id,
            chunk_id=scoped_add_rows.deleted_chunk_id,
            accessible_project_ids=[scoped_add_rows.allowed_project_id],
        )

    verify = session_factory()
    try:
        assert (
            verify.query(CollectionItem)
            .filter(
                CollectionItem.collection_id
                == scoped_add_rows.rejection_collection_id
            )
            .count()
            == 0
        )
    finally:
        verify.close()
