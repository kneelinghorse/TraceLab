"""PostgreSQL concurrency contract for keyed evidence-note upserts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app.models.evidence_ledger import LedgerNote
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.evidence_ledger import NoteUpsertRequest
from app.services.evidence_ledger import EvidenceLedgerService

pytestmark = pytest.mark.integration
_HASH = "placeholder-not-a-real-hash"


def test_competing_note_inserts_retry_as_one_complete_replacement(pg_engine) -> None:
    """Two sessions may create one key concurrently without a 500 or mixed ownership."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    seed = session_factory()
    first_workspace = Workspace(name=f"First note space {uuid4().hex}")
    retry_workspace = Workspace(name=f"Retry note space {uuid4().hex}")
    first_owner = User(
        email=f"note-first-{uuid4().hex}@example.test",
        display_name="First note writer",
        password_hash=_HASH,
        role="member",
    )
    retry_owner = User(
        email=f"note-retry-{uuid4().hex}@example.test",
        display_name="Retry note writer",
        password_hash=_HASH,
        role="member",
    )
    seed.add_all((first_workspace, retry_workspace, first_owner, retry_owner))
    seed.flush()
    project = Project(
        name=f"Concurrent note project {uuid4().hex}",
        owner_id=first_owner.id,
        workspace_id=first_workspace.id,
    )
    seed.add(project)
    seed.commit()
    project_id = project.id
    owner_ids = (first_owner.id, retry_owner.id)
    workspace_ids = (first_workspace.id, retry_workspace.id)
    seed.close()

    note_key = "concurrent-working-note"
    session_key = f"concurrent-session-{uuid4().hex}"
    first_flushes = Barrier(2)
    first_committed = Event()

    def coordinate_first_flush(db: Session, *, wait_for_first: bool) -> None:
        state = {"pending": True}

        @event.listens_for(db, "before_flush")
        def before_first_flush(_session, _flush_context, _instances) -> None:
            if not state["pending"]:
                return
            state["pending"] = False
            first_flushes.wait(timeout=5)
            if wait_for_first and not first_committed.wait(timeout=5):
                raise TimeoutError("first note writer did not commit")

        if not wait_for_first:

            @event.listens_for(db, "after_commit")
            def release_retry_writer(_session) -> None:
                first_committed.set()

    def write_note(
        *,
        content: str,
        tags: list[str],
        owner_id: UUID,
        workspace_id: UUID,
        wait_for_first: bool,
    ) -> dict[str, object]:
        db = session_factory()
        coordinate_first_flush(db, wait_for_first=wait_for_first)
        try:
            note = EvidenceLedgerService().upsert_note(
                db,
                note_key,
                NoteUpsertRequest(
                    project_id=project_id,
                    session_key=session_key,
                    content=content,
                    tags=tags,
                ),
                owner_id=owner_id,
                workspace_id=workspace_id,
            )
            return {
                "id": note.id,
                "content": note.content,
                "tags": note.tags,
                "origin": note.origin,
                "owner_id": note.owner_id,
                "workspace_id": note.workspace_id,
            }
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(
                write_note,
                content="First writer content",
                tags=["first"],
                owner_id=owner_ids[0],
                workspace_id=workspace_ids[0],
                wait_for_first=False,
            )
            retry_future = executor.submit(
                write_note,
                content="Retry writer content",
                tags=["retry", "complete"],
                owner_id=owner_ids[1],
                workspace_id=workspace_ids[1],
                wait_for_first=True,
            )
            first_result = first_future.result(timeout=10)
            retry_result = retry_future.result(timeout=10)

        assert first_result["id"] == retry_result["id"]
        assert retry_result == {
            "id": first_result["id"],
            "content": "Retry writer content",
            "tags": ["retry", "complete"],
            "origin": "mcp-agent",
            "owner_id": owner_ids[1],
            "workspace_id": workspace_ids[1],
        }

        verify = session_factory()
        try:
            notes = (
                verify.query(LedgerNote)
                .filter(
                    LedgerNote.project_id == project_id,
                    LedgerNote.session_key == session_key,
                    LedgerNote.note_key == note_key,
                )
                .all()
            )
            assert len(notes) == 1
            assert notes[0].content == "Retry writer content"
            assert notes[0].tags == ["retry", "complete"]
            assert notes[0].origin == "mcp-agent"
            assert notes[0].owner_id == owner_ids[1]
            assert notes[0].workspace_id == workspace_ids[1]
        finally:
            verify.close()
    finally:
        cleanup = session_factory()
        try:
            cleanup.query(LedgerNote).filter(LedgerNote.project_id == project_id).delete(synchronize_session=False)
            cleanup.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
            cleanup.query(User).filter(User.id.in_(owner_ids)).delete(synchronize_session=False)
            cleanup.query(Workspace).filter(Workspace.id.in_(workspace_ids)).delete(synchronize_session=False)
            cleanup.commit()
        finally:
            cleanup.close()
