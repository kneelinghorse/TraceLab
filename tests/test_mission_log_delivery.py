"""A log observation is evidence from an owned attempt, never an unfenced append."""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.models.mission import Mission
from app.models.mission_log import MissionLog
from app.models.user import User

WIRE = json.loads((Path(__file__).parent / 'fixtures/mission-logs-v2/batch.json').read_text())
VERSION = 'tracelab-mission-logs-v2'


@pytest.fixture
def log_case(db_session, monkeypatch):
    monkeypatch.setattr(settings, 'rbac_enabled', True)
    users = {}
    for role in ('service', 'member', 'owner', 'admin'):
        user = User(email=f'{role}-{uuid4()}@controlled.test', display_name=role, role=role, password_hash='unused')  # noqa: S106 - no password authentication in isolated fixture
        db_session.add(user)
        db_session.flush()
        users[role] = user
    payload = copy.deepcopy(WIRE)
    mission = Mission(id=uuid4(), mission_id=f'LOG-{uuid4()}', title='Owned log fixture', objective='Record safe progress', success_criteria=['Owned observations only'],
                      owner_id=users['member'].id, status='in_progress', deepsearch_attempt_count=1,
                      deepsearch_lease_owner=payload['lease_owner'], deepsearch_lease_token=payload['lease_token'],
                      deepsearch_lease_expires_at=datetime.now(UTC)+timedelta(minutes=5))
    db_session.add(mission)
    db_session.commit()
    payload['mission_id'] = str(mission.id)
    headers = {role: {'Authorization':f'Bearer {create_access_token(subject=str(user.id))}'} for role,user in users.items()}
    return TestClient(app), db_session, mission, payload, headers


def post(case, payload=None, role='service', versioned=True):
    client, _, mission, original, headers = case
    return client.post(f'/api/v1/missions/{mission.id}/logs'+('/v2' if versioned else ''),
                       json=payload or original, headers=headers[role] if role else {})


def test_negotiated_http_fixture_and_lost_ack_replay_leave_one_observation(log_case):
    client, db, mission, body, headers = log_case
    caps = client.get(f'/api/v1/missions/{mission.id}/logs/capabilities', headers=headers['service'])
    assert caps.status_code == 200 and caps.json()['contract_version'] == VERSION
    response = post(log_case)
    assert response.status_code == 201, response.text
    assert response.json() == {'contract_version':VERSION, 'mission_id':str(mission.id), 'attempt_count':1,
                               'accepted':1, 'replayed':0, 'event_ids':[body['logs'][0]['event_id']]}
    row = db.query(MissionLog).filter_by(mission_id=mission.id).one()
    before = (row.id, row.created_at)
    replay = post(log_case)
    assert replay.status_code == 200 and replay.json()['replayed'] == 1
    assert replay.json()['accepted'] == 0
    db.expire_all()
    rows = db.query(MissionLog).filter_by(mission_id=mission.id).all()
    assert [(r.id,r.created_at) for r in rows] == [before]
    read = client.get(f'/api/v1/missions/{mission.id}/logs',headers=headers['member'])
    assert read.status_code == 200 and read.json()[0]['attempt_count'] == 1
    assert read.json()[0]['sequence'] == 1 and read.json()[0]['event_id'] == body['logs'][0]['event_id']
    assert body['lease_token'] not in read.text and 'lease_owner' not in read.text
    db.refresh(mission)
    assert mission.status == 'in_progress' and mission.deepsearch_result_key is None
    assert not mission.result_markdown and not mission.result_report_id


@pytest.mark.parametrize('field,value', [('deepsearch_lease_owner','another-worker'), ('deepsearch_lease_token','other-proof'),
    ('deepsearch_attempt_count',2), ('status','queued'), ('status','cancelled'),
    ('deepsearch_lease_expires_at',datetime(2000,1,1,tzinfo=UTC))])
def test_lost_ownership_never_accepts_even_an_exact_replay(log_case, field, value):
    assert post(log_case).status_code == 201
    _, db, mission, body, _ = log_case
    setattr(mission,field,value)
    db.commit()
    response = post(log_case)
    assert response.status_code == 409
    assert body['lease_token'] not in response.text
    assert db.query(MissionLog).filter_by(mission_id=mission.id).count() == 1


@pytest.mark.parametrize('status', ['completed','blocked','validation_failed'])
def test_terminal_result_identity_allows_final_flush_after_active_token_is_cleared(log_case, status):
    _, db, mission, body, _ = log_case
    mission.status = status
    mission.deepsearch_lease_token = None
    mission.deepsearch_lease_expires_at = None
    mission.deepsearch_result_key = hashlib.sha256(f"tracelab-missions-lease-v2:{mission.id}:1:{body['lease_token']}".encode()).hexdigest()
    db.commit()
    assert post(log_case).status_code == 201
    assert post(log_case).json()['replayed'] == 1
    body['lease_token'] = str(uuid4())
    assert post(log_case).status_code == 409


@pytest.mark.parametrize('change', ['message','event_id','sequence','logged_at','level','source'])
def test_changed_identity_is_atomic_conflict_and_never_overwrites_history(log_case, change):
    assert post(log_case).status_code == 201
    _, db, mission, original, _ = log_case
    body = copy.deepcopy(original)
    replacements = {'message':'changed','event_id':str(uuid4()),'sequence':2,'logged_at':'2026-10-01T00:00:00Z','level':'ERROR','source':'other'}
    body['logs'][0][change] = replacements[change]
    body['logs'].append({**original['logs'][0], 'event_id':str(uuid4()), 'sequence':3})
    response = post(log_case,body)
    assert response.status_code == 409
    assert db.query(MissionLog).filter_by(mission_id=mission.id).count() == 1


@pytest.mark.parametrize('role', ['owner','admin','member',None])
@pytest.mark.parametrize('enabled', [True,False])
def test_machine_writes_and_negotiation_are_service_only_in_both_policy_modes(log_case, monkeypatch, role, enabled):
    monkeypatch.setattr(settings,'rbac_enabled',enabled)
    client, _, mission, _, headers = log_case
    expected = 403 if role else 401
    assert post(log_case,role=role).status_code == expected
    assert client.get(f'/api/v1/missions/{mission.id}/logs/capabilities',headers=headers[role] if role else {}).status_code == expected
    assert post(log_case,{'logs':[{'message':'untrusted'}]},role=role,versioned=False).status_code == expected


@pytest.mark.parametrize('mutation', ['wrong_mission','oversized','too_many','empty','duplicate_id','duplicate_sequence','mixed_attempt','naive_time','unknown_version','proof_extra','proof_message','proof_source'])
def test_invalid_batch_never_partially_inserts_or_echoes_private_proof(log_case, mutation):
    _, db, mission, original, _ = log_case
    body = copy.deepcopy(original)
    if mutation == 'wrong_mission':
        body['mission_id'] = str(uuid4())
    elif mutation == 'oversized':
        body['logs'][0]['message'] = 'x'*2049
    elif mutation == 'too_many':
        body['logs'] *= 201
    elif mutation == 'empty':
        body['logs'] = []
    elif mutation == 'duplicate_id':
        body['logs'].append({**body['logs'][0], 'sequence':2})
    elif mutation == 'duplicate_sequence':
        body['logs'].append({**body['logs'][0], 'event_id':str(uuid4())})
    elif mutation == 'mixed_attempt':
        body['logs'][0]['attempt_count'] = 2
    elif mutation == 'naive_time':
        body['logs'][0]['logged_at'] = '2026-09-30T12:00:00'
    elif mutation == 'unknown_version':
        body['contract_version'] = 'unknown'
    elif mutation == 'proof_extra':
        body['other'] = body['lease_token']
    elif mutation == 'proof_message':
        body['logs'][0]['message'] = body['lease_token']
    elif mutation == 'proof_source':
        body['logs'][0]['source'] = body['lease_token']
    response = post(log_case,body)
    assert response.status_code in {409,422}
    assert original['lease_token'] not in response.text
    assert db.query(MissionLog).filter_by(mission_id=mission.id).count() == 0


def test_canonical_timestamp_replay_and_equal_time_sequence_order_with_legacy_history(log_case):
    client, db, mission, body, headers = log_case
    db.add(MissionLog(mission_id=mission.id,message='old history',logged_at=datetime(2020,1,1)))
    db.commit()
    body['logs'].append({**body['logs'][0],'sequence':2,'event_id':str(uuid4())})
    body['logs'].reverse()
    assert post(log_case).status_code == 201
    body['logs'][0]['logged_at'] = '2026-09-30T07:00:00-05:00'
    assert post(log_case).json()['replayed'] == 2
    read = client.get(f'/api/v1/missions/{mission.id}/logs?limit=2',headers=headers['member'])
    assert [row['sequence'] for row in read.json()] == [1,2]
    all_rows = client.get(f'/api/v1/missions/{mission.id}/logs',headers=headers['member']).json()
    assert all_rows[0]['message'] == 'old history' and all_rows[0]['attempt_count'] is None


def test_simultaneous_sqlite_http_retries_do_not_duplicate_the_observation(log_case, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    from app.core import security
    from app.core.database import get_db

    # The shared unit-test engine uses StaticPool (one physical connection).
    # A race needs independent connections to the same real SQLite file.
    _, db, mission, _, _ = log_case
    engine = create_engine(db.get_bind().url, poolclass=NullPool, connect_args={"check_same_thread":False, "timeout":10})
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(security, "SessionLocal", factory)
    def independent_session():
        with factory() as connection:
            yield connection
    monkeypatch.setitem(app.dependency_overrides, get_db, independent_session)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(lambda _:post(log_case).status_code,range(2))) == [200,201]
        assert db.query(MissionLog).filter_by(mission_id=mission.id).count() == 1
    finally:
        engine.dispose()


def test_retired_legacy_route_never_appends_even_with_terminal_proof(log_case):
    _, db, mission, body, _ = log_case
    legacy = {'entries':[{'level':'INFO','message':'old runner','phase':'complete','ts':'2026-09-30T12:00:00Z'}]}
    assert post(log_case,legacy,versioned=False).status_code == 426
    assert post(log_case,body,versioned=False).status_code == 422
    mission.status = 'completed'
    mission.deepsearch_lease_token = mission.deepsearch_lease_expires_at = None
    mission.deepsearch_result_key = hashlib.sha256(f"tracelab-missions-lease-v2:{mission.id}:1:{body['lease_token']}".encode()).hexdigest()
    db.commit()
    assert post(log_case,legacy,versioned=False).status_code == 426
    assert post(log_case).status_code == 201
    assert post(log_case,legacy,versioned=False).status_code == 426
    assert db.query(MissionLog).filter_by(mission_id=mission.id,attempt_count=None).count() == 0


def test_outsider_and_service_cannot_read_even_valid_owned_observations(log_case):
    client, db, mission, _, headers = log_case
    outsider = User(email='outsider@controlled.test',display_name='Outsider',role='member',password_hash='unused')  # noqa: S106 - no password authentication in isolated fixture
    db.add(outsider)
    db.commit()
    outsider_header = {'Authorization':f'Bearer {create_access_token(subject=str(outsider.id))}'}
    assert post(log_case).status_code == 201
    assert client.get(f'/api/v1/missions/{mission.id}/logs',headers=outsider_header).status_code == 403
    assert client.get(f'/api/v1/missions/{mission.id}/logs',headers=headers['service']).status_code == 403


def test_partial_replay_ack_preserves_request_order_and_original_receipt(log_case):
    client, db, mission, body, _ = log_case
    assert post(log_case).status_code == 201
    original = db.query(MissionLog).filter_by(mission_id=mission.id).one()
    receipt = original.created_at
    body['logs'].insert(0, {**body['logs'][0], 'event_id':str(uuid4()), 'sequence':2})
    response = post(log_case)
    assert response.status_code == 201
    assert response.json()['accepted'] == response.json()['replayed'] == 1
    assert response.json()['event_ids'] == [entry['event_id'] for entry in body['logs']]
    body['logs'].reverse()
    replay = post(log_case)
    assert replay.status_code == 200 and replay.json()['replayed'] == 2
    db.refresh(original)
    assert original.created_at == receipt
    assert db.query(MissionLog).filter_by(mission_id=mission.id).count() == 2
    responses = client.get('/openapi.json').json()['paths']['/api/v1/missions/{mission_id}/logs/v2']['post']['responses']
    assert set(responses) >= {'200', '201', '409', '422'}
