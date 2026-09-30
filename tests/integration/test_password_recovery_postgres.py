"""Real PostgreSQL proves single-consumption and the credential issuance/reset fence."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.api.v1.auth import create_api_key, login, refresh_token
from app.api.v1.auth_device import approve_device_grant
from app.core.config import settings
from app.core.security import _to_authenticated_user, hash_password, verify_password
from app.models.api_key import APIKey
from app.models.device_authorization import DeviceAuthorizationGrant
from app.models.password_recovery import PasswordRecovery
from app.models.user import User
from app.schemas.api_key import APIKeyCreate
from app.schemas.auth import LoginRequest
from app.schemas.device_auth import DeviceApproveRequest
from app.services.password_recovery import PasswordRecoveryService

pytestmark = pytest.mark.integration


@pytest.fixture
def pg_recovery(pg_engine, monkeypatch):
    monkeypatch.setattr(settings, "frontend_url", "https://tracelab.test")
    factory = sessionmaker(bind=pg_engine)
    mail = AsyncMock()
    mail.send.return_value = "provider-ack"
    service = PasswordRecoveryService(factory, mail)
    with factory.begin() as db:
        user = User(email=f"{uuid4()}@controlled.org", display_name="Recovery race", password_hash=hash_password("original-password"), role="member")
        db.add(user)
        db.flush()
        principal = _to_authenticated_user(user)
    asyncio.run(service.request(principal.email))
    token = mail.send.call_args.args[0].text.split("#token=", 1)[1].split()[0]
    return factory, service, principal, token


def test_migration_preserves_users_and_fk_purge(alembic_cfg, migration_db_url):
    command.upgrade(alembic_cfg, "055_collection_review")
    engine = create_engine(migration_db_url)
    user_id = uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id,email,display_name,password_hash,role,is_active) VALUES (:id,'legacy@controlled.org','Legacy','original-hash','member',true)"), {"id": user_id})
    command.upgrade(alembic_cfg, "head")
    with engine.begin() as conn:
        assert tuple(conn.execute(text("SELECT password_hash,credential_version FROM users WHERE id=:id"), {"id": user_id}).one()) == ("original-hash", 0)
        conn.execute(text("INSERT INTO password_recoveries (user_id,token_hash,credential_version,requested_at,expires_at,delivery_status) VALUES (:id,'digest',0,now(),now(),'accepted')"), {"id": user_id})
        conn.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
        assert conn.execute(text("SELECT count(*) FROM password_recoveries")).scalar() == 0
    command.downgrade(alembic_cfg, "055_collection_review")
    assert "credential_version" not in {c["name"] for c in inspect(engine).get_columns("users")}
    assert "password_recoveries" not in inspect(engine).get_table_names()
    command.upgrade(alembic_cfg, "head")
    engine.dispose()


def test_concurrent_redemption_has_exactly_one_winner(pg_recovery):
    factory, service, principal, token = pg_recovery
    def redeem(_):
        with factory() as db:
            try:
                service.confirm(db, token, "replacement-password")
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(redeem, range(2))) == [200, 400]
    with factory() as db:
        user = db.get(User, principal.user_id)
        assert user.credential_version == 1
        assert verify_password("replacement-password", user.password_hash)
        assert db.get(PasswordRecovery, user.id) is None


@pytest.mark.parametrize("operation", ["key", "device", "refresh", "login"])
def test_already_authenticated_writer_waits_for_reset_and_then_fails(pg_recovery, operation):
    factory, service, principal, token = pg_recovery
    started = Event()
    with factory() as reset_db:
        reset_db.query(User).filter(User.id == principal.user_id).with_for_update().one()
        def stale_write():
            with factory() as db:
                started.set()
                try:
                    if operation == "key":
                        create_api_key(APIKeyCreate(name="stale"), principal, db)
                    elif operation == "device":
                        approve_device_grant(DeviceApproveRequest(user_code="BCDF-GHJK"), principal, db)
                    elif operation == "refresh":
                        refresh_token(principal, db)
                    else:
                        login(LoginRequest(email=principal.email, password="original-password"),  # noqa: S106 - isolated fixture
                              Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1234)}), db)
                    return 200
                except HTTPException as exc:
                    return exc.status_code
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(stale_write)
            assert started.wait(5)
            service.confirm(reset_db, token, "replacement-password")
            assert future.result(timeout=10) == 401
    with factory() as db:
        assert db.query(APIKey).filter_by(user_id=principal.user_id).count() == 0


def test_api_key_authentication_racing_reset_cannot_borrow_new_revision(pg_recovery, monkeypatch):
    from app.core import security

    factory, service, principal, token = pg_recovery
    monkeypatch.setattr(security, "SessionLocal", factory)
    with factory() as db:
        key = create_api_key(APIKeyCreate(name="before reset"), principal, db).key
    started = Event()
    with factory() as db:
        db.query(User).filter(User.id == principal.user_id).with_for_update().one()
        def authenticate():
            started.set()
            return security._validate_api_key(key)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(authenticate)
            assert started.wait(5)
            service.confirm(db, token, "replacement-password")
            assert future.result(timeout=10) is None


def test_slow_key_hash_does_not_hold_the_user_lock_but_rechecks_revocation(pg_recovery, monkeypatch):
    from app.core import security

    factory, service, principal, token = pg_recovery
    monkeypatch.setattr(security, "SessionLocal", factory)
    with factory() as db:
        key = create_api_key(APIKeyCreate(name="slow verification"), principal, db).key
    hashing, resume = Event(), Event()
    verify = security.verify_api_key
    def slow_verify(plain, hashed):
        hashing.set()
        assert resume.wait(10)
        return verify(plain, hashed)
    monkeypatch.setattr(security, "verify_api_key", slow_verify)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(security._validate_api_key, key)
        assert hashing.wait(5)
        try:
            with factory() as db:
                db.execute(text("SET LOCAL lock_timeout = '2s'"))
                service.confirm(db, token, "replacement-password")
        finally:
            resume.set()
        assert future.result(timeout=10) is None


def test_reset_deletes_device_children_before_keys_and_preserves_pending(pg_recovery):
    factory, service, principal, token = pg_recovery
    with factory.begin() as db:
        key = APIKey(user_id=principal.user_id, name="device", key_hash="unused", key_prefix="tl_fixture")
        db.add(key)
        db.flush()
        approved = DeviceAuthorizationGrant(device_code=str(uuid4()), user_code=str(uuid4())[:8], client_label="test", status="approved", user_id=principal.user_id, api_key_id=key.id, expires_at=datetime.utcnow()+timedelta(minutes=5))
        pending = DeviceAuthorizationGrant(device_code=str(uuid4()), user_code=str(uuid4())[:8], client_label="test", status="pending", expires_at=datetime.utcnow()+timedelta(minutes=5))
        db.add_all([approved, pending])
        db.flush()
        approved_id, pending_id = approved.id, pending.id
    with factory() as db:
        service.confirm(db, token, "replacement-password")
        assert db.get(DeviceAuthorizationGrant, approved_id) is None
        assert db.get(DeviceAuthorizationGrant, pending_id).status == "pending"


def test_admin_and_public_request_share_the_database_cooldown(pg_recovery):
    from app.models.password_recovery import PasswordRecoveryAudit

    factory, service, principal, _ = pg_recovery
    with factory.begin() as db:
        db.get(PasswordRecovery, principal.user_id).requested_at = datetime.utcnow() - timedelta(minutes=2)
    service.sender.reset_mock()

    def request(admin):
        try:
            return asyncio.run(service.request(None, target_user_id=principal.user_id, actor_user_id=principal.user_id)) if admin else asyncio.run(service.request(principal.email))
        except HTTPException as exc:
            assert exc.status_code == 429
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(request, [True, False])) == [False, True]
    assert service.sender.send.call_count == 1
    with factory() as db:
        audit = db.query(PasswordRecoveryAudit).filter_by(target_user_id=principal.user_id).one()
        assert audit.outcome in {"accepted", "rate_limited"}
        assert db.get(User, principal.user_id).credential_version == 0
        assert db.get(PasswordRecovery, principal.user_id).delivery_status == "accepted"


def test_admin_audit_migration_keeps_history_after_deletion(alembic_cfg, migration_db_url):
    command.upgrade(alembic_cfg, "056_password_recovery")
    engine = create_engine(migration_db_url)
    actor, target, audit = uuid4(), uuid4(), uuid4()
    with engine.begin() as conn:
        for user_id in (actor, target):
            conn.execute(text("INSERT INTO users (id,email,display_name,password_hash,role,is_active) VALUES (:id,:email,'Audit fixture','unused','member',true)"), {"id":user_id,"email":f"{user_id}@controlled.org"})
    command.upgrade(alembic_cfg, "057_password_recovery_audit")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO password_recovery_audits VALUES (:id,:actor,:target,now(),now(),'accepted')"), {"id":audit,"actor":actor,"target":target})
        conn.execute(text("DELETE FROM users WHERE id IN (:actor,:target)"), {"actor":actor,"target":target})
        assert tuple(conn.execute(text("SELECT actor_user_id,target_user_id,outcome FROM password_recovery_audits WHERE id=:id"), {"id":audit}).one()) == (actor, target, "accepted")
    command.downgrade(alembic_cfg, "056_password_recovery")
    assert "password_recovery_audits" not in inspect(engine).get_table_names()
    assert "password_recoveries" in inspect(engine).get_table_names()
    command.upgrade(alembic_cfg, "head")
    engine.dispose()
