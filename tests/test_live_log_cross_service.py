"""Opt-in real HTTP proof against a checked-out DeepSearch sender (no providers).

DEEPSEARCH_SOURCE_ROOT=/path/to/DeepSearch.alpha pytest tests/test_live_log_cross_service.py
The external checkout is required deliberately: vendoring a fake sender would
miss the cross-repository contract this test exists to protect.
"""

import asyncio
import json
import logging
import os
import socket
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from test_mission_log_delivery import log_case  # noqa: F401 - shared owned-row fixture

from app.core import security
from app.core.database import get_db
from app.main import app
from app.models.api_key import APIKey
from app.models.mission_log import MissionLog
from app.models.user import User


@pytest.mark.skipif(not os.environ.get('DEEPSEARCH_SOURCE_ROOT'), reason='Requires explicit DeepSearch checkout; run the LOG-2 cross-service command')
def test_real_sender_receives_replay_ack_and_streams_before_terminal(log_case, monkeypatch):  # noqa: F811 - imported pytest fixture
    root = Path(os.environ['DEEPSEARCH_SOURCE_ROOT']).resolve()
    assert (root / 'deepsearch/tracelab/log_handler.py').is_file()
    monkeypatch.syspath_prepend(str(root))
    from deepsearch.tracelab.auth import TraceLabAuth
    from deepsearch.tracelab.log_handler import TracelabLogHandler
    from deepsearch.worker.lease import LeaseAttempt

    _, db, mission, payload, headers = log_case
    assert json.loads((root / 'tests/fixtures/mission-logs-v2/batch.json').read_text()) == json.loads(
        (Path(__file__).parent / 'fixtures/mission-logs-v2/batch.json').read_text())
    engine = create_engine(db.get_bind().url, poolclass=NullPool,
                           connect_args={'check_same_thread': False, 'timeout': 10})
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(security, 'SessionLocal', factory)
    def independent_session():
        with factory() as connection:
            yield connection
    monkeypatch.setitem(app.dependency_overrides, get_db, independent_session)
    received = []
    faults = ['unavailable', 'lost_ack']

    async def receiver(scope, receive, send):
        if scope.get('method') != 'POST' or not scope.get('path', '').endswith('/logs/v2'):
            return await app(scope, receive, send)
        chunks = []
        async def capture_body():
            message = await receive()
            chunks.append(message.get('body', b''))
            return message
        fault = faults.pop(0) if faults else None
        if fault == 'unavailable':
            await send({'type': 'http.response.start', 'status': 503, 'headers': []})
            await send({'type': 'http.response.body', 'body': b''})
            return
        async def delayed_ack(message):
            if message['type'] == 'http.response.start':
                received.append((time.monotonic(), message['status'], json.loads(b''.join(chunks))))
                if fault == 'lost_ack':
                    await asyncio.sleep(1.5)  # Commit succeeded; caller times out before ACK.
            await send(message)
        await app(scope, capture_body, delayed_ack)

    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    origin = f'http://127.0.0.1:{sock.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(receiver, lifespan='off', log_level='critical', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    key = security.generate_api_key()
    db.add(APIKey(user_id=db.query(User).filter_by(role='service').one().id, name='Local log proof',
                  key_hash=security.hash_api_key(key), key_prefix=security.get_key_prefix(key)))
    db.commit()
    auth = TraceLabAuth(base_url=origin, api_key=key, username='', password='', timeout=2)
    now = datetime.now(UTC)
    lease = LeaseAttempt(payload['lease_owner'], payload['lease_token'], now, now,
                         now + timedelta(minutes=5), payload['attempt_count'])
    handler = TracelabLogHandler(str(mission.id), lease=lease, auth=auth, timeout=1, backoff_base=0,
                                 flush_threshold=100)
    def emit(event):
        record = logging.LogRecord('deepsearch.cross_service', logging.INFO, '', 0,
                                   'Private prompt and signed URL must stay internal', (), None)
        record.tracelab_event = event
        handler.emit(record)
    def wait_for_count(count):
        until = time.monotonic() + 8
        while time.monotonic() < until:
            db.expire_all()
            if db.query(MissionLog).filter_by(mission_id=mission.id).count() == count:
                return
            time.sleep(0.02)
        pytest.fail(f'Expected {count} observations within the five-second delivery cadence')
    try:
        auth.require_service_role()
        assert handler.start_live_delivery(), handler.get_telemetry()
        first_emit = time.monotonic()
        emit('phase_started')
        wait_for_count(1)
        # Let the lost ACK retry complete before the second independent batch.
        until = time.monotonic()+3
        while handler.get_telemetry()['pending_entries'] and time.monotonic() < until:
            time.sleep(0.02)
        assert handler.get_telemetry()['accepted_entries'] == 1
        assert received[0][1] == 201 and received[1][1] == 200
        assert received[0][2] == received[1][2]
        emit('mission_progress')
        wait_for_count(2)
        db.refresh(mission)
        assert mission.status == 'in_progress' and mission.deepsearch_result_key is None
        with httpx.Client() as reader:
            visible = reader.get(f'{origin}/api/v1/missions/{mission.id}/logs', headers=headers['member'])
        assert visible.status_code == 200 and len(visible.json()) == 2
        assert 'Private prompt' not in visible.text and lease.token not in visible.text
        assert received[0][0] - first_emit < 8
        assert len({batch[2]['logs'][0]['event_id'] for batch in received}) == 2
        mission.status = 'completed'
        mission.deepsearch_lease_token = mission.deepsearch_lease_expires_at = None
        mission.deepsearch_result_key = lease.persistence_key(str(mission.id))
        db.commit()
        emit('phase_completed')
        handler.close()
        wait_for_count(3)
        assert handler.get_telemetry()['pending_entries'] == 0
        # A successor never legitimizes a prior attempt, including terminal retries.
        stale = TracelabLogHandler(str(mission.id), lease=lease, auth=auth, max_attempts=1)
        record = logging.LogRecord('deepsearch', logging.INFO, '', 0, 'stale', (), None)
        stale.emit(record)
        mission.status = 'in_progress'
        mission.deepsearch_attempt_count = 2
        mission.deepsearch_lease_token = 'successor-fixture'  # noqa: S105 - local ownership fixture
        mission.deepsearch_result_key = None
        mission.deepsearch_lease_expires_at = datetime.now(UTC)+timedelta(minutes=5)
        db.commit()
        stale.flush()
        assert stale.get_telemetry()['last_status_code'] == 409
        assert stale.get_telemetry()['discarded_entries'] == 1
        stale.discard()
        db.expire_all()
        assert db.query(MissionLog).filter_by(mission_id=mission.id).count() == 3
        assert {row.attempt_count for row in db.query(MissionLog).filter_by(mission_id=mission.id)} == {1}
        successor_lease = LeaseAttempt(lease.owner, 'successor-fixture', now, now,
                                       now+timedelta(minutes=5), 2)
        successor = TracelabLogHandler(str(mission.id), lease=successor_lease, auth=auth,
                                       max_pending_entries=2, flush_threshold=100)
        for _ in range(3):
            successor.emit(record)
        assert successor.get_telemetry()['overflowed_entries'] == 1
        successor.flush()
        successor.discard()
        db.expire_all()
        rows = db.query(MissionLog).filter_by(mission_id=mission.id).all()
        assert len(rows) == 5
        assert sorted(row.sequence for row in rows if row.attempt_count == 2) == [2, 3]
        assert sum(row.attempt_count == 1 for row in rows) == 3
    finally:
        handler.discard()
        server.should_exit = True
        thread.join(5)
        sock.close()
        engine.dispose()
        assert not thread.is_alive()
