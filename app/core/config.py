"""Application configuration and settings management."""

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
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "research_chunks"
    qdrant_prefer_grpc: bool = False
    qdrant_timeout_seconds: float = 10.0
    # HNSW tuning for 3072d vectors (text-embedding-3-large)
    # T30.4 re-tuned for 3072d (was 1536d in B19.3).
    # Higher dimensions need higher m for graph quality; ef_construct raised for index quality.
    # ef_search=64 retained — Sprint 19 showed 100% recall at current corpus.
    qdrant_hnsw_m: int = 24  # Graph degree (was 16 for 1536d)
    qdrant_hnsw_ef_construct: int = (
        128  # Index construction quality (was 100 for 1536d)
    )
    qdrant_hnsw_ef_default: int = 64  # Query-time ef (100% recall at 7K corpus)

    # OpenAI
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-large"
    openai_embedding_dimension: int = 3072
    openai_chat_model: str = "gpt-5.1"
    openai_escalation_model: str = "gpt-5.2"
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
    access_token_expire_minutes: int = 10080  # 7 days
    auth_username: str = "tracelab-admin"
    auth_password: str | None = "changeme"
    auth_password_hash: str | None = None
    cors_allowed_origins_dev: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    cors_allowed_origins_prod: list[str] = Field(default_factory=list)
    cors_allowed_methods: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    )
    cors_allowed_headers: list[str] = Field(
        default_factory=lambda: ["Authorization", "Content-Type"]
    )
    cors_allow_credentials: bool = True

    # Frontend URL — used to build the device-code verification_uri (T42.4)
    # the MCP client prints to its terminal. Dev defaults to localhost; prod
    # deployments override via env var.
    frontend_url: str = "http://localhost:3000"

    # PEDR cache settings
    pedr_cache_max_size: int = 1000  # Max cached queries
    pedr_cache_ttl_seconds: int = 300  # 5 minutes TTL
    pedr_cache_enabled: bool = True
    pedr_candidate_multiplier: int = 3

    # DeepSearch integration
    # Mode: "worker" (DB polling, Railway prod) or "http" (API calls, local dev)
    deepsearch_mode: str = "worker"
    deepsearch_api_url: str | None = None
    deepsearch_api_key: str | None = None
    deepsearch_timeout: float = 30.0
    deepsearch_retries: int = 3
    deepsearch_backoff_multiplier: float = 2.0
    deepsearch_initial_backoff: float = 1.0
    deepsearch_webhook_secret: str | None = None
    # T40.4: renamed shared secret that both TraceLab and DeepSearch use for
    # HMAC signing/verification across all service-to-service calls (inbound
    # webhooks + outbound preview proxy). The old deepsearch_webhook_secret
    # env var continues to work as a transitional fallback; deepsearch_secret
    # takes precedence when both are set.
    deepsearch_tracelab_service_secret: str | None = None
    # DeepSearch worker health endpoint (for console monitoring)
    deepsearch_worker_health_url: str = "http://localhost:8080/health"
    # Where to POST the contract-preview request (T40.4). Falls back to
    # deepsearch_api_url when unset — useful when preview lives alongside the
    # main API.
    deepsearch_preview_url: str | None = None

    # Evidence auto-linking (T29.6: difflib → embeddings)
    auto_link_similarity_threshold: float = 0.78
    auto_link_top_k: int = 3
    auto_link_fallback_to_difflib: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"

    @property
    def cors_origins(self) -> list[str]:
        """Return CORS origins based on deployment environment."""
        if self.environment.lower() in {"production", "prod"}:
            return self.cors_allowed_origins_prod or []
        return self.cors_allowed_origins_dev or []

    @property
    def effective_deepsearch_service_secret(self) -> str | None:
        """Resolve the shared service secret (T40.4).

        Prefers ``deepsearch_tracelab_service_secret``; falls back to the
        legacy ``deepsearch_webhook_secret`` so existing deployments keep
        working during the rename. Returns None if neither is set, in which
        case HMAC validation is skipped (dev-only mode — prod must have one).
        """
        return (
            self.deepsearch_tracelab_service_secret
            or self.deepsearch_webhook_secret
            or None
        )


settings = Settings()
