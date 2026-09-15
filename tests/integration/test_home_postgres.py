"""Prove Home's SQL aggregates, per-item viewed marks and migration 049 on real PostgreSQL."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command
from app.adapters.repositories.sqlalchemy_activity_repo import SQLAlchemyActivityRepository
from app.adapters.repositories.sqlalchemy_home_repo import SQLAlchemyHomeRepository
from app.core.authorization import accessible_filter
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.mission import Mission
from app.models.user import User
from app.models.user_item_view import UserItemView
from app.schemas.activity import ViewedItem
from app.services.mission_service import MissionService

pytestmark = pytest.mark.integration
_HASH = "placeholder-not-a-real-hash"


def test_postgres_home_counts_and_per_item_viewed_marks(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    user = User(
        id=uuid4(), email=f"{uuid4()}@example.test", display_name="Home reader", password_hash=_HASH, role="member"
    )
    db_session.add(user)
    db_session.flush()
    now = datetime.utcnow()
    rows = [
        Mission(
            mission_id=uuid4().hex,
            title="PostgreSQL research",
            objective="Count all missions",
            success_criteria=["No page truncation"],
            status="completed",
            completed_at=now - timedelta(minutes=index),
            owner_id=user.id,
        )
        for index in range(143)
    ]
    db_session.add_all(rows)
    # The shared integration database may already contain other fixtures. A
    # caller's total must include every owned row and exclude unrelated ones.
    db_session.add(
        Mission(
            mission_id=uuid4().hex,
            title="Another caller's result",
            objective="Keep ownership scoped",
            success_criteria=["Hidden from this reader"],
            status="completed",
        )
    )
    db_session.commit()
    principal = AuthenticatedUser(user_id=user.id, email=user.email, display_name=user.display_name, role="member")
    repository = SQLAlchemyHomeRepository()
    activity = SQLAlchemyActivityRepository()
    body = repository.snapshot(db_session, principal, now=datetime.utcnow())
    assert body.missions.total == 143
    assert body.activity.total == 143 and body.activity.new_total == 143
    assert len(body.activity.items) == 10 and body.activity.items[0].id == rows[0].id
    row = rows[0]
    for _ in range(2):
        activity.mark_viewed(db_session, principal, [ViewedItem(type="mission", id=row.id, occurred_at=row.completed_at)], now=now)
    assert db_session.query(UserItemView).filter(UserItemView.user_id == user.id).count() == 1
    assert activity.summary(db_session, principal, now=datetime.utcnow()).new_total == 142
    row.completed_at += timedelta(seconds=1)
    db_session.commit()
    assert activity.summary(db_session, principal, now=datetime.utcnow()).new_total == 143

    # The job list is recency-sorted over the full scope and ignores status for order.
    rows[1].status = "validation_failed"
    rows[2].status = "blocked"
    db_session.commit()
    service = MissionService()
    scope = accessible_filter(principal, Mission, db_session)
    first, meta = service.list_missions(db_session, page_size=3, access_filter=scope)
    assert meta.total == 143
    assert {item.id for item in first} <= {row.id for row in rows}
    _, updated_meta = service.list_missions(db_session, sort="updated_desc", access_filter=scope)
    assert updated_meta.total == 143


def test_activity_migration_replaces_the_three_preference_tables_reversibly(alembic_cfg, migration_db_url):
    engine = create_engine(migration_db_url)
    try:
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "user_item_views" in tables
        assert not {"user_inbox_state", "user_mission_reviews", "user_saved_views"} & tables
        assert set(inspector.get_pk_constraint("user_item_views")["constrained_columns"]) == {
            "user_id", "item_type", "item_id",
        }
        assert "ix_missions_status_completed_at" in {index["name"] for index in inspector.get_indexes("missions")}
        command.downgrade(alembic_cfg, "048_user_inbox_state")
        tables = set(inspect(engine).get_table_names())
        assert "user_item_views" not in tables
        assert {"user_inbox_state", "user_mission_reviews", "user_saved_views"} <= tables
        command.upgrade(alembic_cfg, "head")
        assert "user_item_views" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
