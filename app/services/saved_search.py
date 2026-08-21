"""Service for managing saved search records."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session

from app.core.database import SessionLocal
from app.models.saved_search import SavedSearch

SessionFactory = Callable[[], Session]


class SavedSearchService:
    """Provide CRUD operations plus usage tracking for saved searches."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        max_saved_per_user: int = 50,
    ) -> None:
        self.session_factory = session_factory
        self.max_saved_per_user = max_saved_per_user

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_for_owner(
        self, owner_id: UUID | None, *, legacy_owner: str | None = None
    ) -> list[SavedSearch]:
        """Return saved searches within the request's ownership scope.

        ``None`` is reserved for trusted internal callers. Public routes always
        provide the stable user UUID; RBAC-off callers may additionally recover
        their unresolved pre-migration rows through ``legacy_owner``.
        """
        session = self.session_factory()
        try:
            query = session.query(SavedSearch)
            query = self._scope_query(
                query, owner_id=owner_id, legacy_owner=legacy_owner
            )
            return query.order_by(SavedSearch.updated_at.desc()).all()
        finally:
            session.close()

    def get(
        self,
        saved_search_id: UUID | str,
        owner_id: UUID | None,
        *,
        legacy_owner: str | None = None,
    ) -> SavedSearch | None:
        """Look up a saved search within the request's ownership scope."""
        session = self.session_factory()
        try:
            query = session.query(SavedSearch).filter(
                SavedSearch.id == str(saved_search_id)
            )
            query = self._scope_query(
                query, owner_id=owner_id, legacy_owner=legacy_owner
            )
            return query.one_or_none()
        finally:
            session.close()

    def create(
        self,
        *,
        owner_id: UUID,
        owner: str,
        legacy_owner: str | None = None,
        name: str,
        query_text: str,
        search_mode: str,
        filters: dict[str, Any],
        top_k: int,
        description: str | None = None,
    ) -> SavedSearch:
        """Persist a saved search configuration enforcing per-user limits."""
        owner_key = self._clean_owner(owner)
        if not owner_key:
            raise ValueError("Owner is required.")

        name_value = self._clean_name(name)
        if not name_value:
            raise ValueError("Name is required.")

        query_value = (query_text or "").strip()
        if not query_value:
            raise ValueError("Query text is required.")

        normalized_filters = dict(filters or {})
        session = self.session_factory()
        try:
            owner_query = self._scope_query(
                session.query(SavedSearch),
                owner_id=owner_id,
                legacy_owner=legacy_owner,
            )
            current_total = owner_query.count()
            if current_total >= self.max_saved_per_user:
                raise ValueError(
                    f"Saved search limit of {self.max_saved_per_user} reached."
                )
            if owner_query.filter(SavedSearch.name == name_value).count():
                raise ValueError("A saved search with that name already exists.")

            entry = SavedSearch(
                name=name_value,
                description=self._clean_description(description),
                query_text=query_value,
                search_mode=self._normalize_mode(search_mode),
                filters=normalized_filters,
                top_k=self._normalize_top_k(top_k),
                owner_id=owner_id,
                owner=owner_key,
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry
        except IntegrityError as error:
            session.rollback()
            raise ValueError("A saved search with that name already exists.") from error
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update(
        self,
        saved_search_id: UUID | str,
        *,
        owner_id: UUID | None,
        legacy_owner: str | None = None,
        updates: dict[str, Any],
    ) -> SavedSearch | None:
        """Update mutable fields for a saved search."""
        session = self.session_factory()
        try:
            query = session.query(SavedSearch).filter(
                SavedSearch.id == str(saved_search_id)
            )
            query = self._scope_query(
                query, owner_id=owner_id, legacy_owner=legacy_owner
            )
            entry = query.one_or_none()
            if entry is None:
                return None

            if "name" in updates:
                next_name = self._clean_name(updates["name"])
                if not next_name:
                    raise ValueError("Name is required.")
                duplicate = self._scope_query(
                    session.query(SavedSearch).filter(
                        SavedSearch.id != str(saved_search_id)
                    ),
                    owner_id=owner_id,
                    legacy_owner=legacy_owner,
                ).filter(SavedSearch.name == next_name)
                if duplicate.first() is not None:
                    raise ValueError("A saved search with that name already exists.")
                entry.name = next_name
            if "description" in updates:
                entry.description = self._clean_description(updates.get("description"))
            if "query_text" in updates:
                query_value = (updates["query_text"] or "").strip()
                if not query_value:
                    raise ValueError("Query text is required.")
                entry.query_text = query_value
            if "search_mode" in updates and updates["search_mode"] is not None:
                entry.search_mode = self._normalize_mode(str(updates["search_mode"]))
            if "filters" in updates and updates["filters"] is not None:
                entry.filters = dict(updates["filters"])
            if "top_k" in updates and updates["top_k"] is not None:
                entry.top_k = self._normalize_top_k(int(updates["top_k"]))

            session.commit()
            session.refresh(entry)
            return entry
        except IntegrityError as error:
            session.rollback()
            raise ValueError("A saved search with that name already exists.") from error
        except ValueError:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(
        self,
        saved_search_id: UUID | str,
        *,
        owner_id: UUID | None,
        legacy_owner: str | None = None,
    ) -> bool:
        """Delete a saved search within the request's ownership scope."""
        session = self.session_factory()
        try:
            query = session.query(SavedSearch).filter(
                SavedSearch.id == str(saved_search_id)
            )
            query = self._scope_query(
                query, owner_id=owner_id, legacy_owner=legacy_owner
            )
            deleted = query.delete(synchronize_session=False)
            session.commit()
            return bool(deleted)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def mark_used(
        self,
        saved_search_id: UUID | str,
        *,
        owner_id: UUID | None,
        legacy_owner: str | None = None,
    ) -> SavedSearch | None:
        """Increment usage metrics within the request's ownership scope."""
        session = self.session_factory()
        try:
            query = session.query(SavedSearch).filter(
                SavedSearch.id == str(saved_search_id)
            )
            query = self._scope_query(
                query, owner_id=owner_id, legacy_owner=legacy_owner
            )
            entry = query.one_or_none()
            if entry is None:
                return None
            entry.use_count = int(entry.use_count or 0) + 1
            entry.last_used_at = datetime.utcnow()
            session.commit()
            session.refresh(entry)
            return entry
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_owner(owner: str) -> str:
        return (owner or "").strip()

    @classmethod
    def _scope_query(
        cls,
        query: Query[SavedSearch],
        *,
        owner_id: UUID | None,
        legacy_owner: str | None,
    ) -> Query[SavedSearch]:
        """Apply stable ownership plus the explicit RBAC-off legacy fallback."""
        if owner_id is None:
            return query
        owner_filters = [SavedSearch.owner_id == owner_id]
        legacy_key = cls._clean_owner(legacy_owner or "")
        if legacy_key:
            owner_filters.append(
                and_(SavedSearch.owner_id.is_(None), SavedSearch.owner == legacy_key)
            )
        return query.filter(or_(*owner_filters))

    @staticmethod
    def _clean_name(name: str | None) -> str:
        return (name or "").strip()

    @staticmethod
    def _clean_description(description: str | None) -> str | None:
        text = (description or "").strip()
        return text or None

    @staticmethod
    def _normalize_mode(search_mode: str | None) -> str:
        mode = (search_mode or "semantic").strip().lower()
        return mode or "semantic"

    @staticmethod
    def _normalize_top_k(top_k: int | None) -> int:
        value = int(top_k or 5)
        if value < 1:
            return 1
        if value > 50:
            return 50
        return value


_saved_search_service: SavedSearchService | None = None


def get_saved_search_service() -> SavedSearchService:
    """Provide a lazily instantiated singleton saved-search service."""
    global _saved_search_service
    if _saved_search_service is None:
        _saved_search_service = SavedSearchService()
    return _saved_search_service
