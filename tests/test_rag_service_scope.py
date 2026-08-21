"""Request-local project scoping regressions for the legacy RAG endpoint."""

from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.api.v1 import search as search_router
from app.core.authorization import accessible_project_ids as resolve_project_scope
from app.core.config import settings
from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_SERVICE,
    AuthenticatedUser,
)
from app.schemas.rag import RagQuery, RagResponse
from app.services import rag_service as rag_module
from app.services.cache_manager import CacheManager
from app.services.faceted_search import FacetFilters
from app.services.pedr.search_orchestrator import (
    LayerTimings,
    PEDRMetadata,
    PEDRSearchResponse,
    PEDRSearchResult,
)

PROJECT_A = UUID("00000000-0000-0000-0000-000000000001")
PROJECT_B = UUID("00000000-0000-0000-0000-000000000002")
PROJECT_C = UUID("00000000-0000-0000-0000-000000000003")


class _RecordingApplicationCache:
    def __init__(self) -> None:
        self.key_kwargs: list[dict[str, Any]] = []
        self.keys: list[tuple[Any, ...]] = []

    def rag_query_key(self, **kwargs: Any) -> tuple[Any, ...]:
        self.key_kwargs.append(copy.deepcopy(kwargs))
        key = CacheManager.rag_query_key(**kwargs)
        self.keys.append(key)
        return key

    def cached_value(self, _name: str, _key: tuple[Any, ...], loader):
        return loader(), False

    def ttl_seconds(self, _name: str) -> float:
        return 300.0


class _RecordingSemanticCache:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.stores: list[dict[str, Any]] = []

    def check_cache(self, *, metadata: dict[str, Any], **_kwargs: Any):
        self.checks.append(copy.deepcopy(metadata))
        return None

    def store_in_cache(self, *, metadata: dict[str, Any], **_kwargs: Any) -> None:
        self.stores.append(copy.deepcopy(metadata))


class _Embedding:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def generate_embedding(self, query: str) -> list[float]:
        self.queries.append(query)
        return [1.0, 0.0, 0.0]


class _PEDR:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> PEDRSearchResponse:
        self.calls.append(copy.deepcopy(kwargs))
        scope = kwargs.get("allowed_project_ids")
        project_id = str(scope[0]) if scope else str(PROJECT_A)
        result = PEDRSearchResult(
            chunk_id="chunk-1",
            content=(
                "TraceLab keeps authorization scope local to each request and "
                "binds cached evidence to that exact scope."
            ),
            document_id="doc-1",
            project_id=project_id,
            chunk_index=0,
            source_type="report",
            rrf_score=0.95,
            embedding=[1.0, 0.0, 0.0],
        )
        return PEDRSearchResponse(
            results=[result],
            metadata=PEDRMetadata(
                query=str(kwargs["query"]),
                intent="factual",
                intent_confidence=1.0,
                detected_type=None,
                type_confidence=0.0,
                layers_used=["semantic"],
                layer_weights={"semantic": 1.0},
                timings=LayerTimings(total_ms=1.0),
                total_candidates=1,
                result_count=1,
            ),
        )


class _ChatCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any):
        self.calls.append(kwargs)
        message = SimpleNamespace(
            content=(
                "Authorization scope remains request-local and cache-safe. "
                "[Document: doc-1, Chunk: 0]"
            )
        )
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class _Client:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_ChatCompletions())


def _service(monkeypatch):
    application_cache = _RecordingApplicationCache()
    semantic_cache = _RecordingSemanticCache()
    pedr = _PEDR()
    embedding = _Embedding()
    monkeypatch.setattr(rag_module, "_openai_import_error", None, raising=False)
    service = rag_module.RagService(
        pedr_orchestrator=pedr,
        embedding_service=embedding,
        cache_service=semantic_cache,
        client=_Client(),
        model="gpt-test",
        escalation_model=None,
        default_temperature=0.0,
        cost_monitor=None,
        graph_rag_helper=object(),
    )
    service.cache_manager = application_cache
    return service, application_cache, semantic_cache, pedr, embedding


def test_scoped_rag_caches_are_partitioned_and_scope_order_is_canonical(monkeypatch):
    """Equivalent grants share keys; different grants cannot share either cache."""
    service, application_cache, semantic_cache, pedr, _embedding = _service(
        monkeypatch
    )

    service.run_query(
        query="cache scope",
        allowed_project_ids=[PROJECT_B, PROJECT_A, PROJECT_B],
    )
    service.run_query(
        query="cache scope",
        allowed_project_ids=[PROJECT_A, PROJECT_B],
    )
    service.run_query(query="cache scope", allowed_project_ids=[PROJECT_C])

    canonical_ab = (
        "*|*|*|*|*|*|allowed_projects:"
        f"{PROJECT_A},{PROJECT_B}"
    )
    canonical_c = f"*|*|*|*|*|*|allowed_projects:{PROJECT_C}"
    application_signatures = [
        call["filters_signature"] for call in application_cache.key_kwargs
    ]
    semantic_check_signatures = [
        call["filters_signature"] for call in semantic_cache.checks
    ]
    semantic_store_signatures = [
        call["filters_signature"] for call in semantic_cache.stores
    ]

    assert application_cache.keys[0] == application_cache.keys[1]
    assert application_cache.keys[0] != application_cache.keys[2]
    assert application_signatures == [canonical_ab, canonical_ab, canonical_c]
    assert semantic_check_signatures == application_signatures
    assert semantic_store_signatures == application_signatures
    assert pedr.calls[0]["allowed_project_ids"] == [PROJECT_A, PROJECT_B]
    assert pedr.calls[1]["allowed_project_ids"] == [PROJECT_A, PROJECT_B]
    assert pedr.calls[2]["allowed_project_ids"] == [PROJECT_C]


def test_none_scope_preserves_legacy_application_key_and_semantic_signature(
    monkeypatch,
):
    """The unrestricted path retains its old cache identities and provider kwargs."""
    service, application_cache, semantic_cache, pedr, _embedding = _service(
        monkeypatch
    )
    base_signature = FacetFilters.from_kwargs().signature()
    expected_key_kwargs = {
        "query": "legacy cache",
        "project_id": None,
        "document_id": None,
        "source_type": None,
        "top_k": 5,
        "temperature": None,
        "max_tokens": None,
        "search_mode": "semantic",
        "filters_signature": base_signature,
        "quality_signature": "*|*|any|strict",
        "graph_context_enabled": False,
    }

    service.run_query(query="legacy cache")

    assert application_cache.key_kwargs == [expected_key_kwargs]
    assert application_cache.keys == [CacheManager.rag_query_key(**expected_key_kwargs)]
    assert semantic_cache.checks[0]["filters_signature"] == base_signature
    assert semantic_cache.stores[0]["filters_signature"] == base_signature
    assert "allowed_project_ids" not in pedr.calls[0]


class _ExplodingCache:
    def __getattr__(self, name: str):
        raise AssertionError(f"empty scope must not touch application cache: {name}")


class _ExplodingProvider:
    def __getattr__(self, name: str):
        raise AssertionError(f"empty scope must not touch provider: {name}")


def test_empty_scope_fails_closed_before_cache_embedding_or_provider(monkeypatch):
    """A principal with no projects receives a normal empty result without I/O."""
    service, _application_cache, _semantic_cache, _pedr, _embedding = _service(
        monkeypatch
    )
    service.cache_manager = _ExplodingCache()
    service.cache_service = _ExplodingCache()
    service.embedding_service = _ExplodingProvider()
    service.pedr_orchestrator = _ExplodingProvider()

    result = service.run_query(query="nothing readable", allowed_project_ids=[])

    response = RagResponse.model_validate(result)
    assert response.sources == []
    assert response.citations == []
    assert response.cache.hit is False
    assert response.routing.attempts == []


def _route_result(search_mode: str) -> dict[str, Any]:
    return {
        "answer": "Scoped route result.",
        "citations": [],
        "sources": [],
        "latency_ms": 0.0,
        "compression": {
            "original_chunks": 0,
            "filtered_chunks": 0,
            "original_tokens": 0,
            "filtered_tokens": 0,
            "reduction_ratio": 0.0,
            "threshold": 0.7,
            "compression_ms": 0.0,
        },
        "cache": {"hit": False},
        "quality": {
            "composite_score": 1.0,
            "threshold": 0.85,
            "pillar_scores": {
                "linguistic_uncertainty": 1.0,
                "answer_integrity": 1.0,
                "source_provenance": 1.0,
            },
            "hard_failures": [],
            "reasons": [],
        },
        "routing": {
            "selected_model": "none",
            "escalated": False,
            "attempts": [],
            "estimated_cost_usd": 0.0,
            "metrics": {"total_queries": 0, "escalations": 0},
        },
        "search_mode": search_mode,
    }


class _RouteService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run_query(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return _route_result(str(kwargs["search_mode"]))


class _History:
    def record_search(self, **_kwargs: Any) -> None:
        return None


class _ExplodingDB:
    def query(self, *_args: Any, **_kwargs: Any):
        raise AssertionError("unrestricted scope must not query the database")


@pytest.mark.parametrize(
    ("rbac_enabled", "role"),
    [
        (True, ROLE_OWNER),
        (True, ROLE_ADMIN),
        (False, ROLE_SERVICE),
    ],
)
def test_route_privileged_and_flag_off_paths_preserve_legacy_call_shape(
    monkeypatch,
    rbac_enabled,
    role,
):
    """Unrestricted route requests resolve once and omit the scope keyword."""
    user = AuthenticatedUser(
        user_id=PROJECT_A,
        email="principal@example.com",
        display_name="principal",
        role=role,
    )
    service = _RouteService()
    scope_calls: list[tuple[AuthenticatedUser, object]] = []

    def _scope(current_user, db):
        scope_calls.append((current_user, db))
        return resolve_project_scope(current_user, db)

    monkeypatch.setattr(settings, "rbac_enabled", rbac_enabled)
    monkeypatch.setattr(search_router, "accessible_project_ids", _scope)
    monkeypatch.setattr(search_router, "get_rag_service", lambda: service)

    response = asyncio.run(
        search_router.run_rag_search(
            RagQuery(query="legacy route"),
            user,
            _ExplodingDB(),
            _History(),
        )
    )

    assert response.answer == "Scoped route result."
    assert len(scope_calls) == 1
    assert "allowed_project_ids" not in service.calls[0]


def test_route_resolves_scoped_project_ids_once_and_forwards_them(monkeypatch):
    """Ordinary principals pass one request-local scope into the RAG service."""
    user = AuthenticatedUser(
        user_id=PROJECT_A,
        email="member@example.com",
        display_name="member",
        role=ROLE_MEMBER,
    )
    service = _RouteService()
    scope_calls: list[tuple[AuthenticatedUser, object]] = []

    def _scope(current_user, db):
        scope_calls.append((current_user, db))
        return [PROJECT_B]

    monkeypatch.setattr(search_router, "accessible_project_ids", _scope)
    monkeypatch.setattr(search_router, "get_rag_service", lambda: service)

    asyncio.run(
        search_router.run_rag_search(
            RagQuery(query="scoped route"),
            user,
            object(),
            _History(),
        )
    )

    assert len(scope_calls) == 1
    assert service.calls[0]["allowed_project_ids"] == [PROJECT_B]


def test_route_empty_scope_returns_before_rag_singleton_construction(monkeypatch):
    """No-grant requests cannot initialize provider-backed RAG dependencies."""
    user = AuthenticatedUser(
        user_id=PROJECT_A,
        email="member@example.com",
        display_name="member",
        role=ROLE_MEMBER,
    )
    scope_calls: list[tuple[AuthenticatedUser, object]] = []

    def _scope(current_user, db):
        scope_calls.append((current_user, db))
        return []

    def _explode():
        raise AssertionError("empty scope must not construct the RAG singleton")

    monkeypatch.setattr(search_router, "accessible_project_ids", _scope)
    monkeypatch.setattr(search_router, "get_rag_service", _explode)

    response = asyncio.run(
        search_router.run_rag_search(
            RagQuery(query="no grants"),
            user,
            object(),
            _History(),
        )
    )

    assert len(scope_calls) == 1
    assert response.sources == []
    assert response.cache.hit is False
