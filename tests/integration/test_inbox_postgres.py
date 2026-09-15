"""Inbox persistence must work on the deployed migration chain: cascade, index and the monotonic upsert."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, update
from sqlalchemy.orm import Session

from alembic import command
from app.adapters.repositories.sqlalchemy_home_repo import SQLAlchemyHomeRepository
from app.adapters.repositories.sqlalchemy_inbox_repo import SQLAlchemyInboxRepository
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.evidence_ledger import LedgerEntry, LedgerSource
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User
from app.models.user_inbox_state import UserInboxState

pytestmark = pytest.mark.integration
_HASH = "test-only"


def test_inbox_state_migration_roundtrip_index_and_user_delete(alembic_cfg, migration_db_url):
    engine = create_engine(migration_db_url)
    try:
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(engine)
        assert inspector.get_pk_constraint("user_inbox_state")["constrained_columns"] == ["user_id"]
        assert {(fk["referred_table"], fk["options"]["ondelete"]) for fk in inspector.get_foreign_keys("user_inbox_state")} == {("users", "CASCADE")}
        columns = {column["name"]: column for column in inspector.get_columns("user_inbox_state")}
        assert set(columns) == {"user_id", "seen_through", "updated_at"}
        assert not columns["seen_through"]["nullable"] and not columns["updated_at"]["nullable"]
        assert any(index["name"] == "ix_missions_status_completed_at" and index["column_names"] == ["status", "completed_at"]
                   for index in inspector.get_indexes("missions"))
        with Session(engine) as db:
            user = User(email=f"{uuid4()}@example.test", display_name="Inbox reader", password_hash=_HASH)
            db.add(user)
            db.flush()
            db.add(UserInboxState(user_id=user.id, seen_through=datetime.utcnow(), updated_at=datetime.utcnow()))
            db.commit()
            user_id = user.id
            assert db.get(UserInboxState, user_id).seen_through is not None
            db.delete(user)
            db.commit()
            db.expire_all()
            assert db.get(UserInboxState, user_id) is None
        command.downgrade(alembic_cfg, "047_user_saved_views")
        assert "user_inbox_state" not in inspect(engine).get_table_names()
        assert not any(index["name"] == "ix_missions_status_completed_at" for index in inspect(engine).get_indexes("missions"))
        command.upgrade(alembic_cfg, "head")
        assert "user_inbox_state" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_postgres_watermark_upsert_is_monotonic_and_sections_match_home(db_session, monkeypatch):
    # The shared integration database holds other fixtures; a scoped member sees only these rows.
    monkeypatch.setattr(settings, "rbac_enabled", True)
    now = datetime.utcnow()
    user = User(email=f"{uuid4()}@example.test", display_name="Inbox reader", password_hash=_HASH, role="member",
                created_at=now - timedelta(days=1))
    db_session.add(user)
    db_session.flush()
    principal = AuthenticatedUser(user_id=user.id, email=user.email, display_name=user.display_name, role=user.role)
    project = Project(name="Isolated inbox fixture", owner_id=user.id)
    db_session.add(project)
    db_session.flush()

    def mission(status, **kwargs):
        row = Mission(mission_id=uuid4().hex, title="PostgreSQL inbox", objective="Prove the watermark",
                      success_criteria=["Counts match"], status=status, owner_id=user.id, project_id=project.id, **kwargs)
        db_session.add(row)
        return row

    blocked = mission("blocked", completed_at=now - timedelta(hours=1))
    done = mission("completed", completed_at=now - timedelta(minutes=30))
    running = mission("in_progress", started_at=now)
    source = LedgerSource(project_id=project.id, source_url="https://example.test/source", source_url_hash=uuid4().hex * 2)
    db_session.add(source)
    db_session.flush()
    db_session.add(LedgerEntry(project_id=project.id, mission_id=done.id, session_key="pg-run", source_id=source.id,
                               claim="Finding", source_url=source.source_url, disposition="supporting", origin="deepsearch-worker",
                               created_at=now - timedelta(minutes=20)))
    db_session.commit()
    repository = SQLAlchemyInboxRepository()

    def unread(section):
        page = repository.list(db_session, principal, now=datetime.utcnow(), section=section, page=1, page_size=20, unread_only=True)
        return [item.session_key if section == "evidence" else item.id for item in page.items]

    def totals():
        counts = repository.summary(db_session, principal, now=datetime.utcnow()).unread
        return (counts.failures, counts.completions, counts.evidence)

    assert unread("failures") == [str(blocked.id)] and unread("completions") == [str(done.id)] and unread("evidence") == ["pg-run"]
    assert totals() == (1, 1, 1)
    assert repository.mark_seen(db_session, principal, now - timedelta(minutes=45), now=now) == now - timedelta(minutes=45)
    assert unread("failures") == [] and unread("completions") == [str(done.id)] and totals() == (0, 1, 1)
    # An older value never wins the upsert; a newer one does.
    assert repository.mark_seen(db_session, principal, now - timedelta(hours=2), now=now) == now - timedelta(minutes=45)
    assert repository.mark_seen(db_session, principal, now - timedelta(minutes=10), now=now) == now - timedelta(minutes=10)
    assert totals() == (0, 0, 0)
    assert db_session.query(UserInboxState).filter(UserInboxState.user_id == user.id).count() == 1

    # A DeepSearch-style direct terminal write is visible on the next read.
    terminal = datetime.utcnow()
    db_session.execute(update(Mission).where(Mission.id == running.id).values(status="validation_failed", completed_at=terminal, updated_at=terminal))
    db_session.commit()
    assert unread("failures") == [str(running.id)] and totals() == (1, 0, 0)

    home = SQLAlchemyHomeRepository().snapshot(db_session, principal, now=datetime.utcnow()).evidence_activity
    inbox = repository.list(db_session, principal, now=datetime.utcnow(), section="evidence", page=1, page_size=20, unread_only=False)
    assert home.total == inbox.total == 1
