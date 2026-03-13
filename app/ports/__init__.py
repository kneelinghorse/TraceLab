# ABOUTME: Public API for hexagonal architecture port interfaces.
# ABOUTME: Exports all Protocol types for dependency injection via FastAPI Depends().

from app.ports.events import EventPublisher
from app.ports.external import EmbeddingPort, LLMPort, SearchPort, VectorDBPort
from app.ports.repositories import (
    ChunkRepository,
    CollectionRepository,
    DocumentRepository,
    MissionRepository,
    ProjectRepository,
    ReportRepository,
    SearchHistoryRepository,
    UserRepository,
)

__all__ = [
    # Repositories
    "DocumentRepository",
    "ProjectRepository",
    "ChunkRepository",
    "MissionRepository",
    "UserRepository",
    "CollectionRepository",
    "ReportRepository",
    "SearchHistoryRepository",
    # External
    "EmbeddingPort",
    "VectorDBPort",
    "LLMPort",
    "SearchPort",
    # Events
    "EventPublisher",
]
