"""Real PostgreSQL proves append/replay serialize with the worker's lease writes."""

import copy
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from queue import Queue
from threading import Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.adapters.repositories.sqlalchemy_mission_log_repo import SQLAlchemyMissionLogRepository
from app.models.mission import Mission
from app.models.mission_log import MissionLog
from app.schemas.mission_logs import AttemptLogBatch
from app.services.mission_logs import MissionLogService

pytestmark = pytest.mark.integration
WIRE = json.loads((Path(__file__).parents[1]/'fixtures/mission-logs-v2/batch.json').read_text())


@pytest.fixture
def pg_logs(pg_engine):
    factory = sessionmaker(bind=pg_engine)
    wire = copy.deepcopy(WIRE)
    wire['mission_id'], wire['lease_token'] = str(uuid4()), str(uuid4())
    body = AttemptLogBatch.model_validate(wire)
    with factory.begin() as db:
        db.add(Mission(id=body.mission_id, mission_id=f'PG-LOG-{uuid4()}', title='Concurrency fixture', objective='Owned events',
                       success_criteria=['No successor contamination'], status='in_progress', deepsearch_attempt_count=1,
                       deepsearch_lease_owner=body.lease_owner, deepsearch_lease_token=wire['lease_token'],
                       deepsearch_lease_expires_at=datetime.now(UTC)+timedelta(minutes=5)))
    return factory, body, MissionLogService(SQLAlchemyMissionLogRepository())


def deliver(factory, service, body, pids=None):
    with factory() as db:
        if pids is not None:
            pids.put(db.scalar(text('SELECT pg_backend_pid()')))
        try:
            result = service.ingest(db, body.mission_id, body)
            return 201 if result.accepted else 200
        except HTTPException as exc:
            return exc.status_code


def wait_for_lock(factory, pid):
    deadline = time.monotonic()+5
    with factory() as db:
        while time.monotonic() < deadline:
            # Clear the statistics snapshot so each poll observes the wait now.
            db.execute(text('SELECT pg_stat_clear_snapshot()'))
            if db.scalar(text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"), {'pid':pid}) == 'Lock':
                return
            time.sleep(.02)
    pytest.fail('Expected a real PostgreSQL lock wait, not only a thread scheduling race')


def test_concurrent_identical_batches_have_one_insert_and_one_replay(pg_logs):
    factory, body, service = pg_logs
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _:deliver(factory,service,body), range(2))) == [200,201]
    with factory() as db:
        assert db.query(MissionLog).filter_by(mission_id=body.mission_id).count() == 1


def test_concurrent_changed_content_conflicts_without_overwriting_the_winner(pg_logs):
    factory, body, service = pg_logs
    other = body.model_copy(deep=True)
    other.logs[0].message = 'different observation'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda value:deliver(factory,service,value), [body,other])) == [201,409]
    with factory() as db:
        assert db.query(MissionLog).filter_by(mission_id=body.mission_id).count() == 1


@pytest.mark.parametrize('winner', ['requeue','reclaim','terminal','expiry'])
def test_log_request_waits_for_lease_writer_then_checks_fresh_state_and_time(pg_logs, winner):
    factory, body, service = pg_logs
    pids = Queue()
    with factory() as holder:
        mission = holder.scalar(select(Mission).where(Mission.id==body.mission_id).with_for_update(of=Mission))
        if winner == 'expiry':
            mission.deepsearch_lease_expires_at = datetime.now(UTC)+timedelta(milliseconds=200)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(deliver,factory,service,body,pids)
            wait_for_lock(factory,pids.get(timeout=5))
            if winner == 'requeue':
                mission.status = 'queued'
                mission.deepsearch_lease_owner = mission.deepsearch_lease_token = None
            elif winner == 'reclaim':
                mission.deepsearch_attempt_count = 2
                mission.deepsearch_lease_owner = 'successor'
                mission.deepsearch_lease_token = str(uuid4())
            elif winner == 'terminal':
                mission.status = 'completed'
                mission.deepsearch_lease_token = mission.deepsearch_lease_expires_at = None
                mission.deepsearch_result_key = hashlib.sha256(f'tracelab-missions-lease-v2:{body.mission_id}:1:{body.lease_token.get_secret_value()}'.encode()).hexdigest()
            else:
                time.sleep(.3)
            holder.commit()
            assert future.result(timeout=10) == (201 if winner == 'terminal' else 409)
    with factory() as db:
        assert db.query(MissionLog).filter_by(mission_id=body.mission_id).count() == (1 if winner == 'terminal' else 0)


def test_ingestion_holds_mission_lock_until_commit_before_reclaim_can_relabel_history(pg_logs):
    factory, body, _ = pg_logs
    locked, resume = Event(), Event()
    pids = Queue()
    class PausingRepository(SQLAlchemyMissionLogRepository):
        def append(self, db, rows):
            locked.set()
            assert resume.wait(10)
            super().append(db,rows)
    service = MissionLogService(PausingRepository())
    next_token = str(uuid4())
    def reclaim():
        with factory.begin() as db:
            pids.put(db.scalar(text('SELECT pg_backend_pid()')))
            db.execute(update(Mission).where(Mission.id==body.mission_id).values(
                deepsearch_attempt_count=2,deepsearch_lease_owner='successor',deepsearch_lease_token=next_token))
    with ThreadPoolExecutor(max_workers=2) as pool:
        ingestion = pool.submit(deliver,factory,service,body)
        assert locked.wait(5)
        writer = pool.submit(reclaim)
        try:
            wait_for_lock(factory,pids.get(timeout=5))
        finally:
            resume.set()
        assert ingestion.result(timeout=10) == 201
        writer.result(timeout=10)
    normal = MissionLogService(SQLAlchemyMissionLogRepository())
    assert deliver(factory,normal,body) == 409
    successor = body.model_copy(update={'attempt_count':2,'lease_owner':'successor'})
    wire = successor.model_dump(mode='json')
    wire['lease_token'] = next_token
    assert deliver(factory,normal,AttemptLogBatch.model_validate(wire)) == 201
    with factory() as db:
        assert [r.attempt_count for r in db.query(MissionLog).filter_by(mission_id=body.mission_id).order_by(MissionLog.attempt_count)] == [1,2]


def test_migration_preserves_legacy_history_and_enforces_both_identity_keys(alembic_cfg, migration_db_url):
    command.upgrade(alembic_cfg,'057_password_recovery_audit')
    engine = create_engine(migration_db_url)
    factory = sessionmaker(bind=engine)
    mission_id, legacy_id = uuid4(), uuid4()
    with factory.begin() as db:
        db.add(Mission(id=mission_id,mission_id='MIGRATION-LOG',title='History',objective='Retain legacy',success_criteria=['preserved']))
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO mission_logs (id,mission_id,level,message,logged_at,created_at) VALUES (:id,:mission,'INFO','legacy',now(),now())"),{'id':legacy_id,'mission':mission_id})
    command.upgrade(alembic_cfg,'head')
    with factory.begin() as db:
        old = db.get(MissionLog,legacy_id)
        assert old.message == 'legacy' and old.attempt_count is None and old.event_id is None
        db.add(MissionLog(mission_id=mission_id,attempt_count=1,event_id=uuid4(),sequence=1,message='new'))
    for duplicate in ('event','sequence'):
        with factory() as db:
            row = db.query(MissionLog).filter_by(mission_id=mission_id,attempt_count=1).one()
            with pytest.raises(IntegrityError), db.begin_nested():
                db.add(MissionLog(mission_id=mission_id,attempt_count=1,event_id=row.event_id if duplicate=='event' else uuid4(),sequence=2 if duplicate=='event' else 1,message='collision'))
                db.flush()
    command.downgrade(alembic_cfg,'057_password_recovery_audit')
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM mission_logs')).scalar() == 2
        assert 'event_id' not in {c['name'] for c in inspect(conn).get_columns('mission_logs')}
    command.upgrade(alembic_cfg,'head')
    engine.dispose()
