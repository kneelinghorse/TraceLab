"""PostgreSQL coverage for migration 052: personal Spaces (PERSONAL-1).

Why these assertions matter: the backfill decides where every existing person's
work lives. Derek's own Space must be designated, not duplicated (decision #531,
"yes to both"); a member's project must leave Default Workspace with its children
so nobody who later joins Default sees it; nothing privileged may move ("agree":
Default stays the owner's legacy bucket); and the pre-existing child drift is not
this migration's to touch. The downgrade must put every row back rather than
strand it with a NULL Space. Shared fixtures: conftest.py.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic import command

pytestmark = pytest.mark.integration

REV_051 = "051_usage_records"
REV_052 = "052_personal_spaces"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
DEREK_PRIVATE_ID = "081a5f9a-7629-45b7-bb53-5448bd050aec"


def _user(conn, display_name, role, *, active=True):
    user_id = uuid4()
    conn.execute(
        text(
            "INSERT INTO users (id, email, display_name, password_hash, role, is_active, "
            "created_at, updated_at) VALUES (:id, :email, :name, 'x', :role, :active, now(), now())"
        ),
        {"id": user_id, "email": f"{uuid4().hex}@example.com", "name": display_name, "role": role, "active": active},
    )
    return user_id


def _space(conn, name, member_id=None, space_id=None):
    space_id = space_id or uuid4()
    conn.execute(
        text("INSERT INTO workspaces (id, name, created_at) VALUES (:id, :name, now())"),
        {"id": space_id, "name": name},
    )
    if member_id is not None:
        conn.execute(
            text("INSERT INTO space_members (id, workspace_id, user_id) VALUES (:id, :ws, :user)"),
            {"id": uuid4(), "ws": space_id, "user": member_id},
        )
    return space_id


def _project(conn, owner_id, workspace_id):
    project_id = uuid4()
    conn.execute(
        text("INSERT INTO projects (id, name, owner_id, workspace_id) VALUES (:id, 'p', :o, :w)"),
        {"id": project_id, "o": owner_id, "w": workspace_id},
    )
    return project_id


def _children(conn, project_id, owner_id, workspace_id):
    """One document, mission and report under ``project_id``, all in ``workspace_id``."""
    ids = {"documents": uuid4(), "missions": uuid4(), "reports": uuid4()}
    params = {"pid": project_id, "o": owner_id, "w": workspace_id}
    conn.execute(
        text(
            "INSERT INTO documents (id, project_id, name, owner_id, workspace_id) "
            "VALUES (:id, :pid, 'd', :o, :w)"
        ),
        {"id": ids["documents"], **params},
    )
    conn.execute(
        text(
            "INSERT INTO missions (id, project_id, mission_id, title, objective, success_criteria, "
            "status, owner_id, workspace_id, created_at, updated_at) VALUES (:id, :pid, :mid, "
            "'Personal Space mission', 'Prove the mission follows its project', "
            "CAST(:criteria AS jsonb), 'draft', :o, :w, now(), now())"
        ),
        {"id": ids["missions"], "mid": f"P1-{uuid4().hex[:8]}", "criteria": json.dumps(["c"]), **params},
    )
    conn.execute(
        text(
            "INSERT INTO reports (id, project_id, title, report_type, content, status, tokens_used, "
            "chunk_count, owner_id, workspace_id, created_at, updated_at) VALUES (:id, :pid, 't', "
            "'markdown', 'b', 'draft', 0, 0, :o, :w, now(), now())"
        ),
        {"id": ids["reports"], **params},
    )
    return ids


def _space_of(conn, table, row_id):
    return str(
        conn.execute(
            text(f"SELECT workspace_id FROM {table} WHERE id = :id"),  # noqa: S608
            {"id": row_id},
        ).scalar()
    )


def _personal_spaces(conn):
    """{owner user id: (space id, name, member ids)} for every personal Space."""
    rows = conn.execute(
        text("SELECT id, name, personal_owner_id FROM workspaces WHERE personal_owner_id IS NOT NULL")
    ).fetchall()
    spaces = {}
    for space_id, name, owner in rows:
        members = conn.execute(
            text("SELECT user_id FROM space_members WHERE workspace_id = :ws"), {"ws": space_id}
        ).scalars()
        spaces[str(owner)] = (str(space_id), name, {str(m) for m in members})
    return spaces


class TestPersonalSpacesMigration:
    def test_backfill_then_downgrade_then_reupgrade(self, alembic_cfg, migration_db_url):
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_051)
            with engine.begin() as conn:
                derek = _user(conn, "kneelinghorse", "owner")
                admin = _user(conn, "Birch", "admin")
                guest = _user(conn, "Walkthrough Guest", "member")
                viewer = _user(conn, "Watcher", "viewer", active=False)
                service = _user(conn, "DeepSearch", "service")
                _space(conn, "Derek-Private", derek, space_id=DEREK_PRIVATE_ID)
                shared = _space(conn, "Walkthrough Guest", guest)

                moving = _project(conn, guest, DEFAULT_WORKSPACE_ID)
                children = _children(conn, moving, guest, DEFAULT_WORKSPACE_ID)
                drifted = uuid4()  # a child already out of step with its project
                conn.execute(
                    text("INSERT INTO documents (id, project_id, name, workspace_id) VALUES (:id, :p, 'x', :w)"),
                    {"id": drifted, "p": moving, "w": shared},
                )
                in_shared = _project(conn, guest, shared)
                derek_legacy = _project(conn, derek, DEFAULT_WORKSPACE_ID)
                admin_legacy = _project(conn, admin, DEFAULT_WORKSPACE_ID)
                guest_collection, derek_collection = uuid4(), uuid4()
                for coll_id, owner in ((guest_collection, guest), (derek_collection, derek)):
                    conn.execute(
                        text(
                            "INSERT INTO collections (id, name, created_at, owner_id, workspace_id) "
                            "VALUES (:id, 'c', now(), :o, :w)"
                        ),
                        {"id": coll_id, "o": owner, "w": DEFAULT_WORKSPACE_ID},
                    )
                humans = {
                    str(row[0])
                    for row in conn.execute(text("SELECT id FROM users WHERE role <> 'service'"))
                }

            command.upgrade(alembic_cfg, REV_052)

            insp = inspect(engine)
            column = {c["name"]: c for c in insp.get_columns("workspaces")}["personal_owner_id"]
            assert column["nullable"] is True
            fks = {
                (tuple(fk["constrained_columns"]), fk["referred_table"], (fk.get("options") or {}).get("ondelete"))
                for fk in insp.get_foreign_keys("workspaces")
            }
            assert (("personal_owner_id",), "users", "CASCADE") in fks
            uniques = {tuple(uc["column_names"]) for uc in insp.get_unique_constraints("workspaces")}
            assert ("personal_owner_id",) in uniques

            with engine.connect() as conn:
                spaces = _personal_spaces(conn)
                # One personal Space per human, including the inactive and the bootstrap
                # user; none for the service principal.
                assert set(spaces) == humans
                assert str(service) not in spaces
                for owner, (_space_id, _name, members) in spaces.items():
                    assert members == {owner}
                # Derek-Private is designated, keeps its name, and is his only one.
                assert spaces[str(derek)] == (DEREK_PRIVATE_ID, "Derek-Private", {str(derek)})
                assert spaces[str(guest)][1] == "Walkthrough Guest's Space"
                assert spaces[str(viewer)][1] == "Watcher's Space"

                guest_space = spaces[str(guest)][0]
                assert _space_of(conn, "projects", moving) == guest_space
                for table, row_id in children.items():
                    assert _space_of(conn, table, row_id) == guest_space, table
                assert _space_of(conn, "documents", drifted) == str(shared)
                assert _space_of(conn, "projects", in_shared) == str(shared)
                assert _space_of(conn, "projects", derek_legacy) == DEFAULT_WORKSPACE_ID
                assert _space_of(conn, "projects", admin_legacy) == DEFAULT_WORKSPACE_ID
                assert _space_of(conn, "collections", guest_collection) == guest_space
                assert _space_of(conn, "collections", derek_collection) == DEFAULT_WORKSPACE_ID

            command.downgrade(alembic_cfg, REV_051)

            assert "personal_owner_id" not in {c["name"] for c in inspect(engine).get_columns("workspaces")}
            with engine.connect() as conn:
                names = set(conn.execute(text("SELECT name FROM workspaces")).scalars())
                assert names == {"Default Workspace", "Derek-Private", "Walkthrough Guest"}
                assert conn.execute(
                    text("SELECT count(*) FROM space_members WHERE workspace_id = :ws"),
                    {"ws": DEREK_PRIVATE_ID},
                ).scalar() == 1
                assert _space_of(conn, "projects", moving) == DEFAULT_WORKSPACE_ID
                for table, row_id in children.items():
                    assert _space_of(conn, table, row_id) == DEFAULT_WORKSPACE_ID, table
                assert _space_of(conn, "documents", drifted) == str(shared)
                assert _space_of(conn, "collections", guest_collection) == DEFAULT_WORKSPACE_ID
                for table in ("projects", "collections", "documents", "missions", "reports"):
                    stranded = conn.execute(
                        text(f"SELECT count(*) FROM {table} WHERE workspace_id IS NULL")  # noqa: S608
                    ).scalar()
                    assert stranded == 0, table

            command.upgrade(alembic_cfg, REV_052)
            with engine.connect() as conn:
                again = _personal_spaces(conn)
                assert set(again) == humans
                assert again[str(derek)][0] == DEREK_PRIVATE_ID
                assert _space_of(conn, "projects", moving) == again[str(guest)][0]
        finally:
            engine.dispose()

    def test_deleting_a_user_takes_their_personal_space(self, alembic_cfg, migration_db_url):
        """The CASCADE that lets the admin hard-delete leave no orphan Space; the
        user's projects survive, un-Spaced, through migration 030's SET NULL."""
        engine = create_engine(migration_db_url)
        try:
            command.upgrade(alembic_cfg, REV_051)
            with engine.begin() as conn:
                leaving = _user(conn, "Leaving", "member")
                project = _project(conn, leaving, DEFAULT_WORKSPACE_ID)
            command.upgrade(alembic_cfg, REV_052)

            with engine.begin() as conn:
                space_id = _personal_spaces(conn)[str(leaving)][0]
                assert _space_of(conn, "projects", project) == space_id
                conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": leaving})

            with engine.connect() as conn:
                assert conn.execute(
                    text("SELECT count(*) FROM workspaces WHERE id = :id"), {"id": space_id}
                ).scalar() == 0
                assert conn.execute(
                    text("SELECT count(*) FROM space_members WHERE workspace_id = :id"), {"id": space_id}
                ).scalar() == 0
                assert conn.execute(
                    text("SELECT workspace_id FROM projects WHERE id = :id"), {"id": project}
                ).scalar() is None
        finally:
            engine.dispose()
