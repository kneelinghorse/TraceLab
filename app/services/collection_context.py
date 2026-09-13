"""Project a readable collection into authored inputs, never execution state."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser
from app.ports.collection_context import CollectionContextRepository
from app.schemas.collection_context import CollectionDocumentPage, CollectionDocumentRead, CollectionMissionSeed


class CollectionContextService:
    def __init__(self, repository: CollectionContextRepository):
        self.repository = repository

    def documents(self, db: Session, user: AuthenticatedUser, collection_id: UUID, *, page: int, page_size: int) -> CollectionDocumentPage:
        return self.repository.documents(db, user, collection_id, page=page, page_size=page_size)

    def seed(self, db: Session, user: AuthenticatedUser, collection_id: UUID) -> CollectionMissionSeed:
        context = self.repository.context(db, user, collection_id)
        projects = {document.project_id for document in context.documents}
        references = [{"title": document.name, "document_id": str(document.id), "href": f"/documents/{document.id}"} for document in context.documents]
        inventory = "\n".join(f"- {document.name} (TraceLab document {document.id})" for document in context.documents)
        background = context.instructions or ""
        if inventory:
            background += "\n\nReference documents from this collection:\n" + inventory
        return CollectionMissionSeed(
            collection_id=context.id, title=f"Research: {context.name}"[:255],
            project_id=next(iter(projects)) if len(projects) == 1 else None,
            background=background.strip(), references=references,
            context={"collection_id": str(context.id), "document_ids": [str(document.id) for document in context.documents]},
        )

    def attach(self, db: Session, user: AuthenticatedUser, collection_id: UUID, document_id: UUID) -> CollectionDocumentRead:
        return self.repository.attach(db, user, collection_id, document_id)

    def detach(self, db: Session, user: AuthenticatedUser, collection_id: UUID, document_id: UUID) -> None:
        self.repository.detach(db, user, collection_id, document_id)
