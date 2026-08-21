"""Service for managing chunk collections."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document

SessionFactory = Callable[[], Session]

MAX_CHUNKS_PER_COLLECTION = 100


class CollectionChunkNotFoundError(ValueError):
    """Raised when an add target is missing from the authoritative document graph."""


class CollectionChunkForbiddenError(ValueError):
    """Raised when an existing add target is outside the caller's project scope."""


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
    def list_collections(self, access_filter=None) -> list[Collection]:
        """Return collections ordered by most recent.

        ``access_filter`` (authorization.accessible_filter) is an optional RBAC
        row-filter (T47.3); it is a session-agnostic SQLAlchemy expression built from
        the request session and applied here on this service's own session. None = no
        filtering.
        """
        session = self.session_factory()
        try:
            query = session.query(Collection)
            if access_filter is not None:
                query = query.filter(access_filter)
            return query.order_by(Collection.updated_at.desc()).all()
        finally:
            session.close()

    def get(self, collection_id: UUID | str) -> Collection | None:
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
        description: str | None = None,
        owner_id: UUID | None = None,
        workspace_id: UUID | None = None,
    ) -> Collection:
        """Create a new collection.

        ``owner_id``/``workspace_id`` are resolved by the route (the caller + default
        Space) and passed as scalar UUIDs — this service opens its OWN session, so it
        can't read the request principal itself (T48.4).
        """
        name_value = self._clean_name(name)
        if not name_value:
            raise ValueError("Name is required.")

        session = self.session_factory()
        try:
            entry = Collection(
                name=name_value,
                description=self._clean_description(description),
                owner_id=owner_id,
                workspace_id=workspace_id,
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
        updates: dict[str, Any],
    ) -> Collection | None:
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
        notes: str | None = None,
        accessible_project_ids: list[UUID] | None = None,
    ) -> CollectionItem:
        """Add a live chunk to a collection within the caller's project scope."""
        session = self.session_factory()
        try:
            if accessible_project_ids is None:
                # Preserve the unrestricted lookup exactly, including its SQL shape.
                collection = (
                    session.query(Collection)
                    .filter(Collection.id == str(collection_id))
                    .one_or_none()
                )
            else:
                # Lock the parent where the database supports row locking. This
                # keeps the scoped limit check and insert in one transaction.
                collection = (
                    session.query(Collection)
                    .filter(Collection.id == str(collection_id))
                    .with_for_update(of=Collection)
                    .one_or_none()
                )
            if collection is None:
                if accessible_project_ids is None:
                    raise ValueError("Collection not found.")
                raise CollectionChunkNotFoundError("Collection not found.")

            if accessible_project_ids is None:
                chunk = (
                    session.query(DocumentChunk)
                    .filter(DocumentChunk.id == str(chunk_id))
                    .one_or_none()
                )
                if chunk is None:
                    raise ValueError("Chunk not found.")
            else:
                # Resolve through the live document and lock the matched row where
                # supported. Its project_id is authoritative for authorization.
                chunk_row = (
                    session.query(DocumentChunk, Document.project_id)
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .filter(
                        DocumentChunk.id == str(chunk_id),
                        Document.deleted_at.is_(None),
                    )
                    .with_for_update()
                    .one_or_none()
                )
                if chunk_row is None:
                    raise CollectionChunkNotFoundError("Chunk not found.")

                _chunk, project_id = chunk_row
                if project_id not in set(accessible_project_ids):
                    raise CollectionChunkForbiddenError(
                        "You do not have access to this chunk."
                    )

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
        *,
        accessible_project_ids: list[UUID] | None = None,
    ) -> bool:
        """Remove a chunk visible within the caller's project scope."""
        if accessible_project_ids == []:
            return False

        session = self.session_factory()
        try:
            if accessible_project_ids is not None:
                item = (
                    session.query(CollectionItem)
                    .join(
                        DocumentChunk,
                        CollectionItem.chunk_id == DocumentChunk.id,
                    )
                    .join(Document, DocumentChunk.document_id == Document.id)
                    .filter(
                        CollectionItem.collection_id == str(collection_id),
                        CollectionItem.chunk_id == str(chunk_id),
                        Document.deleted_at.is_(None),
                        Document.project_id.in_(accessible_project_ids),
                    )
                    .with_for_update(of=CollectionItem)
                    .one_or_none()
                )
                if item is None:
                    return False
                session.delete(item)
                session.commit()
                return True

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

    def get_items(
        self,
        collection_id: UUID | str,
        *,
        accessible_project_ids: list[UUID] | None = None,
    ) -> list[CollectionItem]:
        """Get all items in a collection with chunk data."""
        if accessible_project_ids == []:
            return []

        session = self.session_factory()
        try:
            if accessible_project_ids is not None:
                return (
                    session.query(CollectionItem)
                    .join(
                        DocumentChunk,
                        CollectionItem.chunk_id == DocumentChunk.id,
                    )
                    .join(Document, DocumentChunk.document_id == Document.id)
                    .filter(
                        CollectionItem.collection_id == str(collection_id),
                        Document.deleted_at.is_(None),
                        Document.project_id.in_(accessible_project_ids),
                    )
                    .order_by(CollectionItem.added_at.desc())
                    .all()
                )

            return (
                session.query(CollectionItem)
                .filter(CollectionItem.collection_id == str(collection_id))
                .order_by(CollectionItem.added_at.desc())
                .all()
            )
        finally:
            session.close()

    def get_item_count(
        self,
        collection_id: UUID | str,
        *,
        accessible_project_ids: list[UUID] | None = None,
    ) -> int:
        """Get count of items in a collection."""
        if accessible_project_ids == []:
            return 0

        session = self.session_factory()
        try:
            if accessible_project_ids is not None:
                return (
                    session.query(CollectionItem)
                    .join(
                        DocumentChunk,
                        CollectionItem.chunk_id == DocumentChunk.id,
                    )
                    .join(Document, DocumentChunk.document_id == Document.id)
                    .filter(
                        CollectionItem.collection_id == str(collection_id),
                        Document.deleted_at.is_(None),
                        Document.project_id.in_(accessible_project_ids),
                    )
                    .count()
                )

            return (
                session.query(CollectionItem)
                .filter(CollectionItem.collection_id == str(collection_id))
                .count()
            )
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def export_markdown(
        self,
        collection_id: UUID | str,
        *,
        accessible_project_ids: list[UUID] | None = None,
    ) -> str | None:
        """Export collection as markdown bundle for agent synthesis.

        Returns None if collection not found, otherwise a markdown string.
        """
        session = self.session_factory()
        try:
            collection = (
                session.query(Collection)
                .filter(Collection.id == str(collection_id))
                .one_or_none()
            )
            if collection is None:
                return None

            # Keep the unrestricted query byte-identical. Scoped reads instead
            # resolve each child through its live document and project grant.
            if accessible_project_ids is None:
                items = (
                    session.query(CollectionItem)
                    .filter(CollectionItem.collection_id == str(collection_id))
                    .order_by(CollectionItem.added_at.asc())
                    .all()
                )
            elif accessible_project_ids == []:
                items = []
            else:
                items = (
                    session.query(CollectionItem)
                    .join(
                        DocumentChunk,
                        CollectionItem.chunk_id == DocumentChunk.id,
                    )
                    .join(Document, DocumentChunk.document_id == Document.id)
                    .filter(
                        CollectionItem.collection_id == str(collection_id),
                        Document.deleted_at.is_(None),
                        Document.project_id.in_(accessible_project_ids),
                    )
                    .order_by(CollectionItem.added_at.asc())
                    .all()
                )

            # Gather document info for chunks
            doc_ids = set()
            for item in items:
                if item.chunk and item.chunk.document_id:
                    doc_ids.add(str(item.chunk.document_id))

            documents: dict[str, Document] = {}
            if doc_ids:
                docs = session.query(Document).filter(Document.id.in_(doc_ids)).all()
                documents = {str(d.id): d for d in docs}

            # Build markdown
            lines: list[str] = []
            lines.append(f"# {collection.name}")
            lines.append("")
            if collection.description:
                lines.append(f"> {collection.description}")
                lines.append("")
            lines.append("---")
            lines.append("")
            lines.append("## Metadata")
            lines.append("")
            lines.append(f"- **Collection ID:** `{collection.id}`")
            lines.append(
                f"- **Created:** {collection.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
            )
            lines.append(
                f"- **Updated:** {collection.updated_at.strftime('%Y-%m-%d %H:%M UTC')}"
            )
            lines.append(f"- **Total Chunks:** {len(items)}")
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append("## Collected Chunks")
            lines.append("")

            for idx, item in enumerate(items, start=1):
                chunk = item.chunk
                doc = documents.get(str(chunk.document_id)) if chunk else None

                lines.append(f"### Chunk {idx}")
                lines.append("")

                # Source info
                if doc:
                    lines.append(f"**Source:** {doc.name}")
                    if doc.file_type:
                        lines.append(f"**Type:** {doc.file_type}")
                    if doc.source_type:
                        lines.append(f"**Source Type:** {doc.source_type}")
                elif chunk:
                    lines.append(f"**Document ID:** `{chunk.document_id}`")

                if chunk:
                    lines.append(f"**Chunk Index:** {chunk.chunk_index}")

                lines.append(
                    f"**Added to Collection:** {item.added_at.strftime('%Y-%m-%d %H:%M UTC')}"
                )

                if item.notes:
                    lines.append("")
                    lines.append(f"**Notes:** {item.notes}")

                lines.append("")
                lines.append("```")
                if chunk and chunk.content:
                    lines.append(chunk.content)
                else:
                    lines.append("(Content unavailable)")
                lines.append("```")
                lines.append("")
                lines.append("---")
                lines.append("")

            # Footer for agent context
            lines.append("## Export Info")
            lines.append("")
            lines.append(
                f"*Exported at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} for agent synthesis.*"
            )
            lines.append("")

            return "\n".join(lines)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_name(name: str | None) -> str:
        return (name or "").strip()

    @staticmethod
    def _clean_description(description: str | None) -> str | None:
        text = (description or "").strip()
        return text or None


_collection_service: CollectionService | None = None


def get_collection_service() -> CollectionService:
    """Provide a lazily instantiated singleton collection service."""
    global _collection_service
    if _collection_service is None:
        _collection_service = CollectionService()
    return _collection_service
