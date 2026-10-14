"""The production backfill classifies every old report without erasing a copy."""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import MetaData, Table, create_engine, inspect, select
from sqlalchemy.exc import IntegrityError

from alembic import command

pytestmark = pytest.mark.integration


def test_report_origin_backfill_priority_default_and_roundtrip(alembic_cfg, migration_db_url):
    engine = create_engine(migration_db_url)
    try:
        command.upgrade(alembic_cfg, "058_mission_log_attempts")
        metadata = MetaData()
        reports = Table("reports", metadata, autoload_with=engine)
        missions = Table("missions", metadata, autoload_with=engine)
        now = datetime.utcnow()
        base = dict(title="Retained", content="Original bytes", report_type="summary", version=1,
                    status="draft", tokens_used=0, chunk_count=0, created_at=now, updated_at=now)
        ids = [uuid4() for _ in range(6)]
        cases = [{"report_type": "evidence-ledger", "generation_provenance": {"origin": "librarian"}},
                 {"prompt": "Auto-generated from mission ORPHAN", "report_type": "evidence-ledger"},
                 {"report_type": "evidence-ledger", "generation_provenance": {"origin": "librarian"}},
                 {"generation_provenance": {"origin": "librarian"}}, {},
                 {"prompt": "auto-generated from mission is not the exact marker"}]
        with engine.begin() as db:
            for identity, fields in zip(ids, cases, strict=True):
                db.execute(reports.insert().values(id=identity, **(base | fields)))
            db.execute(missions.insert().values(id=uuid4(), mission_id="linked", title="Linked",
                       objective="Keep results", success_criteria=["Retained"], status="completed",
                       created_at=now, updated_at=now, result_report_id=ids[0]))
        command.upgrade(alembic_cfg, "head")
        reports = Table("reports", MetaData(), autoload_with=engine)
        with engine.begin() as db:
            actual = dict(db.execute(select(reports.c.id, reports.c.origin)).all())
            assert actual == dict(zip(ids, ["mission", "mission", "agent_brief", "librarian", "written", "written"], strict=True))
            assert set(db.execute(select(reports.c.content)).scalars()) == {"Original bytes"}
            identity = uuid4()
            db.execute(reports.insert().values(id=identity, **base))
            assert db.execute(select(reports.c.origin).where(reports.c.id == identity)).scalar_one() == "written"
        with pytest.raises(IntegrityError), engine.begin() as db:
            db.execute(reports.insert().values(id=uuid4(), origin="guessed", **base))
        command.downgrade(alembic_cfg, "058_mission_log_attempts")
        assert "origin" not in {c["name"] for c in inspect(engine).get_columns("reports")}
        command.upgrade(alembic_cfg, "head")
        with engine.connect() as db:
            assert len(db.execute(select(reports.c.id)).all()) == 7
    finally:
        engine.dispose()
