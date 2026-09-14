# ABOUTME: Composition root for dependency injection via FastAPI Depends().
# ABOUTME: Wires port protocols to concrete adapter implementations.

from __future__ import annotations

import logging

from app.adapters.external.openai_embedding import OpenAIEmbeddingAdapter
from app.adapters.external.openai_llm import OpenAILLMAdapter
from app.adapters.external.qdrant_vectordb import QdrantVectorDBAdapter
from app.adapters.repositories.sqlalchemy_document_repo import SQLAlchemyDocumentRepository
from app.adapters.repositories.sqlalchemy_mission_repo import SQLAlchemyMissionRepository
from app.adapters.repositories.sqlalchemy_project_repo import SQLAlchemyProjectRepository
from app.core.config import settings
from app.ports.external import EmbeddingPort, LLMPort, VectorDBPort
from app.ports.navigation_search import NavigationSearchRepository
from app.ports.repositories import DocumentRepository, MissionRepository, ProjectRepository
from app.services.admin_stats import AdminStatsService
from app.services.collection_context import CollectionContextService
from app.services.home import HomeService

logger = logging.getLogger(__name__)


def get_document_repository() -> DocumentRepository:
    """Provide a DocumentRepository backed by SQLAlchemy."""
    return SQLAlchemyDocumentRepository()


def get_project_repository() -> ProjectRepository:
    """Provide a ProjectRepository backed by SQLAlchemy."""
    return SQLAlchemyProjectRepository()


def get_mission_repository() -> MissionRepository:
    """Provide a MissionRepository backed by SQLAlchemy."""
    return SQLAlchemyMissionRepository()


def get_collection_context_service() -> CollectionContextService:
    """Wire complete readable collection context to authoring projection."""
    from app.adapters.repositories.sqlalchemy_collection_context_repo import SQLAlchemyCollectionContextRepository

    return CollectionContextService(SQLAlchemyCollectionContextRepository())


def get_home_service() -> HomeService:
    """Wire Home's scoped aggregate repository to its service."""
    from app.adapters.repositories.sqlalchemy_home_repo import SQLAlchemyHomeRepository

    return HomeService(SQLAlchemyHomeRepository())


def get_navigation_search_repository() -> NavigationSearchRepository:
    """Provide scoped SQL name lookup for the command palette."""
    from app.adapters.repositories.sqlalchemy_navigation_search_repo import SQLAlchemyNavigationSearchRepository

    return SQLAlchemyNavigationSearchRepository()


def get_embedding_port() -> EmbeddingPort | None:
    """Provide an EmbeddingPort backed by OpenAI, or None if unconfigured."""
    if not settings.openai_api_key:
        return None
    try:
        from app.services.embedding_service import get_embedding_service

        return OpenAIEmbeddingAdapter(get_embedding_service())
    except Exception:
        logger.warning("EmbeddingPort unavailable: OpenAI not configured", exc_info=True)
        return None


def get_vector_db_port() -> VectorDBPort | None:
    """Provide a VectorDBPort backed by Qdrant, or None if unconfigured."""
    try:
        from app.services.qdrant_service import get_qdrant_service

        return QdrantVectorDBAdapter(get_qdrant_service())
    except Exception:
        logger.warning("VectorDBPort unavailable: Qdrant not configured", exc_info=True)
        return None


def get_llm_port() -> LLMPort | None:
    """Provide an LLMPort backed by OpenAI, or None if unconfigured."""
    if not settings.openai_api_key:
        return None
    try:
        return OpenAILLMAdapter()
    except Exception:
        logger.warning("LLMPort unavailable: OpenAI not configured", exc_info=True)
        return None


def get_admin_stats_service() -> AdminStatsService:
    """Wire persisted counts and external worker health without contacting it yet."""
    from app.adapters.external.worker_probe import HTTPWorkerProbe
    from app.adapters.repositories.sqlalchemy_admin_stats_repo import SQLAlchemyAdminStatsRepository

    return AdminStatsService(SQLAlchemyAdminStatsRepository(), HTTPWorkerProbe())
