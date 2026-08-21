"""Request-local project scoping regressions for the PEDR search chokepoints."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import pedr_search as pedr_search_api
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.project import Project
from app.services.hybrid_search import HybridSearchService
from app.services.pedr import search_orchestrator as orchestrator_module
from app.services.pedr.cache import PEDRCache
from app.services.pedr.fusion import LayerResult
from app.services.pedr.hybrid_rerank import (
    HybridReranker,
    HybridRerankResult,
    HybridRerankTimings,
)
from app.services.pedr.search_orchestrator import (
    LayerTimings,
    PEDRConfig,
    PEDRMetadata,
    PEDRSearchOrchestrator,
    PEDRSearchResponse,
    PEDRSearchResult,
)


def _internal_response(rows: list[dict[str, Any]]) -> PEDRSearchResponse:
    results = [
        PEDRSearchResult(
            chunk_id=str(row["chunk_id"]),
            content=str(row.get("content", row["chunk_id"])),
            document_id=(
                str(row["document_id"])
                if row.get("document_id") is not None
                else None
            ),
            project_id=(
                str(row["project_id"])
                if row.get("project_id") is not None
                else None
            ),
            rrf_score=float(row.get("score", 0.5)),
            rrf_rank=index,
            urn=row.get("urn"),
            contributing_layers=list(row.get("contributing_layers", [])),
        )
        for index, row in enumerate(rows, start=1)
    ]
    return PEDRSearchResponse(
        results=results,
        metadata=PEDRMetadata(
            query="scope query",
            intent="search",
            intent_confidence=1.0,
            detected_type=None,
            type_confidence=0.0,
            layers_used=["semantic"],
            layer_weights={"semantic": 1.0},
            timings=LayerTimings(total_ms=1.0),
            total_candidates=len(results),
            result_count=len(results),
        ),
    )


class _RecordingOrchestrator:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> PEDRSearchResponse:
        self.calls.append(kwargs)
        return _internal_response(self.rows)


def test_route_scope_is_request_local_and_none_preserves_legacy_shape(
    monkeypatch, auth_headers
):
    """A cached orchestrator receives each request's scope, never singleton state."""
    first_project, second_project = uuid4(), uuid4()
    fake = _RecordingOrchestrator(
        [
            {"chunk_id": "first", "project_id": first_project},
            {"chunk_id": "second", "project_id": second_project},
            {"chunk_id": "missing-project"},
        ]
    )
    scopes = iter([[first_project], [second_project], None])
    monkeypatch.setattr(
        pedr_search_api,
        "accessible_project_ids",
        lambda _user, _db: next(scopes),
    )
    monkeypatch.setattr(pedr_search_api, "_get_pedr_orchestrator", lambda: fake)

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/pedr/search",
            headers=auth_headers,
            json={"query": "first request"},
        )
        second = client.post(
            "/api/v1/pedr/search",
            headers=auth_headers,
            json={"query": "second request"},
        )
        unrestricted = client.post(
            "/api/v1/pedr/search",
            headers=auth_headers,
            json={"query": "rbac off"},
        )

    assert [row["chunk_id"] for row in first.json()["results"]] == ["first"]
    assert [row["chunk_id"] for row in second.json()["results"]] == ["second"]
    assert [row["chunk_id"] for row in unrestricted.json()["results"]] == [
        "first",
        "second",
        "missing-project",
    ]
    assert fake.calls[0]["allowed_project_ids"] == [first_project]
    assert fake.calls[1]["allowed_project_ids"] == [second_project]
    assert "allowed_project_ids" not in fake.calls[2]
    assert "layer_diagnostics" not in first.json()["metadata"]
    assert "degraded" not in first.json()["metadata"]


@pytest.mark.parametrize("rerank_mode", ["full", "hybrid"])
def test_route_disjoint_explicit_project_returns_empty_without_search(
    monkeypatch, auth_headers, rerank_mode
):
    """A nonempty allow-list still intersects an inaccessible project to empty."""
    allowed_project_ids = [uuid4(), uuid4()]
    requested_project_id = uuid4()
    calls = {"full": 0, "hybrid": 0}

    class _ExplodingFull:
        def search(self, **_kwargs):
            calls["full"] += 1
            raise AssertionError("disjoint scope reached the full orchestrator")

    class _ExplodingHybrid:
        def search(self, **_kwargs):
            calls["hybrid"] += 1
            raise AssertionError("disjoint scope reached the hybrid reranker")

    monkeypatch.setattr(
        pedr_search_api,
        "accessible_project_ids",
        lambda _user, _db: allowed_project_ids,
    )
    monkeypatch.setattr(
        pedr_search_api, "_get_pedr_orchestrator", lambda: _ExplodingFull()
    )
    monkeypatch.setattr(
        pedr_search_api, "get_hybrid_reranker", lambda: _ExplodingHybrid()
    )

    response = TestClient(app).post(
        "/api/v1/pedr/search",
        headers=auth_headers,
        json={
            "query": "cross-project",
            "project_id": str(requested_project_id),
            "rerank_mode": rerank_mode,
        },
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert response.json()["metadata"]["result_count"] == 0
    assert calls == {"full": 0, "hybrid": 0}


@pytest.mark.parametrize("rerank_mode", ["full", "hybrid"])
def test_route_empty_scope_returns_empty_without_search(
    monkeypatch, auth_headers, rerank_mode
):
    """A caller with no readable projects reaches neither search pipeline."""
    calls = {"full": 0, "hybrid": 0}

    class _ExplodingFull:
        def search(self, **_kwargs):
            calls["full"] += 1
            raise AssertionError("empty scope reached the full orchestrator")

    class _ExplodingHybrid:
        def search(self, **_kwargs):
            calls["hybrid"] += 1
            raise AssertionError("empty scope reached the hybrid reranker")

    monkeypatch.setattr(
        pedr_search_api,
        "accessible_project_ids",
        lambda _user, _db: [],
    )
    monkeypatch.setattr(
        pedr_search_api, "_get_pedr_orchestrator", lambda: _ExplodingFull()
    )
    monkeypatch.setattr(
        pedr_search_api, "get_hybrid_reranker", lambda: _ExplodingHybrid()
    )

    response = TestClient(app).post(
        "/api/v1/pedr/search",
        headers=auth_headers,
        json={"query": "no grants", "rerank_mode": rerank_mode},
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert calls == {"full": 0, "hybrid": 0}


def test_full_route_post_filter_enforces_project_and_document(
    monkeypatch, auth_headers
):
    """The HTTP boundary drops rows from a scope-ignoring full backend."""
    project_id, other_project_id = uuid4(), uuid4()
    document_id, other_document_id = uuid4(), uuid4()
    fake = _RecordingOrchestrator(
        [
            {
                "chunk_id": "kept",
                "project_id": project_id,
                "document_id": document_id,
            },
            {
                "chunk_id": "wrong-document",
                "project_id": project_id,
                "document_id": other_document_id,
            },
            {
                "chunk_id": "other-allowed-project",
                "project_id": other_project_id,
                "document_id": document_id,
            },
            {"chunk_id": "missing-identifiers"},
        ]
    )
    allowed = [other_project_id, project_id]
    monkeypatch.setattr(
        pedr_search_api,
        "accessible_project_ids",
        lambda _user, _db: allowed,
    )
    monkeypatch.setattr(pedr_search_api, "_get_pedr_orchestrator", lambda: fake)

    response = TestClient(app).post(
        "/api/v1/pedr/search",
        headers=auth_headers,
        json={
            "query": "exact scope",
            "project_id": str(project_id),
            "document_id": str(document_id),
        },
    )

    assert response.status_code == 200
    assert [row["chunk_id"] for row in response.json()["results"]] == ["kept"]
    assert fake.calls[0]["allowed_project_ids"] == allowed


class _RecordingHybridReranker:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> HybridRerankResult:
        self.calls.append(kwargs)
        return HybridRerankResult(
            results=list(self.rows),
            timings=HybridRerankTimings(total_ms=1.0),
            mode_used="hybrid",
            fts_candidates_count=len(self.rows),
            fallback_used=False,
        )


def test_hybrid_route_threads_scope_and_post_filters_backend_rows(
    monkeypatch, auth_headers
):
    """Hybrid mode applies the same project/document defense as full mode."""
    project_id, other_project_id = uuid4(), uuid4()
    document_id = uuid4()
    fake = _RecordingHybridReranker(
        [
            {
                "chunk_id": "kept",
                "content": "kept",
                "project_id": str(project_id),
                "document_id": str(document_id),
                "score": 0.9,
            },
            {
                "chunk_id": "foreign",
                "content": "foreign",
                "project_id": str(other_project_id),
                "document_id": str(document_id),
                "score": 0.8,
            },
            {"chunk_id": "missing", "content": "missing", "score": 0.7},
        ]
    )
    allowed = [project_id, other_project_id]
    monkeypatch.setattr(
        pedr_search_api,
        "accessible_project_ids",
        lambda _user, _db: allowed,
    )
    monkeypatch.setattr(pedr_search_api, "get_hybrid_reranker", lambda: fake)

    response = TestClient(app).post(
        "/api/v1/pedr/search",
        headers=auth_headers,
        json={
            "query": "hybrid scope",
            "rerank_mode": "hybrid",
            "project_id": str(project_id),
            "document_id": str(document_id),
            "enable_governance": False,
        },
    )

    assert response.status_code == 200
    assert [row["chunk_id"] for row in response.json()["results"]] == ["kept"]
    assert fake.calls[0]["allowed_project_ids"] == allowed


def test_include_related_receives_request_scope(monkeypatch, auth_headers):
    """Relational expansion uses the same request-local scope as retrieval."""
    project_id = uuid4()
    fake = _RecordingOrchestrator(
        [
            {
                "chunk_id": uuid4(),
                "project_id": project_id,
                "urn": f"urn:research:chunk:{uuid4()}",
            }
        ]
    )
    related_calls: list[dict[str, Any]] = []

    class _Relational:
        def get_related(self, _urn: str, **kwargs: Any):
            related_calls.append(kwargs)
            return SimpleNamespace(related_entities=[])

    monkeypatch.setattr(
        pedr_search_api,
        "accessible_project_ids",
        lambda _user, _db: [project_id],
    )
    monkeypatch.setattr(pedr_search_api, "_get_pedr_orchestrator", lambda: fake)
    monkeypatch.setattr(
        pedr_search_api, "get_relational_service", lambda: _Relational()
    )

    response = TestClient(app).post(
        "/api/v1/pedr/search",
        headers=auth_headers,
        json={"query": "related", "include_related": True},
    )

    assert response.status_code == 200
    assert related_calls[0]["allowed_project_ids"] == [project_id]


def test_route_batch_resolves_graph_results_without_project_ids(
    monkeypatch, auth_headers, db_session
):
    """Scoped graph rows batch-resolve; None scope preserves them with zero I/O."""
    allowed_project = Project(name="Allowed graph route")
    foreign_project = Project(name="Foreign graph route")
    db_session.add_all([allowed_project, foreign_project])
    db_session.flush()
    allowed_document = Document(project_id=allowed_project.id, name="Allowed")
    foreign_document = Document(project_id=foreign_project.id, name="Foreign")
    db_session.add_all([allowed_document, foreign_document])
    db_session.flush()
    allowed_chunk = DocumentChunk(
        document_id=allowed_document.id,
        chunk_index=0,
        content="allowed",
    )
    foreign_chunk = DocumentChunk(
        document_id=foreign_document.id,
        chunk_index=0,
        content="foreign",
    )
    db_session.add_all([allowed_chunk, foreign_chunk])
    db_session.commit()

    fake = _RecordingOrchestrator(
        [
            {
                "chunk_id": allowed_chunk.id,
                "contributing_layers": ["graph"],
            },
            {
                "chunk_id": foreign_chunk.id,
                "contributing_layers": ["graph"],
            },
            {
                "chunk_id": foreign_chunk.id,
                "document_id": allowed_document.id,
                "project_id": allowed_project.id,
                "contributing_layers": ["graph"],
            },
            {
                "chunk_id": uuid4(),
                "contributing_layers": ["graph"],
            },
        ]
    )

    class _SessionProxy:
        def __init__(self) -> None:
            self.execute_count = 0

        def execute(self, statement):
            if self.execute_count:
                raise AssertionError("None scope must not resolve graph projects")
            self.execute_count += 1
            return db_session.execute(statement)

    proxy = _SessionProxy()
    scopes = iter([[allowed_project.id], None])
    monkeypatch.setattr(
        pedr_search_api,
        "accessible_project_ids",
        lambda _user, _db: next(scopes),
    )
    monkeypatch.setattr(pedr_search_api, "_get_pedr_orchestrator", lambda: fake)
    app.dependency_overrides[get_db] = lambda: proxy
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/pedr/search",
                headers=auth_headers,
                json={"query": "graph route scope"},
            )
            unrestricted = client.post(
                "/api/v1/pedr/search",
                headers=auth_headers,
                json={"query": "graph route unrestricted"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert [row["chunk_id"] for row in response.json()["results"]] == [
        str(allowed_chunk.id)
    ]
    assert [row["chunk_id"] for row in unrestricted.json()["results"]] == [
        str(allowed_chunk.id),
        str(foreign_chunk.id),
        str(foreign_chunk.id),
        str(fake.rows[3]["chunk_id"]),
    ]
    assert unrestricted.json()["results"][0]["project_id"] is None
    assert unrestricted.json()["results"][1]["project_id"] is None
    assert unrestricted.json()["results"][2]["project_id"] == str(
        allowed_project.id
    )
    assert unrestricted.json()["results"][3]["project_id"] is None
    assert proxy.execute_count == 1
    assert "allowed_project_ids" not in fake.calls[1]
    assert "scope_verified" not in response.json()


def test_real_scoped_route_reuses_orchestrator_graph_verification_once(
    monkeypatch, auth_headers
):
    """A verified real response skips the API's duplicate ownership query."""
    project_id, document_id = uuid4(), uuid4()
    seed_chunk_id, graph_chunk_id = uuid4(), uuid4()

    def _lexical(**_kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "chunk_id": str(seed_chunk_id),
                "document_id": str(document_id),
                "project_id": str(project_id),
                "content": "seed",
                "score": 1.0,
            }
        ]

    class _Graph:
        def expand_from_results(self, _results, **_kwargs):
            return LayerResult(
                layer_name="graph",
                results=[{"chunk_id": str(graph_chunk_id), "score": 0.8}],
                metadata={"total_candidates": 1},
            )

    class _Rows:
        def all(self):
            return [
                SimpleNamespace(
                    _mapping={
                        "chunk_id": graph_chunk_id,
                        "document_id": document_id,
                        "project_id": project_id,
                    }
                )
            ]

    class _SessionProxy:
        def __init__(self) -> None:
            self.execute_count = 0

        def execute(self, _statement):
            self.execute_count += 1
            return _Rows()

        def close(self) -> None:
            return None

    session_proxy = _SessionProxy()
    orchestrator = PEDRSearchOrchestrator(
        config=PEDRConfig(
            enable_semantic=False,
            enable_syntactic=False,
            enable_pragmatic=False,
            enable_governance=False,
            enable_graph=True,
        ),
        lexical_search=_lexical,
        graph_service=_Graph(),
        telemetry_enabled=False,
    )
    captured: dict[str, PEDRSearchResponse] = {}
    real_search = orchestrator.search

    def _recording_search(**kwargs: Any) -> PEDRSearchResponse:
        result = real_search(**kwargs)
        captured["result"] = result
        return result

    monkeypatch.setattr(orchestrator, "search", _recording_search)
    monkeypatch.setattr(orchestrator_module, "SessionLocal", lambda: session_proxy)
    monkeypatch.setattr(settings, "pedr_cache_enabled", False)
    monkeypatch.setattr(
        pedr_search_api,
        "accessible_project_ids",
        lambda _user, _db: [project_id],
    )
    monkeypatch.setattr(
        pedr_search_api, "_get_pedr_orchestrator", lambda: orchestrator
    )

    def _unexpected_route_resolution(*_args: Any, **_kwargs: Any):
        raise AssertionError("verified response reached the API ownership resolver")

    monkeypatch.setattr(
        pedr_search_api,
        "_resolve_graph_result_projects",
        _unexpected_route_resolution,
    )

    response = TestClient(app).post(
        "/api/v1/pedr/search",
        headers=auth_headers,
        json={
            "query": "one graph ownership query",
            "enable_graph": True,
            "enable_semantic": False,
            "enable_syntactic": False,
            "enable_pragmatic": False,
            "enable_governance": False,
        },
    )

    assert response.status_code == 200
    assert {row["chunk_id"] for row in response.json()["results"]} == {
        str(seed_chunk_id),
        str(graph_chunk_id),
    }
    assert session_proxy.execute_count == 1
    assert captured["result"].scope_verified is True
    assert "scope_verified" not in captured["result"].to_dict()
    assert "scope_verified" not in response.json()


class _CacheStats:
    def to_dict(self) -> dict[str, Any]:
        return {}


class _CaptureCache:
    def __init__(self, cached: list[dict[str, Any]] | None = None) -> None:
        self.cached = cached
        self.filters: list[dict[str, Any]] = []

    def get(self, _query: str, _top_k: int, filters: dict[str, Any]):
        self.filters.append(dict(filters))
        return self.cached

    def set(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def get_stats(self) -> _CacheStats:
        return _CacheStats()


def test_cache_key_sorts_scope_none_keeps_shared_key_and_hit_is_filtered(
    monkeypatch,
):
    """Authorization partitions cache entries without changing the legacy None key."""
    first_project, second_project = uuid4(), uuid4()
    document_id, other_document_id = uuid4(), uuid4()
    cache = _CaptureCache(
        [
            {
                "chunk_id": "kept",
                "project_id": str(first_project),
                "document_id": str(document_id),
                "rrf_score": 0.9,
                "rrf_rank": 1,
            },
            {
                "chunk_id": "wrong-document",
                "project_id": str(first_project),
                "document_id": str(other_document_id),
                "rrf_score": 0.8,
                "rrf_rank": 2,
            },
            {
                "chunk_id": "foreign",
                "project_id": str(uuid4()),
                "document_id": str(document_id),
                "rrf_score": 0.7,
                "rrf_rank": 3,
            },
        ]
    )
    monkeypatch.setattr(orchestrator_module, "get_pedr_cache", lambda: cache)
    monkeypatch.setattr(settings, "pedr_cache_enabled", True)
    orchestrator = PEDRSearchOrchestrator(
        lexical_search=lambda **_kwargs: [],
        semantic_search=lambda **_kwargs: [],
        telemetry_enabled=False,
    )

    scoped = orchestrator.search(
        query="cache scope",
        project_id=str(first_project),
        document_id=str(document_id),
        allowed_project_ids=[second_project, first_project, second_project],
    )
    cache.cached = None
    legacy = orchestrator.search(query="legacy cache", allowed_project_ids=None)

    assert [result.chunk_id for result in scoped.results] == ["kept"]
    assert scoped.scope_verified is True
    assert legacy.scope_verified is False
    assert "scope_verified" not in scoped.to_dict()
    assert cache.filters[0]["allowed_project_ids"] == tuple(
        sorted((str(first_project), str(second_project)))
    )
    assert "allowed_project_ids" not in cache.filters[1]


def test_cache_partitions_two_scopes_and_sorted_equivalent_scope_hits(monkeypatch):
    """The same query cannot reuse another scope's row, while equal sets do hit."""
    first_project, peer_project, second_project = uuid4(), uuid4(), uuid4()
    provider_calls: list[list[UUID]] = []

    def _lexical(**kwargs: Any) -> list[dict[str, Any]]:
        allowed = list(kwargs["allowed_project_ids"])
        provider_calls.append(allowed)
        return [
            {
                "chunk_id": f"chunk-{allowed[0]}",
                "content": "scoped",
                "project_id": str(allowed[0]),
                "score": 1.0,
            }
        ]

    cache = PEDRCache(max_size=10, ttl_seconds=60)
    monkeypatch.setattr(orchestrator_module, "get_pedr_cache", lambda: cache)
    monkeypatch.setattr(settings, "pedr_cache_enabled", True)
    orchestrator = PEDRSearchOrchestrator(
        config=PEDRConfig(
            enable_semantic=False,
            enable_syntactic=False,
            enable_pragmatic=False,
            enable_governance=False,
            enable_graph=False,
        ),
        lexical_search=_lexical,
        telemetry_enabled=False,
    )

    first = orchestrator.search(
        query="identical query",
        allowed_project_ids=[first_project, peer_project],
    )
    second = orchestrator.search(
        query="identical query",
        allowed_project_ids=[second_project],
    )
    equivalent = orchestrator.search(
        query="identical query",
        allowed_project_ids=[peer_project, first_project, peer_project],
    )

    assert first.results[0].project_id == str(first_project)
    assert second.results[0].project_id == str(second_project)
    assert equivalent.results[0].project_id == str(first_project)
    assert equivalent.metadata.cache_hit is True
    assert provider_calls == [
        [first_project, peer_project],
        [second_project],
    ]


def test_orchestrator_disjoint_project_skips_cache_and_providers(monkeypatch):
    """Direct orchestrator callers get the same no-I/O disjoint intersection."""
    class _ExplodingCache:
        def get(self, *_args, **_kwargs):
            raise AssertionError("disjoint scope reached cache")

    def _explode(**_kwargs):
        raise AssertionError("disjoint scope reached a retrieval provider")

    monkeypatch.setattr(
        orchestrator_module, "get_pedr_cache", lambda: _ExplodingCache()
    )
    orchestrator = PEDRSearchOrchestrator(
        lexical_search=_explode,
        semantic_search=_explode,
        telemetry_enabled=False,
    )

    response = orchestrator.search(
        query="disjoint direct",
        project_id=str(uuid4()),
        allowed_project_ids=[uuid4(), uuid4()],
    )

    assert response.results == []
    assert response.metadata.result_count == 0


def test_orchestrator_empty_scope_skips_cache_retrieval_and_graph(monkeypatch):
    """An empty direct scope short-circuits before every data provider."""
    class _ExplodingCache:
        def get(self, *_args, **_kwargs):
            raise AssertionError("empty scope reached cache")

    class _ExplodingGraph:
        def expand_from_results(self, *_args, **_kwargs):
            raise AssertionError("empty scope reached graph expansion")

    class _ExplodingAnalysis:
        def create_filters(self, **_kwargs):
            raise AssertionError("empty scope reached query analysis")

    def _explode(**_kwargs):
        raise AssertionError("empty scope reached a retrieval provider")

    monkeypatch.setattr(
        orchestrator_module, "get_pedr_cache", lambda: _ExplodingCache()
    )
    orchestrator = PEDRSearchOrchestrator(
        config=PEDRConfig(enable_graph=True),
        lexical_search=_explode,
        semantic_search=_explode,
        graph_service=_ExplodingGraph(),
        syntactic_service=_ExplodingAnalysis(),
        pragmatic_service=_ExplodingAnalysis(),
        telemetry_enabled=False,
    )

    response = orchestrator.search(
        query="empty direct",
        allowed_project_ids=[],
    )

    assert response.results == []
    assert response.metadata.graph_enabled is True
    assert response.metadata.graph_candidates_expanded == 0
    assert response.scope_verified is True


def test_graph_scope_resolves_missing_project_ids_in_one_batch(
    monkeypatch, db_session
):
    """Graph-only chunks are batch-resolved to projects and fail closed."""
    allowed_project = Project(name="Allowed")
    foreign_project = Project(name="Foreign")
    db_session.add_all([allowed_project, foreign_project])
    db_session.flush()
    allowed_document = Document(project_id=allowed_project.id, name="Allowed doc")
    foreign_document = Document(project_id=foreign_project.id, name="Foreign doc")
    db_session.add_all([allowed_document, foreign_document])
    db_session.flush()
    seed_chunk = DocumentChunk(
        document_id=allowed_document.id,
        chunk_index=0,
        content="seed",
    )
    graph_chunk = DocumentChunk(
        document_id=allowed_document.id,
        chunk_index=1,
        content="allowed graph",
    )
    foreign_chunk = DocumentChunk(
        document_id=foreign_document.id,
        chunk_index=0,
        content="foreign graph",
    )
    db_session.add_all([seed_chunk, graph_chunk, foreign_chunk])
    db_session.commit()

    provider_calls: list[dict[str, Any]] = []

    def _lexical(**kwargs: Any) -> list[dict[str, Any]]:
        provider_calls.append(kwargs)
        return [
            {
                "chunk_id": str(seed_chunk.id),
                "document_id": str(allowed_document.id),
                "project_id": str(allowed_project.id),
                "content": "seed",
                "score": 1.0,
            },
            {
                "chunk_id": str(foreign_chunk.id),
                "document_id": str(foreign_document.id),
                "project_id": str(foreign_project.id),
                "content": "foreign seed",
                "score": 0.9,
            },
        ]

    class _Graph:
        def __init__(self) -> None:
            self.seeds: list[dict[str, Any]] = []

        def expand_from_results(self, results, **_kwargs):
            self.seeds = list(results)
            return LayerResult(
                layer_name="graph",
                results=[
                    {"chunk_id": str(graph_chunk.id), "score": 0.8},
                    {
                        "chunk_id": str(foreign_chunk.id),
                        "document_id": str(allowed_document.id),
                        "project_id": str(allowed_project.id),
                        "score": 0.7,
                    },
                    {
                        "chunk_id": str(uuid4()),
                        "document_id": str(allowed_document.id),
                        "project_id": str(allowed_project.id),
                        "score": 0.6,
                    },
                ],
                metadata={"total_candidates": 3},
            )

    class _SessionProxy:
        def __init__(self) -> None:
            self.execute_count = 0

        def execute(self, statement):
            self.execute_count += 1
            return db_session.execute(statement)

        def close(self) -> None:
            return None

    graph = _Graph()
    session_proxy = _SessionProxy()
    monkeypatch.setattr(orchestrator_module, "SessionLocal", lambda: session_proxy)
    monkeypatch.setattr(settings, "pedr_cache_enabled", False)
    orchestrator = PEDRSearchOrchestrator(
        config=PEDRConfig(
            enable_semantic=False,
            enable_syntactic=False,
            enable_pragmatic=False,
            enable_governance=False,
            enable_graph=True,
        ),
        lexical_search=_lexical,
        graph_service=graph,
        telemetry_enabled=False,
    )

    response = orchestrator.search(
        query="graph scope",
        top_k=10,
        project_id=str(allowed_project.id),
        document_id=str(allowed_document.id),
        allowed_project_ids=[allowed_project.id],
    )

    result_ids = {result.chunk_id for result in response.results}
    assert str(seed_chunk.id) in result_ids
    assert str(graph_chunk.id) in result_ids
    assert str(foreign_chunk.id) not in result_ids
    assert provider_calls[0]["allowed_project_ids"] == [allowed_project.id]
    assert [row["chunk_id"] for row in graph.seeds] == [str(seed_chunk.id)]
    assert session_proxy.execute_count == 1
    assert response.metadata.graph_candidates_expanded == 1
    assert response.scope_verified is True


def test_graph_none_scope_with_explicit_filters_preserves_legacy_results(
    monkeypatch,
):
    """None scope adds no graph resolver or post-filter to the legacy path."""
    project_id, document_id = uuid4(), uuid4()
    graph_chunk_id = uuid4()
    provider_calls: list[dict[str, Any]] = []

    def _lexical(**kwargs: Any) -> list[dict[str, Any]]:
        provider_calls.append(kwargs)
        return [
            {
                "chunk_id": str(uuid4()),
                "document_id": str(document_id),
                "project_id": str(project_id),
                "content": "seed",
                "score": 1.0,
            }
        ]

    class _Graph:
        def expand_from_results(self, _results, **_kwargs):
            return LayerResult(
                layer_name="graph",
                results=[
                    {
                        "chunk_id": str(graph_chunk_id),
                        "content": "legacy cross-expansion",
                        "score": 0.8,
                    }
                ],
                metadata={"total_candidates": 1},
            )

    monkeypatch.setattr(
        orchestrator_module,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(
            AssertionError("None scope reached the graph ownership resolver")
        ),
    )
    monkeypatch.setattr(settings, "pedr_cache_enabled", False)
    orchestrator = PEDRSearchOrchestrator(
        config=PEDRConfig(
            enable_semantic=False,
            enable_syntactic=False,
            enable_pragmatic=False,
            enable_governance=False,
            enable_graph=True,
        ),
        lexical_search=_lexical,
        graph_service=_Graph(),
        telemetry_enabled=False,
    )

    response = orchestrator.search(
        query="legacy explicit graph",
        top_k=10,
        project_id=str(project_id),
        document_id=str(document_id),
        allowed_project_ids=None,
    )

    assert graph_chunk_id in {UUID(result.chunk_id) for result in response.results}
    assert response.metadata.graph_candidates_expanded == 1
    assert response.scope_verified is False
    assert provider_calls[0]["project_id"] == str(project_id)
    assert provider_calls[0]["document_id"] == str(document_id)
    assert "allowed_project_ids" not in provider_calls[0]


class _PassThroughQuality:
    def apply(self, results, *, filters=None):
        return list(results)


class _PassThroughSyntactic:
    def create_filters(self, **_kwargs):
        return SimpleNamespace()

    def apply(self, results, **_kwargs):
        return list(results)


class _PassThroughFacets:
    def filter_chunks(self, results, _filters):
        return list(results)


class _RecordingRetrieval:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        return list(self.rows)


def test_hybrid_service_threads_scope_and_filters_semantic_provider():
    """HybridSearchService does not trust a scope-ignoring semantic provider."""
    project_id, foreign_project_id = uuid4(), uuid4()
    document_id = uuid4()
    retrieval = _RecordingRetrieval(
        [
            {
                "chunk_id": "kept",
                "project_id": str(project_id),
                "document_id": str(document_id),
                "score": 0.9,
            },
            {
                "chunk_id": "foreign",
                "project_id": str(foreign_project_id),
                "document_id": str(document_id),
                "score": 0.8,
            },
            {"chunk_id": "missing", "score": 0.7},
        ]
    )
    service = HybridSearchService(
        retrieval_service=retrieval,
        faceted_service=_PassThroughFacets(),
        quality_service=_PassThroughQuality(),
        syntactic_service=_PassThroughSyntactic(),
    )

    results = service.search(
        query="semantic scope",
        search_mode="semantic",
        project_id=str(project_id),
        document_id=str(document_id),
        allowed_project_ids=[project_id, foreign_project_id],
    )

    assert [row["chunk_id"] for row in results] == ["kept"]
    assert retrieval.calls[0]["allowed_project_ids"] == [
        project_id,
        foreign_project_id,
    ]


class _Embedding:
    def generate_embedding(self, _query: str) -> list[float]:
        return [1.0, 0.0]


class _RecordingQdrant:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def search_chunks(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        return list(self.rows)


def test_hybrid_reranker_threads_full_scope_and_preserves_none_call_shape():
    """Full rerank scopes Qdrant while None retains the legacy call payload."""
    project_id, foreign_project_id = uuid4(), uuid4()
    document_id = uuid4()
    qdrant = _RecordingQdrant(
        [
            {
                "chunk_id": "kept",
                "project_id": str(project_id),
                "document_id": str(document_id),
                "score": 0.9,
            },
            {
                "chunk_id": "foreign",
                "project_id": str(foreign_project_id),
                "document_id": str(document_id),
                "score": 0.8,
            },
        ]
    )
    reranker = HybridReranker(
        embedding_service=_Embedding(),
        qdrant_service=qdrant,
    )

    scoped = reranker.search(
        query="full scope",
        mode="full",
        project_id=str(project_id),
        document_id=str(document_id),
        allowed_project_ids=[project_id, foreign_project_id],
    )
    unrestricted = reranker.search(
        query="legacy full",
        mode="full",
        allowed_project_ids=None,
    )

    assert [row["chunk_id"] for row in scoped.results] == ["kept"]
    assert qdrant.calls[0]["allowed_project_ids"] == [
        project_id,
        foreign_project_id,
    ]
    assert [row["chunk_id"] for row in unrestricted.results] == ["kept", "foreign"]
    assert "allowed_project_ids" not in qdrant.calls[1]


def test_hybrid_reranker_threads_scope_to_fts_candidates(monkeypatch):
    """Hybrid mode carries the allow-list into its lexical first stage."""
    project_id = uuid4()
    reranker = HybridReranker(
        embedding_service=_Embedding(),
        qdrant_service=_RecordingQdrant([]),
    )
    captured: dict[str, Any] = {}

    def _fts(**kwargs: Any) -> list[dict[str, Any]]:
        captured.update(kwargs)
        return [
            {
                "chunk_id": "candidate",
                "project_id": str(project_id),
                "fts_score": 1.0,
            }
        ]

    monkeypatch.setattr(reranker, "_fts_candidates", _fts)
    monkeypatch.setattr(
        reranker,
        "_semantic_rerank",
        lambda **kwargs: list(kwargs["candidates"]),
    )

    result = reranker.search(
        query="hybrid lexical scope",
        mode="hybrid",
        allowed_project_ids=[project_id],
    )

    assert result.results[0]["chunk_id"] == "candidate"
    assert captured["allowed_project_ids"] == [project_id]


def test_empty_scope_short_circuits_hybrid_service_and_reranker():
    """An empty allow-list reaches neither relational nor vector retrieval."""
    retrieval = _RecordingRetrieval([])
    service = HybridSearchService(
        retrieval_service=retrieval,
        faceted_service=_PassThroughFacets(),
        quality_service=_PassThroughQuality(),
        syntactic_service=_PassThroughSyntactic(),
    )
    qdrant = _RecordingQdrant([])
    reranker = HybridReranker(
        embedding_service=_Embedding(),
        qdrant_service=qdrant,
    )

    assert service.search(query="denied", allowed_project_ids=[]) == []
    assert (
        service.search(
            query="disjoint",
            project_id=str(uuid4()),
            allowed_project_ids=[uuid4()],
        )
        == []
    )
    assert reranker.search(query="denied", allowed_project_ids=[]).results == []
    assert retrieval.calls == []
    assert qdrant.calls == []
