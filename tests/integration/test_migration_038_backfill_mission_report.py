"""PostgreSQL coverage for migration 038 mission/report ownership backfill."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from alembic import command

pytestmark = pytest.mark.integration

REV_037 = "037_backfill_doc_coll_owner"
REV_038 = "038_backfill_mission_report"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
BOOTSTRAP_EMAIL = "tracelab-admin@tracelab.local"


class TestBackfillMissionReportOwnership:
    def test_038_backfills_from_parent_project(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_037)
            owner_id = uuid4()
            workspace_id = uuid4()
            project_id = uuid4()
            mission_id = uuid4()
            report_id = uuid4()
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, password_hash, role, "
                        "is_active, created_at, updated_at) "
                        "VALUES (:id, :email, 'Owner', 'x', 'member', true, now(), now())"
                    ),
                    {"id": owner_id, "email": "project-owner@example.com"},
                )
                conn.execute(
                    text(
                        "INSERT INTO workspaces (id, name, created_at) "
                        "VALUES (:id, 'Project workspace', now())"
                    ),
                    {"id": workspace_id},
                )
                conn.execute(
                    text(
                        "INSERT INTO projects (id, name, owner_id, workspace_id) "
                        "VALUES (:id, 'Owned project', :owner_id, :workspace_id)"
                    ),
                    {
                        "id": project_id,
                        "owner_id": owner_id,
                        "workspace_id": workspace_id,
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO missions "
                        "(id, project_id, mission_id, title, objective, success_criteria, "
                        "status, created_at, updated_at) "
                        "VALUES (:id, :project_id, 'T48.8-gap', 'Gap mission', "
                        "'Backfill ownership safely', '[\"ownership inherited\"]'::jsonb, "
                        "'draft', now(), now())"
                    ),
                    {"id": mission_id, "project_id": project_id},
                )
                conn.execute(
                    text(
                        "INSERT INTO reports "
                        "(id, project_id, title, report_type, content, status, tokens_used, "
                        "chunk_count, created_at, updated_at) "
                        "VALUES (:id, :project_id, 'Gap report', 'markdown', 'body', 'draft', "
                        "0, 0, now(), now())"
                    ),
                    {"id": report_id, "project_id": project_id},
                )

            command.upgrade(alembic_cfg, REV_038)

            with engine.connect() as conn:
                for table, row_id in (("missions", mission_id), ("reports", report_id)):
                    row = conn.execute(
                        text(
                            f"SELECT owner_id, workspace_id FROM {table} WHERE id = :id"  # noqa: S608
                        ),
                        {"id": row_id},
                    ).one()
                    assert str(row.owner_id) == str(owner_id)
                    assert str(row.workspace_id) == str(workspace_id)
        finally:
            engine.dispose()

    def test_038_is_convergent_and_preserves_existing_attribution(
        self, alembic_cfg, migration_db_url
    ):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_037)
            with engine.connect() as conn:
                bootstrap_id = conn.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": BOOTSTRAP_EMAIL},
                ).scalar_one()

            assigned_owner = uuid4()
            project_id = uuid4()
            mission_id = uuid4()
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, password_hash, role, "
                        "is_active, created_at, updated_at) "
                        "VALUES (:id, 'assigned@example.com', 'Assigned', 'x', 'member', "
                        "true, now(), now())"
                    ),
                    {"id": assigned_owner},
                )
                conn.execute(
                    text("INSERT INTO projects (id, name) VALUES (:id, 'Gap project')"),
                    {"id": project_id},
                )
                conn.execute(
                    text(
                        "INSERT INTO missions "
                        "(id, project_id, mission_id, title, objective, success_criteria, "
                        "status, owner_id, created_at, updated_at) "
                        "VALUES (:id, :project_id, 'T48.8-preserve', 'Preserve mission', "
                        "'Preserve explicit ownership', '[\"no clobber\"]'::jsonb, 'draft', "
                        ":owner_id, now(), now())"
                    ),
                    {
                        "id": mission_id,
                        "project_id": project_id,
                        "owner_id": assigned_owner,
                    },
                )

            command.upgrade(alembic_cfg, REV_038)
            command.downgrade(alembic_cfg, REV_037)
            command.upgrade(alembic_cfg, REV_038)

            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT owner_id, workspace_id FROM missions WHERE id = :id"
                    ),
                    {"id": mission_id},
                ).one()
            assert str(row.owner_id) == str(assigned_owner)
            assert str(row.workspace_id) == DEFAULT_WORKSPACE_ID
            assert str(row.owner_id) != str(bootstrap_id)
        finally:
            engine.dispose()

    def test_038_noops_without_users(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_037)
            project_id = uuid4()
            report_id = uuid4()
            with engine.begin() as conn:
                conn.execute(text("TRUNCATE TABLE users CASCADE"))
                conn.execute(
                    text("INSERT INTO projects (id, name) VALUES (:id, 'No owner')"),
                    {"id": project_id},
                )
                conn.execute(
                    text(
                        "INSERT INTO reports "
                        "(id, project_id, title, report_type, content, status, tokens_used, "
                        "chunk_count, created_at, updated_at) "
                        "VALUES (:id, :project_id, 'No owner report', 'markdown', 'body', "
                        "'draft', 0, 0, now(), now())"
                    ),
                    {"id": report_id, "project_id": project_id},
                )

            command.upgrade(alembic_cfg, REV_038)

            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT owner_id, workspace_id FROM reports WHERE id = :id"
                    ),
                    {"id": report_id},
                ).one()
            assert row.owner_id is None
            assert row.workspace_id is None
        finally:
            engine.dispose()
