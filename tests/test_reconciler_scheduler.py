"""OPS-2: in-app reconciler scheduler — tick outcomes and /health exposure."""

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services import reconciler_scheduler as sched


@pytest.fixture(autouse=True)
def _reset_state():
    sched._state = sched.ReconcilerState()
    yield
    sched._state = sched.ReconcilerState()
    sched.stop_reconciler()


def _summary(scanned=5, eligible=2, repaired=2, failed=0):
    return SimpleNamespace(
        scanned=scanned, eligible=eligible, repaired=repaired, failed=failed
    )


def test_tick_success_records_ok(monkeypatch):
    monkeypatch.setattr(
        sched, "run_reconciliation_once",
        lambda: {"scanned": 5, "eligible": 2, "repaired": 2, "failed": 0},
    )
    asyncio.run(sched.run_tick())
    assert sched._state.last_status == "ok"
    assert sched._state.last_counts == {
        "scanned": 5, "eligible": 2, "repaired": 2, "failed": 0
    }
    assert sched._state.runs == 1
    assert sched._state.consecutive_errors == 0
    assert sched._state.last_run_at is not None


def test_tick_partial_when_failures_present(monkeypatch):
    monkeypatch.setattr(
        sched, "run_reconciliation_once",
        lambda: {"scanned": 5, "eligible": 3, "repaired": 1, "failed": 2},
    )
    asyncio.run(sched.run_tick())
    assert sched._state.last_status == "partial"
    assert sched._state.last_counts["failed"] == 2


def test_tick_error_never_raises_and_records_error(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(sched, "run_reconciliation_once", boom)
    asyncio.run(sched.run_tick())
    assert sched._state.last_status == "error"
    assert sched._state.last_counts is None
    assert sched._state.consecutive_errors == 1
    # a subsequent success resets the error streak
    monkeypatch.setattr(
        sched, "run_reconciliation_once",
        lambda: {"scanned": 0, "eligible": 0, "repaired": 0, "failed": 0},
    )
    asyncio.run(sched.run_tick())
    assert sched._state.consecutive_errors == 0
    assert sched._state.runs == 2


def test_run_reconciliation_once_maps_summary(monkeypatch):
    class FakeService:
        def reconcile_completed(self, db, limit):
            assert limit == settings.reconciler_batch_limit
            return _summary(7, 3, 3, 0)

    import app.services.result_materialization as rm

    monkeypatch.setattr(rm, "MissionResultMaterializationService", FakeService)
    counts = sched.run_reconciliation_once()
    assert counts == {"scanned": 7, "eligible": 3, "repaired": 3, "failed": 0}


def test_start_reconciler_gated_off_under_tests():
    # settings.environment == "test" in this suite → scheduler must refuse
    assert sched.start_reconciler() is False


def test_reconciler_health_shape():
    health = sched.reconciler_health()
    assert set(health) == {
        "enabled", "interval_seconds", "last_run_at", "last_status",
        "last_counts", "runs",
    }
    assert health["interval_seconds"] == settings.reconciler_interval_seconds
    assert health["last_run_at"] is None


def test_health_endpoint_exposes_rbac_and_reconciler(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    # Force the non-default posture so a hard-coded ``False`` response cannot
    # satisfy the production guard by accident.
    monkeypatch.setattr(settings, "rbac_enabled", True)

    # No context manager: skip startup events (Qdrant prewarm) — the endpoint
    # needs no startup state.
    resp = TestClient(app).get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["rbac_enabled"] is True
    assert set(body["reconciler"]) >= {"enabled", "last_run_at", "last_status"}
