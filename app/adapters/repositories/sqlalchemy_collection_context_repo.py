"""Complete scoped collection context, with policy checks before every mutation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Query, Session

from app.core.authorization import accessible_filter
from app.core.security import AuthenticatedUser
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.collection_document import CollectionDocument
from app.models.document import Document
from app.models.project import Project
from app.schemas.collection_context import CollectionContext, CollectionDocumentPage, CollectionDocumentRead


def _collection(db: Session, user: AuthenticatedUser, collection_id: UUID) -> Collection:
    query = db.query(Collection).filter(Collection.id == collection_id)
    scope = accessible_filter(user, Collection, db)
    if scope is not None:
        query = query.filter(scope)
    collection = query.first()
    if collection is None:
        raise LookupError("Collection not found.")
    return collection


def _readable_documents(db: Session, user: AuthenticatedUser) -> Query[Document]:
    query = db.query(Document).join(Project, Document.project_id == Project.id).filter(Document.deleted_at.is_(None), Project.deleted_at.is_(None))
    for model in (Document, Project):
        scope = accessible_filter(user, model, db)
        if scope is not None:
            query = query.filter(scope)
    return query


def _context_documents(db: Session, user: AuthenticatedUser, collection_id: UUID) -> Query[Document]:
    direct = exists(select(CollectionDocument.document_id).where(CollectionDocument.collection_id == collection_id, CollectionDocument.document_id == Document.id))
    excerpts = exists(select(CollectionItem.id).join(DocumentChunk, CollectionItem.chunk_id == DocumentChunk.id).where(CollectionItem.collection_id == collection_id, DocumentChunk.document_id == Document.id))
    return _readable_documents(db, user).filter(or_(direct, excerpts)).order_by(Document.name.asc(), Document.id)


def _document(db: Session, user: AuthenticatedUser, document_id: UUID) -> Document:
    document = _readable_documents(db, user).filter(Document.id == document_id).first()
    if document is None:
        raise LookupError("Document not found.")
    return document


class SQLAlchemyCollectionContextRepository:
    def documents(self, db: Session, user: AuthenticatedUser, collection_id: UUID, *, page: int, page_size: int) -> CollectionDocumentPage:
        _collection(db, user, collection_id)
        query = _context_documents(db, user, collection_id)
        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        return CollectionDocumentPage(items=[CollectionDocumentRead.model_validate(row) for row in rows], total=total, page=page, page_size=page_size)

    def context(self, db: Session, user: AuthenticatedUser, collection_id: UUID) -> CollectionContext:
        collection = _collection(db, user, collection_id)
        documents = _context_documents(db, user, collection_id).all()
        return CollectionContext(id=collection.id, name=collection.name, instructions=collection.instructions, documents=[CollectionDocumentRead.model_validate(row) for row in documents])

    def attach(self, db: Session, user: AuthenticatedUser, collection_id: UUID, document_id: UUID) -> CollectionDocumentRead:
        collection = _collection(db, user, collection_id)
        document = _document(db, user, document_id)
        insert = pg_insert(CollectionDocument) if db.get_bind().dialect.name == "postgresql" else sqlite_insert(CollectionDocument)
        db.execute(insert.values(collection_id=collection_id, document_id=document_id).on_conflict_do_nothing())
        collection.updated_at = datetime.utcnow()
        db.commit()
        return CollectionDocumentRead.model_validate(document)

    def detach(self, db: Session, user: AuthenticatedUser, collection_id: UUID, document_id: UUID) -> None:
        collection = _collection(db, user, collection_id)
        _document(db, user, document_id)
        db.query(CollectionDocument).filter(CollectionDocument.collection_id == collection_id, CollectionDocument.document_id == document_id).delete(synchronize_session=False)
        chunks = select(DocumentChunk.id).where(DocumentChunk.document_id == document_id)
        db.query(CollectionItem).filter(CollectionItem.collection_id == collection_id, CollectionItem.chunk_id.in_(chunks)).delete(synchronize_session=False)
        collection.updated_at = datetime.utcnow()
        db.commit()
