"""Database connection and session management."""

import os
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Test requests may run on another thread; share the SQLite in-memory schema.
_engine_kwargs: dict[str, Any] = {"pool_pre_ping": True, "echo": settings.debug}
if os.environ.get("ENVIRONMENT") == "test" and make_url(settings.database_url).get_backend_name() == "sqlite":
    from sqlalchemy.pool import StaticPool

    _engine_kwargs.update(
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

engine = create_engine(settings.database_url, **_engine_kwargs)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency for FastAPI to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
