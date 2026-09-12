"""RECOVER-1: partial search stays useful and tells callers what failed."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from app.services.pedr.cache import get_pedr_cache
from app.services.pedr.search_orchestrator import PEDRConfig, PEDRSearchOrchestrator

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clear_cache():
    get_pedr_cache().invalidate_all()
    yield
    get_pedr_cache().invalidate_all()


def make_search():
    rows = [{"chunk_id": "recovery-chunk", "content": "Usable research", "score": 0.9}]
    return PEDRSearchOrchestrator(
        config=PEDRConfig(enable_graph=False, enable_governance=False),
        lexical_search=lambda **_: deepcopy(rows),
        semantic_search=lambda **_: deepcopy(rows),
        telemetry_enabled=False,
    )


@pytest.mark.parametrize(
    "layer", ["lexical", "semantic", "graph", "syntactic", "pragmatic", "governance"]
)
def test_failed_layer_keeps_results_and_reports_degradation(layer, monkeypatch, caplog):
    search = make_search()
    failure = MagicMock(side_effect=RuntimeError("provider unavailable"))
    if layer in {"lexical", "semantic"}:
        monkeypatch.setattr(search, f"_{layer}_search", failure)
    elif layer == "graph":
        monkeypatch.setattr(search.graph_service, "expand_from_results", failure)
    else:
        service = (
            search.quality_service
            if layer == "governance"
            else getattr(search, f"{layer}_service")
        )
        monkeypatch.setattr(service, "apply", failure)

    response = search.search(
        query="find research",
        enable_graph=layer == "graph",
        enable_governance=layer == "governance",
    )

    assert (
        response.results
    ), "An independent layer outage must preserve healthy retrieval"
    assert response.metadata.degraded is True
    diagnostic = next(
        d for d in response.metadata.layer_diagnostics if d.layer == layer
    )
    assert diagnostic.status == "error"
    assert diagnostic.error_type == "RuntimeError"
    assert diagnostic.duration_ms >= 0
    assert f"layer={layer}" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    metadata = response.to_dict()["metadata"]
    assert metadata["degraded"] is True
    assert len(metadata["layer_diagnostics"]) == 6


@pytest.mark.parametrize("layer", ["syntactic", "pragmatic"])
def test_analysis_failure_uses_neutral_filters_without_retrying_broken_service(
    layer, monkeypatch
):
    search = make_search()
    service = getattr(search, f"{layer}_service")
    analyze = MagicMock(side_effect=RuntimeError("analysis unavailable"))
    boost = MagicMock(side_effect=AssertionError("failed analysis must skip boost"))
    monkeypatch.setattr(service, "create_filters", analyze)
    monkeypatch.setattr(service, "apply", boost)

    response = search.search(query="create new missions")

    assert response.results
    assert response.metadata.degraded
    analyze.assert_called_once()
    boost.assert_not_called()
    if layer == "syntactic":
        assert response.metadata.detected_type is None
    else:
        assert response.metadata.intent == "search"


def test_disabled_layers_do_not_run_analysis_or_boost(monkeypatch):
    search = make_search()
    for service in (search.syntactic_service, search.pragmatic_service):
        monkeypatch.setattr(
            service, "create_filters", MagicMock(side_effect=AssertionError("disabled"))
        )
        monkeypatch.setattr(
            service, "apply", MagicMock(side_effect=AssertionError("disabled"))
        )
    response = search.search(
        query="create missions", enable_syntactic=False, enable_pragmatic=False
    )
    assert response.results
    assert response.metadata.degraded is False
    diagnostics = {d.layer: d.status for d in response.metadata.layer_diagnostics}
    assert diagnostics == {
        "lexical": "ok",
        "semantic": "ok",
        "graph": "disabled",
        "syntactic": "disabled",
        "pragmatic": "disabled",
        "governance": "disabled",
    }


def test_degraded_response_does_not_become_healthy_cache_hit(monkeypatch):
    search = make_search()
    failed = MagicMock(side_effect=RuntimeError("unavailable"))
    monkeypatch.setattr(search, "_lexical_search", failed)
    first = search.search(query="find recovery")
    second = search.search(query="find recovery")
    assert first.metadata.degraded and second.metadata.degraded
    assert (
        failed.call_count == 2
    ), "Transient failures must be retried, not cached as healthy results"


def test_empty_retrieval_reports_success_not_failure():
    search = make_search()
    search._lexical_search = lambda **_: []
    search._semantic_search = lambda **_: []
    response = search.search(query="no matches")
    assert response.results == []
    assert response.metadata.degraded is False
    assert len(response.metadata.layer_diagnostics) == 6


def test_tuned_defaults_reach_the_rest_search_request():
    from app.schemas.pedr_search import PEDRSearchRequest
    from app.services.pedr.search_orchestrator import (
        DEFAULT_GRAPH_WEIGHT,
        DEFAULT_LAYER_WEIGHTS,
    )

    config = PEDRConfig()
    request = PEDRSearchRequest(query="tuning")
    assert config.enable_graph is request.enable_graph is True
    assert config.graph_depth == request.graph_depth == 2
    assert config.graph_weight == request.graph_weight == DEFAULT_GRAPH_WEIGHT == 0.12
    assert config.graph_top_k_seeds == 10
    assert DEFAULT_LAYER_WEIGHTS["graph"] == 0.12
    assert sum(DEFAULT_LAYER_WEIGHTS.values()) == pytest.approx(1)


@pytest.mark.parametrize(
    "restriction",
    [{"allow_pii": False}, {"min_quality_gates": 3}, {"status_filters": ["complete"]}],
)
def test_governance_failure_cannot_bypass_explicit_filters(restriction, monkeypatch):
    search = make_search()
    monkeypatch.setattr(
        search.quality_service,
        "apply",
        MagicMock(side_effect=RuntimeError("governance unavailable")),
    )
    response = search.search(
        query="private research", enable_governance=True, **restriction
    )
    assert (
        response.results == []
    ), "Unevaluated governance restrictions must fail closed"
    assert response.metadata.degraded is True


def test_package_reexports_diagnostics_and_exception_hierarchy():
    import app.services.pedr as pedr
    from app.services.pedr import exceptions

    assert (
        pedr.LayerDiagnostic(layer="lexical", status="ok").to_dict()["status"] == "ok"
    )
    for name in exceptions.__all__:
        assert getattr(pedr, name) is getattr(exceptions, name)


@pytest.mark.parametrize("edge_type", ["co_occurs", "topic_similar"])
def test_related_route_relation_parser_accepts_semantic_edge_types(edge_type):
    from app.services.pedr.relational import RelationType
    from app.services.pedr.semantic_protocol import EDGE_TYPES

    assert RelationType(edge_type).value == edge_type
    assert edge_type in EDGE_TYPES
