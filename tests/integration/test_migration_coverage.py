"""Schema-authority coverage gate (T45.2, sprint-45).

The sprint's definition of done is that Alembic alone reproduces the full schema —
so the dev-gated ``Base.metadata.create_all`` can be retired without losing any
table. This test is the standing evidence for that: it provisions a database with
``alembic upgrade head`` ONLY (no create_all), introspects it, and asserts every
ORM model table is present. Coverage diff must be 0.

It is also a guard going forward: add a model + table but forget the migration and
this fails — the exact gap that left sync_states uncovered (T45.1).

Enumeration note: the model set is built by importing EVERY app/models submodule,
not just the ``app.models`` package. ``app/models/__init__.py`` does not re-export
``MissionLog``, so a bare ``import app.models`` silently omits the mission_logs
table from Base.metadata (it only lands at full app boot, when routers import the
model). Importing all submodules makes the gate see the true model set and removes
that blind spot.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command

pytestmark = pytest.mark.integration

# Tables created by the migration chain that have no ORM model — allowed extras,
# not coverage gaps:
#   - alembic_version : alembic's own revision-bookkeeping table.
# The orphan `metadata` table from migration 001 was dropped by migration 036
# (T45.3), so a head database no longer carries it and it needs no allowlist entry.
NON_MODEL_TABLES = {"alembic_version"}


def _all_model_tables() -> set[str]:
    """Full ORM table set: import every app.models submodule so Base.metadata is
    complete regardless of what app/models/__init__.py happens to re-export."""
    import app.models
    from app.core.database import Base

    for mod in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module(f"app.models.{mod.name}")
    return set(Base.metadata.tables.keys())


class TestMigrationCoverage:
    def test_alembic_head_covers_every_model_table(self, alembic_cfg, migration_db_url):
        model_tables = _all_model_tables()

        engine = create_engine(migration_db_url)
        try:
            # Migrations only — this fixture's DB is never touched by create_all.
            command.upgrade(alembic_cfg, "head")
            db_tables = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

        # The gate: zero model tables missing from a migrations-only database.
        uncovered = model_tables - db_tables
        assert not uncovered, (
            f"{len(uncovered)} ORM model table(s) have no Alembic migration: "
            f"{sorted(uncovered)}. A migrations-only DB (CI/test/fresh prod) would "
            f"lack them — retiring create_all would break those tables."
        )

        # Symmetric sanity: anything in the DB that is not a model table must be a
        # known non-model extra; a surprise here means an undocumented table.
        unexpected = db_tables - model_tables - NON_MODEL_TABLES
        assert not unexpected, (
            f"migrations created table(s) with no ORM model and not in the known "
            f"non-model allowlist: {sorted(unexpected)}"
        )
