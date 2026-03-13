"""Tests for the monitoring API endpoint functions."""

from app.api.v1 import monitoring as monitoring_router


class _DummyMonitor:
    def __init__(self):
        self.calls = []

    def summary(self, *, days: int = 30, months: int = 3):
        self.calls.append({"days": days, "months": months})
        return {
            "currency": "USD",
            "retention_days": 30,
            "totals": {"queries": 0, "cost_usd": 0.0},
            "daily": [],
            "monthly": [],
            "recent": [],
        }


class _DummyRag:
    def __init__(self):
        self.routing_metrics = {"total_queries": 5, "escalations": 1}


def test_monitoring_costs_endpoint(monkeypatch):
    monitor = _DummyMonitor()
    monkeypatch.setattr(monitoring_router, "get_cost_monitor", lambda: monitor)
    payload = monitoring_router.read_costs()
    assert payload["totals"]["queries"] == 0
    assert monitor.calls[0]["days"] == 30


def test_monitoring_performance_endpoint(monkeypatch):
    monitor = _DummyMonitor()
    monkeypatch.setattr(monitoring_router, "get_cost_monitor", lambda: monitor)
    monkeypatch.setattr(
        monitoring_router,
        "_routing_snapshot",
        lambda: {"total_queries": 3, "escalations": 0},
    )
    payload = monitoring_router.read_performance()
    assert payload["routing"]["total_queries"] == 3
    assert monitor.calls[-1]["days"] == 7


def test_routing_snapshot_handles_exceptions(monkeypatch):
    def _raise():  # pragma: no cover - helper for clarity
        raise RuntimeError("qdrant missing")

    monkeypatch.setattr(monitoring_router, "current_rag_service", _raise)
    snapshot = monitoring_router._routing_snapshot()
    assert snapshot["total_queries"] == 0
    assert "qdrant" in snapshot["unavailable"].lower()


def test_routing_snapshot_handles_uninitialized(monkeypatch):
    monkeypatch.setattr(monitoring_router, "current_rag_service", lambda: None)
    snapshot = monitoring_router._routing_snapshot()
    assert snapshot["unavailable"] == "rag_service not initialized"
