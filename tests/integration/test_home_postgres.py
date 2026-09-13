"""Prove Home's SQL aggregates, review upsert and migration on real PostgreSQL."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command
from app.adapters.repositories.sqlalchemy_home_repo import SQLAlchemyHomeRepository
from app.core.security import AuthenticatedUser
from app.models.mission import Mission
from app.models.mission_review import MissionReview
from app.models.user import User

pytestmark = pytest.mark.integration
_HASH = "placeholder-not-a-real-hash"


def test_postgres_home_counts_and_per_result_review(db_session):
    user = User(
        id=uuid4(), email=f"{uuid4()}@example.test", display_name="Home reviewer", password_hash=_HASH, role="admin"
    )
    db_session.add(user)
    rows = [
        Mission(
            mission_id=uuid4().hex,
            title="PostgreSQL research",
            objective="Count all missions",
            success_criteria=["No page truncation"],
            status="completed",
        )
        for _ in range(143)
    ]
    db_session.add_all(rows)
    db_session.commit()
    principal = AuthenticatedUser(user_id=user.id, email=user.email, display_name=user.display_name, role="admin")
    repository = SQLAlchemyHomeRepository()
    body = repository.snapshot(db_session, principal, now=datetime.utcnow())
    assert body.missions.total == 143
    assert body.attention.total == 143
    assert len(body.attention.items) == 6
    row = rows[0]
    for _ in range(2):
        repository.review_completion(db_session, principal, row.id, row.updated_at)
    assert db_session.query(MissionReview).count() == 1
    assert repository.snapshot(db_session, principal, now=datetime.utcnow()).attention.total == 142
    row.updated_at += timedelta(seconds=1)
    db_session.commit()
    assert repository.snapshot(db_session, principal, now=datetime.utcnow()).attention.total == 143


def test_review_migration_chain_is_reversible_and_cascades(alembic_cfg, migration_db_url):
    engine = create_engine(migration_db_url)
    try:
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(engine)
        assert set(inspector.get_pk_constraint("user_mission_reviews")["constrained_columns"]) == {
            "user_id",
            "mission_id",
        }
        assert {
            (fk["referred_table"], fk["options"]["ondelete"])
            for fk in inspector.get_foreign_keys("user_mission_reviews")
        } == {("users", "CASCADE"), ("missions", "CASCADE")}
        command.downgrade(alembic_cfg, "043_deepsearch_evidence")
        assert "user_mission_reviews" not in inspect(engine).get_table_names()
        command.upgrade(alembic_cfg, "head")
        assert "user_mission_reviews" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
