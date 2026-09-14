"""Saved view persistence must work on the deployed migration chain, including cascade."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from alembic import command
from app.adapters.repositories.sqlalchemy_home_repo import SQLAlchemyHomeRepository
from app.adapters.repositories.sqlalchemy_mission_views_repo import SQLAlchemyMissionViewRepository
from app.core.security import AuthenticatedUser
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User
from app.models.user_saved_view import UserSavedView
from app.schemas.mission_views import MissionViewCreate

pytestmark = pytest.mark.integration
_HASH = "test-only"


def test_saved_views_migration_roundtrip_and_user_delete(alembic_cfg, migration_db_url):
    engine = create_engine(migration_db_url)
    try:
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(engine)
        assert {(fk["referred_table"], fk["options"]["ondelete"]) for fk in inspector.get_foreign_keys("user_saved_views")} == {("users", "CASCADE")}
        assert any(set(item["column_names"]) == {"user_id", "name"} for item in inspector.get_unique_constraints("user_saved_views"))
        assert any(item["column_names"] == ["user_id", "updated_at"] for item in inspector.get_indexes("user_saved_views"))
        with Session(engine) as db:
            user = User(email=f"{uuid4()}@example.test", display_name="View reader", password_hash=_HASH)
            db.add(user)
            db.flush()
            view = UserSavedView(user_id=user.id, name="At risk", filters={"view": "attention", "reason": ["blocked"]})
            db.add(view)
            db.commit()
            view_id = view.id
            db.delete(user)
            db.commit()
            db.expire_all()
            assert db.get(UserSavedView, view_id) is None
        command.downgrade(alembic_cfg, "046_collection_context")
        assert "user_saved_views" not in inspect(engine).get_table_names()
        command.upgrade(alembic_cfg, "head")
        assert "user_saved_views" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_postgres_counts_and_saved_views_track_reviewed_result_versions(db_session):
    user = User(email=f"{uuid4()}@example.test", display_name="View reader", password_hash=_HASH, role="admin")
    db_session.add(user)
    db_session.flush()
    principal = AuthenticatedUser(user_id=user.id, email=user.email, display_name=user.display_name, role=user.role)
    project = Project(name="Isolated review-version fixture", owner_id=user.id)
    db_session.add(project)
    db_session.flush()
    # The complete suite may contain committed artifacts. Count only this fresh
    # project, and prove that an unrelated completion cannot affect its view.
    unrelated = Mission(mission_id=uuid4().hex, title="Outside this view", objective="Exclude unrelated work",
                        success_criteria=["Stay outside the saved project filter"], status="completed", owner_id=user.id)
    db_session.add(unrelated)
    done = Mission(mission_id=uuid4().hex, title="Research result", objective="Explicit result review",
                   success_criteria=["Match live totals"], status="completed", owner_id=user.id, project_id=project.id)
    db_session.add(done)
    db_session.commit()
    home = SQLAlchemyHomeRepository()
    repository = SQLAlchemyMissionViewRepository()
    view = repository.create(db_session, principal, MissionViewCreate(name="Unreviewed", filters={"view": "attention", "reason": ["unreviewed"], "project_id": project.id}))
    assert home.attention(db_session, principal, now=datetime.utcnow(), project_id=project.id).by_reason["unreviewed"] == view.total == 1
    home.review_completion(db_session, principal, done.id, done.updated_at)
    assert repository.list(db_session, principal)[0].total == home.attention(db_session, principal, now=datetime.utcnow(), project_id=project.id).total == 0
    done.updated_at += timedelta(seconds=1)
    db_session.commit()
    assert repository.list(db_session, principal)[0].total == home.attention(db_session, principal, now=datetime.utcnow(), project_id=project.id).total == 1
