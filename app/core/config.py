"""Application configuration and settings management."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # App config
    app_name: str = "TraceLab Research Repository"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/tracelab"
    
    # Vector Database (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection_name: str = "research_chunks"
    
    # OpenAI
    openai_api_key: Optional[str] = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimension: int = 1536
    openai_chat_model: str = "gpt-4o-mini"
    openai_chat_temperature: float = 0.2
    rag_default_max_tokens: int = 350
    rag_context_threshold: float = 0.7
    
    # Semantic cache
    semantic_cache_enabled: bool = True
    semantic_cache_collection_name: str = "semantic_cache"
    semantic_cache_similarity_threshold: float = 0.92
    semantic_cache_ttl_seconds: int = 86400  # 24 hours
    semantic_cache_max_items: int = 20000
    
    # API
    api_v1_prefix: str = "/api/v1"
    
    # Security
    secret_key: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
