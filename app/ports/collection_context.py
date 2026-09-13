"""Persistence boundary for independently authorized collection context."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.schemas.collection_context import CollectionContext, CollectionDocumentPage, CollectionDocumentRead


class CollectionContextRepository(Protocol):
    def documents(self, db: Session, user: AuthenticatedUser, collection_id: UUID, *, page: int, page_size: int) -> CollectionDocumentPage: ...

    def context(self, db: Session, user: AuthenticatedUser, collection_id: UUID) -> CollectionContext: ...

    def attach(self, db: Session, user: AuthenticatedUser, collection_id: UUID, document_id: UUID) -> CollectionDocumentRead: ...

    def detach(self, db: Session, user: AuthenticatedUser, collection_id: UUID, document_id: UUID) -> None: ...
