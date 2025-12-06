"""Service for managing chunk collections."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.collection import Collection, CollectionItem
from app.models.chunk import DocumentChunk

SessionFactory = Callable[[], Session]

MAX_CHUNKS_PER_COLLECTION = 100


class CollectionService:
    """Provide CRUD operations for collections and their items."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        max_chunks_per_collection: int = MAX_CHUNKS_PER_COLLECTION,
    ) -> None:
        self.session_factory = session_factory
        self.max_chunks_per_collection = max_chunks_per_collection

    # ------------------------------------------------------------------
    # Collection CRUD
    # ------------------------------------------------------------------
    def list_collections(self) -> List[Collection]:
        """Return all collections ordered by most recent."""
        session = self.session_factory()
        try:
            return (
                session.query(Collection)
                .order_by(Collection.updated_at.desc())
                .all()
            )
        finally:
            session.close()

    def get(self, collection_id: UUID | str) -> Optional[Collection]:
        """Look up a collection by ID."""
        session = self.session_factory()
        try:
            return (
                session.query(Collection)
                .filter(Collection.id == str(collection_id))
                .one_or_none()
            )
        finally:
            session.close()

    def create(
        self,
        *,
        name: str,
        description: Optional[str] = None,
    ) -> Collection:
        """Create a new collection."""
        name_value = self._clean_name(name)
        if not name_value:
            raise ValueError("Name is required.")

        session = self.session_factory()
        try:
            entry = Collection(
                name=name_value,
                description=self._clean_description(description),
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update(
        self,
        collection_id: UUID | str,
        *,
        updates: Dict[str, Any],
    ) -> Optional[Collection]:
        """Update mutable fields for a collection."""
        session = self.session_factory()
        try:
            entry = (
                session.query(Collection)
                .filter(Collection.id == str(collection_id))
                .one_or_none()
            )
            if entry is None:
                return None

            if "name" in updates:
                next_name = self._clean_name(updates["name"])
                if not next_name:
                    raise ValueError("Name is required.")
                entry.name = next_name
            if "description" in updates:
                entry.description = self._clean_description(updates.get("description"))

            session.commit()
            session.refresh(entry)
            return entry
        except ValueError:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, collection_id: UUID | str) -> bool:
        """Delete a collection and all its items."""
        session = self.session_factory()
        try:
            deleted = (
                session.query(Collection)
                .filter(Collection.id == str(collection_id))
                .delete(synchronize_session=False)
            )
            session.commit()
            return bool(deleted)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Collection Item operations
    # ------------------------------------------------------------------
    def add_chunk(
        self,
        collection_id: UUID | str,
        *,
        chunk_id: UUID | str,
        notes: Optional[str] = None,
    ) -> CollectionItem:
        """Add a chunk to a collection."""
        session = self.session_factory()
        try:
            # Verify collection exists
            collection = (
                session.query(Collection)
                .filter(Collection.id == str(collection_id))
                .one_or_none()
            )
            if collection is None:
                raise ValueError("Collection not found.")

            # Verify chunk exists
            chunk = (
                session.query(DocumentChunk)
                .filter(DocumentChunk.id == str(chunk_id))
                .one_or_none()
            )
            if chunk is None:
                raise ValueError("Chunk not found.")

            # Check limit
            item_count = (
                session.query(CollectionItem)
                .filter(CollectionItem.collection_id == str(collection_id))
                .count()
            )
            if item_count >= self.max_chunks_per_collection:
                raise ValueError(
                    f"Collection has reached the maximum of {self.max_chunks_per_collection} chunks."
                )

            item = CollectionItem(
                collection_id=str(collection_id),
                chunk_id=str(chunk_id),
                notes=self._clean_description(notes),
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return item
        except IntegrityError as error:
            session.rollback()
            raise ValueError("Chunk is already in this collection.") from error
        except ValueError:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def remove_chunk(
        self,
        collection_id: UUID | str,
        chunk_id: UUID | str,
    ) -> bool:
        """Remove a chunk from a collection."""
        session = self.session_factory()
        try:
            deleted = (
                session.query(CollectionItem)
                .filter(
                    CollectionItem.collection_id == str(collection_id),
                    CollectionItem.chunk_id == str(chunk_id),
                )
                .delete(synchronize_session=False)
            )
            session.commit()
            return bool(deleted)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_items(self, collection_id: UUID | str) -> List[CollectionItem]:
        """Get all items in a collection with chunk data."""
        session = self.session_factory()
        try:
            return (
                session.query(CollectionItem)
                .filter(CollectionItem.collection_id == str(collection_id))
                .order_by(CollectionItem.added_at.desc())
                .all()
            )
        finally:
            session.close()

    def get_item_count(self, collection_id: UUID | str) -> int:
        """Get count of items in a collection."""
        session = self.session_factory()
        try:
            return (
                session.query(CollectionItem)
                .filter(CollectionItem.collection_id == str(collection_id))
                .count()
            )
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_name(name: str | None) -> str:
        return (name or "").strip()

    @staticmethod
    def _clean_description(description: str | None) -> Optional[str]:
        text = (description or "").strip()
        return text or None


_collection_service: Optional[CollectionService] = None


def get_collection_service() -> CollectionService:
    """Provide a lazily instantiated singleton collection service."""
    global _collection_service
    if _collection_service is None:
        _collection_service = CollectionService()
    return _collection_service
