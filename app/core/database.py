"""Database connection and session management."""
import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create database engine — use StaticPool for SQLite test databases to prevent
# connection pool race conditions during repeated drop_all/create_all cycles.
_engine_kwargs: dict = {"pool_pre_ping": True, "echo": settings.debug}
if os.environ.get("ENVIRONMENT") == "test" and "sqlite" in settings.database_url:
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

