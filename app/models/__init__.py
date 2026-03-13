"""SQLAlchemy models for all core entities."""

from app.core.database import Base
from app.models.api_key import APIKey
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.graph_edge import GraphEdge
from app.models.idempotency import IdempotencyRecord
from app.models.ingestion_job import IngestionJob
from app.models.insight import Insight, InsightSource
from app.models.invite_code import InviteCode
from app.models.mission import Mission
from app.models.processing_status import DocumentProcessingStatus
from app.models.project import Project
from app.models.quality import QualityCheck
from app.models.report import Report, ReportSource
from app.models.saved_search import SavedSearch
from app.models.search_history import SearchHistory
from app.models.sync_state import SyncState
from app.models.synthesis_cache import SynthesisCache
from app.models.tag import DocumentTag, Tag
from app.models.user import User

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
    "APIKey",
    "Report",
    "ReportSource",
    "SynthesisCache",
    "GraphEdge",
    "User",
    "InviteCode",
]
