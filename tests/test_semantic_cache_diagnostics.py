"""Cache persistence uses the real SDK serializer, never a permissive upsert Mock."""

import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from qdrant_client.http.api.points_api import SyncPointsApi
from qdrant_client.http.api_client import ApiClient
from qdrant_client.models import PointsList
from test_rag_service import _service_answering

from app.core.cache import CacheRegistry
from app.core.config import settings
from app.schemas.rag import RagResponse
from app.services.cache_manager import CacheManager
from app.services.cache_metrics import CacheMetrics
from app.services.rag_service import build_empty_scope_result
from app.services.semantic_cache import SemanticCacheService


class WireCache:
    def __init__(self):
        self.points = []
        self.requests = []
        self.fail = None

        def persist(request):
            self.requests.append(json.loads(request.content))
            self.points = self.requests[-1]["points"]
            return httpx.Response(200, json={"result": {"operation_id": 1, "status": "completed"}, "status": "ok", "time": 0.001})

        self.api = SyncPointsApi(ApiClient(host="https://isolated-cache.invalid", transport=httpx.MockTransport(persist)))

    def get_collections(self):
        if self.fail == "initialize":
            raise ConnectionError("private URL and credential")
        return SimpleNamespace(collections=[SimpleNamespace(name=settings.semantic_cache_collection_name)])

    def get_collection(self, _name):
        return SimpleNamespace(config=None)

    def create_payload_index(self, **_kwargs):
        pass

    def upsert(self, *, collection_name, points, wait):
        if self.fail == "write":
            raise TimeoutError("private query, URL and credential")
        return self.api.upsert_points(collection_name, wait=wait, point_insert_operations=PointsList(points=points))

    def search(self, *, query_filter, **_kwargs):
        if self.fail == "lookup":
            raise ConnectionError("private query, URL and credential")
        matches = [point for point in self.points if all(point["payload"].get(condition.key) == condition.match.value for condition in query_filter.must)]
        return [SimpleNamespace(**point, score=0.99) for point in matches[:1]]

    def scroll(self, **_kwargs):
        if self.fail == "maintenance":
            raise ConnectionError("private query, URL and credential")
        return [], None

    def count(self, **_kwargs):
        return SimpleNamespace(count=len(self.points))

    def delete(self, *, points_selector, **_kwargs):
        self.points = [point for point in self.points if point["id"] not in points_selector]


def test_enabled_cache_serializes_fresh_response_and_replays_without_model(monkeypatch, tmp_path):
    wire = WireCache()
    cache = SemanticCacheService(client=wire, enabled=True)
    cache.metrics = CacheMetrics()
    service, provider, _ = _service_answering(monkeypatch, "Iterative experiments help. [Document: doc-1, Chunk: 0]")
    service.cache_service = cache
    service.cache_manager = CacheManager(registry=CacheRegistry(), telemetry_path=tmp_path / "cache.jsonl")
    first = service.run_query(query="How do programs improve?", project_id="proj-1")
    RagResponse.model_validate(first)
    assert wire.requests and cache.metrics.error_count == 0
    calls = len(provider.chat.completions.requests)
    service.cache_manager.clear()
    replay = service.run_query(query="How do programs improve?", project_id="proj-1")
    assert replay["cache"]["hit"] and replay["citations"] == first["citations"]
    assert replay["quality"] == first["quality"]
    assert len(provider.chat.completions.requests) == calls
    assert cache.check_cache([1.0, 0.0, 0.0], {"project_id": "other-project"}) is None


@pytest.mark.parametrize("operation,category", [("lookup", "unavailable"), ("write", "timeout"), ("maintenance", "unavailable")])
def test_cache_failures_preserve_fresh_cited_answer_and_safe_diagnostics(monkeypatch, tmp_path, caplog, operation, category):
    wire = WireCache()
    cache = SemanticCacheService(client=wire, enabled=True)
    cache.metrics = CacheMetrics()
    wire.fail = operation
    service, provider, _ = _service_answering(monkeypatch, "Iterative experiments help. [Document: doc-1, Chunk: 0]")
    service.cache_service = cache
    service.cache_manager = CacheManager(registry=CacheRegistry(), telemetry_path=tmp_path / "cache.jsonl")
    with caplog.at_level(logging.WARNING):
        result = service.run_query(query="How do programs improve?", project_id="proj-1")
    assert not result["cache"]["hit"] and result["citations"]
    RagResponse.model_validate(result)
    assert provider.chat.completions.requests
    snapshot = cache.metrics.snapshot()
    assert snapshot["error_categories"][operation][category] == 1
    assert snapshot["scope"] == "process_local_since_start"
    assert "private" not in caplog.text
    assert "How do programs" not in caplog.text


def test_unavailable_initialization_does_not_prevent_fresh_pipeline(monkeypatch, tmp_path):
    wire = WireCache()
    wire.fail = "initialize"
    cache = SemanticCacheService(client=wire, enabled=True)
    assert cache.enabled
    assert cache.metrics.snapshot()["error_categories"]["initialize"]["unavailable"] >= 1
    service, provider, _ = _service_answering(monkeypatch, "Iterative experiments help. [Document: doc-1, Chunk: 0]")
    service.cache_service = cache
    service.cache_manager = CacheManager(registry=CacheRegistry(), telemetry_path=tmp_path / "cache.jsonl")
    response = service.run_query(query="Initialization outage", project_id="proj-1")
    assert response["citations"] and provider.chat.completions.requests


def test_malformed_persisted_timestamp_is_a_diagnostic_miss_not_a_request_failure():
    wire = WireCache()
    cache = SemanticCacheService(client=wire, enabled=True)
    cache.metrics = CacheMetrics()
    cache.store_in_cache([1.0, 0.0, 0.0], build_empty_scope_result(search_mode="semantic"), {"project_id": "p"})
    wire.points[0]["payload"]["created_at"] = "invalid timestamp"
    assert cache.check_cache([1.0, 0.0, 0.0], {"project_id": "p"}) is None
    assert cache.metrics.snapshot()["error_categories"]["lookup"]["invalid_payload"] == 1
    assert not wire.points


def test_real_sdk_serialization_failure_is_recorded_without_payload_or_log_flood(caplog):
    wire = WireCache()
    cache = SemanticCacheService(client=wire, enabled=True)
    cache.metrics = CacheMetrics()
    result = build_empty_scope_result(search_mode="semantic")
    result["sources"] = [{"private": object()}]
    with caplog.at_level(logging.WARNING):
        for _ in range(100):
            cache.store_in_cache([1.0, 0.0, 0.0], result, {"query": "private prompt"})
    assert not wire.requests
    assert cache.metrics.snapshot()["error_categories"]["write"]["serialization"] == 100
    assert len(caplog.records) == 1
    assert "private" not in caplog.text


def test_cache_metrics_keep_bounded_labels_and_log_again_after_interval(monkeypatch, caplog):
    clock = [100.0]
    monkeypatch.setattr("app.services.cache_metrics.time.monotonic", lambda: clock[0])
    metrics = CacheMetrics()
    with caplog.at_level(logging.WARNING):
        for index in range(100):
            metrics.record_error(f"private-operation-{index}", f"private-error-{index}")
            metrics.observe_lookup(0.5)
        assert len(caplog.records) == 1
        clock[0] += 61
        metrics.record_error("another-private-operation", "another-private-error")
    assert len(caplog.records) == 2 and "private" not in caplog.text
    assert metrics.snapshot()["error_categories"] == {"unknown": {"unknown": 101}}
    assert metrics.snapshot()["avg_lookup_seconds"] == 0.5
    assert not hasattr(metrics, "lookup_latencies")


def test_deployed_diagnostic_owns_and_removes_only_its_fixture_collection():
    from qdrant_client import QdrantClient

    from scripts.cache_diagnostic import run_diagnostic

    client = QdrantClient(location=":memory:")
    application_cache = SemanticCacheService(client=client, enabled=True)
    before = {item.name for item in client.get_collections().collections}
    receipt = run_diagnostic(client)
    assert receipt["replay_hit"] and receipt["other_scope_missed"]
    assert receipt["model_calls"] == 0
    assert {item.name for item in client.get_collections().collections} == before
    assert application_cache.collection_name in before
