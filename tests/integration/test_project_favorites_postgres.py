"""Favorite persistence is proven on migrated PostgreSQL, including rollback."""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command
from app.adapters.repositories.sqlalchemy_home_repo import SQLAlchemyHomeRepository
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.project import Project
from app.models.user import User
from app.models.user_favorite import UserFavorite

pytestmark = pytest.mark.integration

_HASH = "placeholder-not-a-real-hash"


def test_favorites_migration_roundtrip(alembic_cfg, migration_db_url):
    engine = create_engine(migration_db_url)
    try:
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(engine)
        assert set(inspector.get_pk_constraint("user_favorites")["constrained_columns"]) == {"user_id", "entity_type", "entity_id"}
        assert {(fk["referred_table"], fk["options"]["ondelete"]) for fk in inspector.get_foreign_keys("user_favorites")} == {("users", "CASCADE"), ("projects", "CASCADE")}
        command.downgrade(alembic_cfg, "044_home_mission_reviews")
        assert "user_favorites" not in inspect(engine).get_table_names()
        command.upgrade(alembic_cfg, "head")
        assert "user_favorites" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_postgres_favorites_isolation_paging_and_cascade(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    users = [User(email=f"{uuid4()}@example.test", display_name="Favorite reader", password_hash=_HASH, role="admin") for _ in range(2)]
    db_session.add_all(users)
    db_session.flush()
    principals = [AuthenticatedUser(user_id=u.id, email=u.email, display_name=u.display_name, role=u.role) for u in users]
    projects = [Project(name=f"Favorite {index}", owner_id=users[0].id) for index in range(9)]
    db_session.add_all(projects)
    db_session.commit()
    repository = SQLAlchemyHomeRepository()
    for project in projects:
        for _ in range(2):
            repository.set_favorite(db_session, principals[0], project.id, favorite=True)
    assert db_session.query(UserFavorite).filter(UserFavorite.user_id == users[0].id).count() == 9
    first = repository.snapshot(db_session, principals[0], now=datetime.utcnow()).favorites
    second = repository.favorites(db_session, principals[0], page=2)
    assert first.total == second.total == 9
    assert len(first.items) == 6 and len(second.items) == 3
    assert not ({item.id for item in first.items} & {item.id for item in second.items})
    assert repository.snapshot(db_session, principals[1], now=datetime.utcnow()).favorites.total == 0
    db_session.delete(projects[0])
    db_session.commit()
    assert db_session.query(UserFavorite).filter(UserFavorite.user_id == users[0].id).count() == 8
