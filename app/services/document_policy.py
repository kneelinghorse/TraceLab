"""Shared document read policy and pre-provider chunk resolution."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.authorization import accessible_filter
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.chunk import DocumentChunk
from app.models.collection import CollectionItem
from app.models.document import Document
from app.models.project import Project


def document_read_policy(user: AuthenticatedUser, db: Session) -> ColumnElement[bool] | None:
    """Return the live-document scope for every RBAC-on caller, including admins."""
    if not settings.rbac_enabled:
        return None
    clauses = [
        Document.deleted_at.is_(None),
        Document.project_id.in_(select(Project.id).where(Project.deleted_at.is_(None))),
    ]
    scope = accessible_filter(user, Document, db)
    if scope is not None:
        clauses.append(scope)
    return and_(*clauses)


def resolve_readable_chunks(
    db: Session,
    *,
    document_filter: ColumnElement[bool],
    collection_id: UUID | None = None,
    chunk_ids: list[UUID] | None = None,
    accessible_project_ids: list[UUID] | None = None,
) -> list[tuple[UUID, UUID]]:
    """Resolve ordered (chunk, project) IDs before cache or provider initialization.

    Collection order follows addition time, then chunk ID; direct inputs follow
    chunk ID. Always intersect any project scope with authoritative live parents.
    """
    query = db.query(DocumentChunk.id, Document.project_id).join(
        Document, Document.id == DocumentChunk.document_id
    ).join(Project, Project.id == Document.project_id).filter(
        document_filter, Document.deleted_at.is_(None), Project.deleted_at.is_(None)
    )
    if accessible_project_ids is not None:
        query = query.filter(Document.project_id.in_(accessible_project_ids))
    if collection_id is not None:
        query = query.join(CollectionItem, CollectionItem.chunk_id == DocumentChunk.id).filter(
            CollectionItem.collection_id == collection_id
        ).order_by(CollectionItem.added_at, DocumentChunk.id)
    else:
        query = query.filter(DocumentChunk.id.in_(chunk_ids or [])).order_by(DocumentChunk.id)
    return [(row.id, row.project_id) for row in query.all()]
