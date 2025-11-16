"""Search history logging + replay state management."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
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
        filters: Dict[str, Any],
        top_k: int,
        result_count: int,
        duration_ms: Optional[float],
        cache_hit: bool,
        executed_by: Optional[str],
        top_chunks: Iterable[str] | None = None,
        metadata: Optional[Dict[str, Any]] = None,
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
                duration_ms=int(round(duration_ms)) if isinstance(duration_ms, (float, int)) else None,
                cache_hit=bool(cache_hit),
                user_label=executed_by,
                metadata_payload=dict(metadata or {}),
                top_chunks=list(top_chunks or []),
            )
            session.add(entry)
            session.flush()
            self._enforce_retention(session)
            session.commit()
            session.refresh(entry)
            return entry
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_history(self, limit: int = 20) -> List[SearchHistory]:
        """Return the most recent search entries."""
        session = self.session_factory()
        try:
            rows = (
                session.query(SearchHistory)
                .order_by(SearchHistory.created_at.desc())
                .limit(max(1, limit))
                .all()
            )
            return rows or []
        finally:
            session.close()

    def get_entry(self, entry_id: UUID | str) -> Optional[SearchHistory]:
        """Return a specific search entry by identifier."""
        session = self.session_factory()
        try:
            return session.query(SearchHistory).filter(SearchHistory.id == str(entry_id)).one_or_none()
        finally:
            session.close()

    def retention_policy(self) -> Dict[str, int]:
        """Expose configured retention limits."""
        return {
            "max_entries": self.max_entries,
            "max_age_days": self.max_age_days,
        }

    def clear_history(self) -> int:
        """Remove all search history entries."""
        session = self.session_factory()
        try:
            deleted = session.query(SearchHistory).delete(synchronize_session=False)
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
    def _enforce_retention(self, session: Session) -> None:
        """Delete search records that exceed age/count limits."""
        cutoff = datetime.utcnow() - timedelta(days=self.max_age_days)
        session.query(SearchHistory).filter(SearchHistory.created_at < cutoff).delete(synchronize_session=False)

        extra_ids = (
            session.query(SearchHistory.id)
            .order_by(SearchHistory.created_at.desc())
            .offset(self.max_entries)
            .all()
        )
        if not extra_ids:
            return
        session.query(SearchHistory).filter(SearchHistory.id.in_(row.id for row in extra_ids)).delete(
            synchronize_session=False
        )


_history_service: Optional[SearchHistoryService] = None


def get_search_history_service() -> SearchHistoryService:
    """Provide a lazily instantiated singleton search history service."""
    global _history_service
    if _history_service is None:
        _history_service = SearchHistoryService()
    return _history_service
