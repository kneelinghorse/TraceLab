"""Search history logging + replay state management."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.search_history import SearchHistory

SessionFactory = Callable[[], Session]


class SearchHistoryService:
    """Persist and retrieve search history entries with retention controls."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        max_entries: int = 100,
        max_age_days: int = 30,
    ) -> None:
        self.session_factory = session_factory
        self.max_entries = max_entries
        self.max_age_days = max_age_days

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def record_search(
        self,
        *,
        query: str,
        search_mode: str,
        filters: dict[str, Any],
        top_k: int,
        result_count: int,
        duration_ms: float | None,
        cache_hit: bool,
        executed_by: str | None,
        owner_id: UUID | None = None,
        top_chunks: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SearchHistory:
        """Store a search entry and enforce retention controls."""
        session = self.session_factory()
        try:
            entry = SearchHistory(
                query_text=query,
                search_mode=(search_mode or "semantic").lower(),
                filters=dict(filters or {}),
                top_k=int(top_k) if top_k else 5,
                result_count=max(0, int(result_count or 0)),
                duration_ms=int(round(duration_ms))
                if isinstance(duration_ms, float | int)
                else None,
                cache_hit=bool(cache_hit),
                owner_id=owner_id,
                user_label=executed_by,
                metadata_payload=dict(metadata or {}),
                top_chunks=list(top_chunks or []),
            )
            session.add(entry)
            session.flush()
            self._enforce_retention(session, owner_id=owner_id)
            session.commit()
            session.refresh(entry)
            return entry
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_history(
        self, limit: int = 20, *, owner_id: UUID | None = None
    ) -> list[SearchHistory]:
        """Return recent entries within the request's ownership scope."""
        session = self.session_factory()
        try:
            query = session.query(SearchHistory)
            if owner_id is not None:
                query = query.filter(SearchHistory.owner_id == owner_id)
            rows = query.order_by(SearchHistory.created_at.desc()).limit(
                max(1, limit)
            ).all()
            return rows or []
        finally:
            session.close()

    def get_entry(
        self, entry_id: UUID | str, *, owner_id: UUID | None = None
    ) -> SearchHistory | None:
        """Return an entry within the request's ownership scope."""
        session = self.session_factory()
        try:
            query = session.query(SearchHistory).filter(
                SearchHistory.id == str(entry_id)
            )
            if owner_id is not None:
                query = query.filter(SearchHistory.owner_id == owner_id)
            return query.one_or_none()
        finally:
            session.close()

    def visible_top_chunks(
        self,
        entries: Iterable[SearchHistory],
        *,
        allowed_project_ids: list[UUID] | None,
    ) -> dict[UUID, list[str]]:
        """Batch-resolve history chunk IDs through live, authorized documents.

        ``None`` deliberately returns the stored values unchanged for the
        unrestricted legacy path. Scoped callers only receive UUIDs that still
        resolve through ``DocumentChunk -> Document`` to an allowed, non-deleted
        document.
        """
        rows = list(entries)
        if allowed_project_ids is None:
            return {row.id: list(row.top_chunks or []) for row in rows}
        if not rows or not allowed_project_ids:
            return {row.id: [] for row in rows}

        parsed_by_value: dict[str, UUID] = {}
        for row in rows:
            for value in row.top_chunks or []:
                text_value = str(value)
                try:
                    parsed_by_value[text_value] = UUID(text_value)
                except (TypeError, ValueError, AttributeError):
                    continue

        if not parsed_by_value:
            return {row.id: [] for row in rows}

        session = self.session_factory()
        try:
            resolved = (
                session.query(DocumentChunk.id)
                .join(Document, Document.id == DocumentChunk.document_id)
                .filter(
                    DocumentChunk.id.in_(set(parsed_by_value.values())),
                    Document.deleted_at.is_(None),
                    Document.project_id.in_(allowed_project_ids),
                )
                .all()
            )
            visible_ids = {UUID(str(item[0])) for item in resolved}
        finally:
            session.close()

        return {
            row.id: [
                str(value)
                for value in row.top_chunks or []
                if parsed_by_value.get(str(value)) in visible_ids
            ]
            for row in rows
        }

    def retention_policy(self) -> dict[str, int]:
        """Expose configured retention limits."""
        return {
            "max_entries": self.max_entries,
            "max_age_days": self.max_age_days,
        }

    def clear_history(self, *, owner_id: UUID | None = None) -> int:
        """Remove entries within the request's ownership scope."""
        session = self.session_factory()
        try:
            query = session.query(SearchHistory)
            if owner_id is not None:
                query = query.filter(SearchHistory.owner_id == owner_id)
            deleted = query.delete(synchronize_session=False)
            session.commit()
            return int(deleted or 0)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _enforce_retention(
        self, session: Session, *, owner_id: UUID | None
    ) -> None:
        """Delete all expired rows, then enforce the caller's count limit."""
        cutoff = datetime.utcnow() - timedelta(days=self.max_age_days)
        stale_query = session.query(SearchHistory).filter(
            SearchHistory.created_at < cutoff
        )
        retained_query = session.query(SearchHistory.id)
        if owner_id is not None:
            retained_query = retained_query.filter(
                SearchHistory.owner_id == owner_id
            )
        stale_query.delete(synchronize_session=False)

        extra_ids = (
            retained_query.order_by(SearchHistory.created_at.desc())
            .offset(self.max_entries)
            .all()
        )
        if not extra_ids:
            return
        session.query(SearchHistory).filter(
            SearchHistory.id.in_(row.id for row in extra_ids)
        ).delete(synchronize_session=False)


_history_service: SearchHistoryService | None = None


def get_search_history_service() -> SearchHistoryService:
    """Provide a lazily instantiated singleton search history service."""
    global _history_service
    if _history_service is None:
        _history_service = SearchHistoryService()
    return _history_service
