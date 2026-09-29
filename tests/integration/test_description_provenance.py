"""LIB-3 migrations preserve legacy text; concurrent acceptance is one guarded write."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectUpdate
from app.services.librarian import LibrarianConflict
from app.services.librarian_description import accept_description, draft_description, restore_description
from app.services.librarian_model import ModelReply
from app.services.project_query_service import ProjectQueryService

pytestmark = pytest.mark.integration


def test_description_migration_preserves_legacy_and_downgrades(alembic_cfg, migration_db_url):
    command.upgrade(alembic_cfg, "053_report_citations")
    engine = create_engine(migration_db_url)
    identity = uuid4()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO projects (id, name, description) VALUES (:id, 'Legacy', 'Human text')"), {"id": identity})
    command.upgrade(alembic_cfg, "head")
    with engine.begin() as connection:
        assert tuple(connection.execute(text("SELECT description, description_revision, description_provenance FROM projects WHERE id=:id"), {"id": identity}).one()) == ("Human text", 0, None)
        connection.execute(text("UPDATE projects SET description_provenance='{}'::jsonb WHERE id=:id"), {"id": identity})
    command.downgrade(alembic_cfg, "053_report_citations")
    assert "description_revision" not in {c["name"] for c in inspect(engine).get_columns("projects")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT description FROM projects WHERE id=:id"), {"id": identity}).scalar() == "Human text"
    command.upgrade(alembic_cfg, "head")
    engine.dispose()


def test_concurrent_accept_is_idempotent_and_manual_aba_blocks_restore(pg_engine, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", False)
    factory = sessionmaker(bind=pg_engine)
    with factory.begin() as db:
        user = User(email=f"{uuid4()}@example.test", display_name="Description test", password_hash=str(uuid4()), role="admin")
        db.add(user)
        db.flush()
        project = Project(name="Description concurrency", description="Original", owner_id=user.id)
        db.add(project)
        db.flush()
        project_id = project.id
        principal = AuthenticatedUser(user_id=user.id, email=user.email, display_name="Test", role="admin")
    model = Mock(model_name="isolated-model")
    model.complete.return_value = ModelReply(content='{"description":"Planned research."}')
    with factory() as db:
        proposal = draft_description(db, principal, db.get(Project, project_id), "Plan research", Mock(model=model))
    def accept():
        with factory() as db:
            return accept_description(db, principal, db.get(Project, project_id), proposal["proposal_token"], proposal["description"])
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: accept(), range(2)))
    assert results[0] == results[1]
    assert results[0]["revision"] == 1
    with factory() as db:
        service = ProjectQueryService()
        for value in ("Manual text", proposal["description"]):
            service.update_project(db, project_id, ProjectUpdate(description=value))
        project = db.get(Project, project_id)
        assert project.description_revision == 3
        with pytest.raises(LibrarianConflict, match="later edit"):
            restore_description(db, principal, project, results[0]["provenance"]["proposal_id"])
    assert model.complete.call_count == 1
