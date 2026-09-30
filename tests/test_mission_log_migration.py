"""SQLite's additive identity migration retains old logs through rollback."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_sqlite_log_identity_migration_preserves_existing_rows(monkeypatch):
    source=Path(__file__).resolve().parents[1]/'alembic/versions/058_mission_log_attempts.py'
    spec=importlib.util.spec_from_file_location('log_migration',source)
    migration=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE missions (id CHAR(36) PRIMARY KEY)'))
        conn.execute(text('CREATE TABLE mission_logs (id CHAR(36) PRIMARY KEY, mission_id CHAR(36) NOT NULL REFERENCES missions(id), message TEXT NOT NULL)'))
        conn.execute(text("INSERT INTO missions VALUES ('mission')"))
        conn.execute(text("INSERT INTO mission_logs VALUES ('log','mission','legacy observation')"))
        monkeypatch.setattr(migration,'op',Operations(MigrationContext.configure(conn)))
        migration.upgrade()
        assert tuple(conn.execute(text('SELECT message,attempt_count,event_id,sequence FROM mission_logs')).one()) == ('legacy observation',None,None,None)
        assert {c['name'] for c in inspect(conn).get_unique_constraints('mission_logs')} == {'uq_mission_log_event','uq_mission_log_sequence'}
        migration.downgrade()
        assert conn.execute(text('SELECT message FROM mission_logs')).scalar() == 'legacy observation'
        assert 'event_id' not in {c['name'] for c in inspect(conn).get_columns('mission_logs')}
