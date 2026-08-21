"""Real-PostgreSQL retrieval and source-upsert contracts for LEDGER-3."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from app.models.evidence_ledger import LedgerEntry, LedgerSource
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.evidence_ledger import CaptureRequest
from app.services.evidence_ledger import EvidenceLedgerService

pytestmark = pytest.mark.integration
_HASH = "placeholder-not-a-real-hash"


def _capture_request(
    project_id: UUID,
    *,
    session_key: str,
    claim: str,
    source_url: str,
    summary: str | None = None,
    snippet: str | None = None,
    query: str | None = None,
) -> CaptureRequest:
    return CaptureRequest.model_validate(
        {
            "project_id": str(project_id),
            "session_key": session_key,
            "entries": [
                {
                    "claim": claim,
                    "summary": summary,
                    "source_url": source_url,
                    "snippet": snippet,
                    "query": query,
                    "disposition": "supporting",
                }
            ],
        }
    )


def _two_source_capture_request(
    project_id: UUID,
    *,
    session_key: str,
    source_urls: tuple[str, str],
) -> CaptureRequest:
    return CaptureRequest.model_validate(
        {
            "project_id": str(project_id),
            "session_key": session_key,
            "entries": [
                {
                    "claim": f"{session_key} observed source {index}.",
                    "source_url": source_url,
                    "disposition": "supporting",
                }
                for index, source_url in enumerate(source_urls, start=1)
            ],
        }
    )


def _seed_project(session_factory) -> tuple[UUID, UUID, UUID]:
    seed = session_factory()
    try:
        owner = User(
            email=f"ledger-retrieval-{uuid4().hex}@example.test",
            display_name="Ledger retrieval writer",
            password_hash=_HASH,
            role="member",
        )
        workspace = Workspace(name=f"Ledger retrieval space {uuid4().hex}")
        seed.add_all((owner, workspace))
        seed.flush()
        project = Project(
            name=f"Ledger retrieval project {uuid4().hex}",
            owner_id=owner.id,
            workspace_id=workspace.id,
        )
        seed.add(project)
        seed.commit()
        return project.id, owner.id, workspace.id
    finally:
        seed.close()


def _cleanup_project(
    session_factory,
    *,
    project_id: UUID,
    owner_id: UUID,
    workspace_id: UUID,
) -> None:
    cleanup = session_factory()
    try:
        cleanup.query(LedgerEntry).filter(LedgerEntry.project_id == project_id).delete(synchronize_session=False)
        cleanup.query(LedgerSource).filter(LedgerSource.project_id == project_id).delete(synchronize_session=False)
        cleanup.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
        cleanup.query(User).filter(User.id == owner_id).delete(synchronize_session=False)
        cleanup.query(Workspace).filter(Workspace.id == workspace_id).delete(synchronize_session=False)
        cleanup.commit()
    finally:
        cleanup.close()


def test_postgres_search_stems_ranks_and_retrieves_across_sessions(pg_engine) -> None:
    """FTS must find lexical variants and rank evidence, not merely sort recency."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    project_id, owner_id, workspace_id = _seed_project(session_factory)
    db = session_factory()
    service = EvidenceLedgerService()
    try:
        service.capture(
            db,
            _capture_request(
                project_id,
                session_key="ranked-session",
                claim="Analysts run resilient authentication drills and run validation checks.",
                summary="Teams run those authentication drills each quarter.",
                source_url="https://example.test/ranked-source",
                snippet="Operators run the authentication playbook.",
                query="how teams run authentication drills",
            ),
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
        service.capture(
            db,
            _capture_request(
                project_id,
                session_key="literal-session",
                claim="The running baseline is documented.",
                source_url="https://example.test/literal-source",
            ),
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
        service.capture(
            db,
            _capture_request(
                project_id,
                session_key="unrelated-session",
                claim="A retention policy is documented separately.",
                source_url="https://example.test/unrelated-source",
            ),
            owner_id=owner_id,
            workspace_id=workspace_id,
        )

        entries, total = service.search(
            db,
            project_id=project_id,
            keyword="running",
            session_key=None,
            mission_id=None,
            disposition=None,
            page=1,
            page_size=20,
            access_filter=None,
            allowed_project_ids=[project_id],
        )

        assert total == 2
        assert [entry.session_key for entry in entries] == [
            "ranked-session",
            "literal-session",
        ]
        assert "running" not in entries[0].claim.lower(), "the highest-ranked hit contains only the English stem 'run'"
        assert {entry.session_key for entry in entries} == {
            "ranked-session",
            "literal-session",
        }, "search must span research sessions within the selected project"
    finally:
        db.close()
        _cleanup_project(
            session_factory,
            project_id=project_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )


def test_concurrent_same_url_captures_atomically_increment_one_source(pg_engine) -> None:
    """Concurrent sessions cannot lose a sighting or split canonical source identity."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    project_id, owner_id, workspace_id = _seed_project(session_factory)
    source_url = "https://example.test/concurrent-shared-source"
    insert_barrier = Barrier(2)

    def synchronize_source_insert(
        _conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if statement.lstrip().startswith("INSERT INTO ledger_sources"):
            insert_barrier.wait(timeout=10)

    def capture(session_key: str) -> UUID:
        db = session_factory()
        try:
            entry = EvidenceLedgerService().capture(
                db,
                _capture_request(
                    project_id,
                    session_key=session_key,
                    claim=f"{session_key} independently observed the shared source.",
                    source_url=source_url,
                ),
                owner_id=owner_id,
                workspace_id=workspace_id,
            )[0]
            return entry.source_id
        finally:
            db.close()

    try:
        event.listen(pg_engine, "before_cursor_execute", synchronize_source_insert)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(capture, session_key)
                    for session_key in (
                        "concurrent-session-one",
                        "concurrent-session-two",
                    )
                ]
                source_ids = [future.result(timeout=20) for future in futures]
        finally:
            event.remove(
                pg_engine,
                "before_cursor_execute",
                synchronize_source_insert,
            )

        verify = session_factory()
        try:
            sources = verify.query(LedgerSource).filter(LedgerSource.project_id == project_id).all()
            entries = (
                verify.query(LedgerEntry)
                .filter(LedgerEntry.project_id == project_id)
                .order_by(LedgerEntry.session_key)
                .all()
            )
            assert len(set(source_ids)) == 1
            assert len(sources) == 1
            assert sources[0].id == source_ids[0]
            assert sources[0].sighting_count == 2
            assert [entry.session_key for entry in entries] == [
                "concurrent-session-one",
                "concurrent-session-two",
            ]
            assert {entry.source_id for entry in entries} == {sources[0].id}
        finally:
            verify.close()
    finally:
        _cleanup_project(
            session_factory,
            project_id=project_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )


def test_concurrent_reversed_multi_url_batches_commit_without_deadlock(pg_engine) -> None:
    """Stable upsert ordering prevents two shared sources from cyclically locking."""
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    project_id, owner_id, workspace_id = _seed_project(session_factory)
    source_urls = (
        "https://example.test/concurrent-first-source",
        "https://example.test/concurrent-second-source",
    )
    insert_start = Barrier(2)
    coordinated_connections: set[int] = set()
    coordination_lock = Lock()

    def synchronize_first_source_insert(
        conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if not statement.lstrip().startswith("INSERT INTO ledger_sources"):
            return
        connection_key = id(conn)
        with coordination_lock:
            if connection_key in coordinated_connections:
                return
            coordinated_connections.add(connection_key)
        insert_start.wait(timeout=10)

    def capture(session_key: str, ordered_urls: tuple[str, str]) -> list[UUID]:
        db = session_factory()
        try:
            entries = EvidenceLedgerService().capture(
                db,
                _two_source_capture_request(
                    project_id,
                    session_key=session_key,
                    source_urls=ordered_urls,
                ),
                owner_id=owner_id,
                workspace_id=workspace_id,
            )
            return [entry.source_id for entry in entries]
        finally:
            db.close()

    try:
        event.listen(
            pg_engine,
            "before_cursor_execute",
            synchronize_first_source_insert,
        )
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                first_future = executor.submit(
                    capture,
                    "reversed-batch-one",
                    source_urls,
                )
                second_future = executor.submit(
                    capture,
                    "reversed-batch-two",
                    tuple(reversed(source_urls)),
                )
                committed_source_ids = [
                    first_future.result(timeout=20),
                    second_future.result(timeout=20),
                ]
        finally:
            event.remove(
                pg_engine,
                "before_cursor_execute",
                synchronize_first_source_insert,
            )

        verify = session_factory()
        try:
            sources = (
                verify.query(LedgerSource)
                .filter(LedgerSource.project_id == project_id)
                .order_by(LedgerSource.source_url)
                .all()
            )
            entries = verify.query(LedgerEntry).filter(LedgerEntry.project_id == project_id).all()
            assert len(committed_source_ids) == 2, "both transactions must commit"
            assert len(sources) == 2
            assert [source.source_url for source in sources] == list(source_urls)
            assert [source.sighting_count for source in sources] == [2, 2]
            assert len(entries) == 4
            assert {entry.session_key for entry in entries} == {
                "reversed-batch-one",
                "reversed-batch-two",
            }
            assert {source_id for transaction_ids in committed_source_ids for source_id in transaction_ids} == {
                source.id for source in sources
            }
        finally:
            verify.close()
    finally:
        _cleanup_project(
            session_factory,
            project_id=project_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
