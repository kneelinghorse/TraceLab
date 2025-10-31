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
    
    # API
    api_v1_prefix: str = "/api/v1"
    
    # Security
    secret_key: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

