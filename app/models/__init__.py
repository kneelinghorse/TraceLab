"""SQLAlchemy models for all core entities."""
from app.core.database import Base
from app.models.project import Project
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.models.tag import Tag, DocumentTag
from app.models.insight import Insight, InsightSource
from app.models.mission import Mission
from app.models.quality import QualityCheck
from app.models.processing_status import DocumentProcessingStatus
from app.models.ingestion_job import IngestionJob
from app.models.idempotency import IdempotencyRecord
from app.models.search_history import SearchHistory
from app.models.saved_search import SavedSearch
from app.models.sync_state import SyncState
from app.models.collection import Collection, CollectionItem

__all__ = [
    "Base",
    "Project",
    "Document",
    "DocumentChunk",
    "Tag",
    "DocumentTag",
    "Insight",
    "InsightSource",
    "Mission",
    "QualityCheck",
    "DocumentProcessingStatus",
    "IngestionJob",
    "IdempotencyRecord",
    "SearchHistory",
    "SavedSearch",
    "SyncState",
    "Collection",
    "CollectionItem",
]
