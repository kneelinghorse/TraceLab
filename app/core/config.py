"""Application configuration and settings management."""
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


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
    qdrant_prefer_grpc: bool = False
    qdrant_timeout_seconds: float = 10.0
    
    # OpenAI
    openai_api_key: Optional[str] = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimension: int = 1536
    openai_chat_model: str = "gpt-4o-mini"
    openai_escalation_model: str = "gpt-4o"
    openai_chat_temperature: float = 0.2
    rag_default_max_tokens: int = 350
    rag_context_threshold: float = 0.7
    tiered_routing_threshold: float = 0.85
    tiered_weight_linguistic: float = 0.35
    tiered_weight_integrity: float = 0.35
    tiered_weight_provenance: float = 0.30
    
    # Semantic cache
    semantic_cache_enabled: bool = True
    semantic_cache_collection_name: str = "semantic_cache"
    semantic_cache_similarity_threshold: float = 0.92
    semantic_cache_ttl_seconds: int = 86400  # 24 hours
    semantic_cache_max_items: int = 20000

    # Hybrid search
    hybrid_search_semantic_weight: float = 0.7
    hybrid_search_keyword_weight: float = 0.3
    hybrid_search_keyword_language: str = "english"
    hybrid_search_result_multiplier: int = 2
    
    # API
    api_v1_prefix: str = "/api/v1"
    
    # Security & authentication
    secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    auth_username: str = "tracelab-admin"
    auth_password: Optional[str] = "changeme"
    auth_password_hash: Optional[str] = None
    cors_allowed_origins_dev: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cors_allowed_origins_prod: List[str] = Field(default_factory=list)
    cors_allowed_methods: List[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    )
    cors_allowed_headers: List[str] = Field(default_factory=lambda: ["Authorization", "Content-Type"])
    cors_allow_credentials: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"

    @property
    def cors_origins(self) -> List[str]:
        """Return CORS origins based on deployment environment."""
        if self.environment.lower() in {"production", "prod"}:
            return self.cors_allowed_origins_prod or []
        return self.cors_allowed_origins_dev or []


settings = Settings()
