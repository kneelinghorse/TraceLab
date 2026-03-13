"""Tests for the graph quality validation script."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from scripts.pedr_graph_quality_validation import (
    ConfigSummary,
    QueryMetrics,
    _safe_avg,
    analyze_telemetry,
    assess_graph_edges,
    build_config_comparison,
    generate_recommendations,
    load_telemetry_events,
    parse_telemetry_event,
    summarize_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_EVENT_NO_GRAPH = {
    "ts": "2025-12-27T19:59:25.632960+00:00",
    "event": "pedr_graph_telemetry",
    "query": "test query no graph impact",
    "graph": {
        "depth": 2,
        "decay": 0.7,
        "edge_types": [],
        "top_k_seeds": 10,
        "weight": 0.12,
        "seed_count": 10,
        "seed_score_stats": {"count": 10, "score_stats": {"min": 0.4, "max": 0.5, "avg": 0.45, "p50": 0.45, "p90": 0.5}},
        "depth_stats": {},
        "edge_type_usage": {},
        "total_candidates": 0,
        "graph_candidates_expanded": 0,
        "cache": {"hits": 0, "misses": 10, "hit_rate": 0.0},
    },
    "rrf": {
        "k": 60,
        "layers_used": ["semantic", "graph"],
        "total_unique": 60,
        "fusion_latency_ms": 0.99,
        "layer_weights": {"lexical": 0.22, "semantic": 0.308, "graph": 0.12},
        "telemetry": {
            "rrf_score_stats": {"min": 0.002, "max": 0.005, "avg": 0.003, "p50": 0.003, "p90": 0.004},
            "layer_contribution_counts": {"semantic": 60, "graph": 0},
            "layer_contribution_rates": {"semantic": 1.0, "graph": 0.0},
            "multi_layer_result_count": 0,
            "multi_layer_result_rate": 0.0,
        },
    },
    "ranking": {
        "final_result_count": 10,
        "graph_impact": {
            "results_with_graph": 0,
            "result_share": 0.0,
            "rank_stats": {},
            "rrf_contribution_stats": {},
            "rrf_contribution_share_stats": {},
            "top_5_with_graph": 0,
            "top_5_share": 0.0,
        },
    },
    "timings": {"graph_ms": 110.0, "fusion_ms": 1.0, "total_ms": 1000.0},
}

SAMPLE_EVENT_WITH_GRAPH = {
    "ts": "2025-12-27T20:06:30.384655+00:00",
    "event": "pedr_graph_telemetry",
    "query": "test query with graph impact",
    "graph": {
        "depth": 2,
        "decay": 0.7,
        "edge_types": [],
        "top_k_seeds": 10,
        "weight": 0.12,
        "seed_count": 5,
        "seed_score_stats": {},
        "depth_stats": {},
        "edge_type_usage": {},
        "total_candidates": 2,
        "graph_candidates_expanded": 2,
        "cache": {"hits": 0, "misses": 5, "hit_rate": 0.0},
    },
    "rrf": {
        "k": 60,
        "layers_used": ["lexical", "semantic", "graph"],
        "total_unique": 4,
        "fusion_latency_ms": 0.02,
        "layer_weights": {"lexical": 0.23, "semantic": 0.322, "graph": 0.08},
        "telemetry": {
            "rrf_score_stats": {"min": 0.001, "max": 0.009, "avg": 0.005, "p50": 0.004, "p90": 0.005},
            "layer_contribution_counts": {"lexical": 2, "semantic": 2, "graph": 1},
            "layer_contribution_rates": {"lexical": 0.5, "semantic": 0.5, "graph": 0.25},
            "multi_layer_result_count": 1,
            "multi_layer_result_rate": 0.25,
        },
    },
    "ranking": {
        "final_result_count": 4,
        "graph_impact": {
            "results_with_graph": 1,
            "result_share": 0.25,
            "rank_stats": {"min": 4.0, "max": 4.0, "avg": 4.0, "p50": 4.0, "p90": 4.0},
            "rrf_contribution_stats": {"min": 0.001, "max": 0.001, "avg": 0.001, "p50": 0.001, "p90": 0.001},
            "rrf_contribution_share_stats": {"min": 1.0, "max": 1.0, "avg": 1.0, "p50": 1.0, "p90": 1.0},
            "top_5_with_graph": 1,
            "top_5_share": 0.25,
        },
    },
    "timings": {"graph_ms": 12.5, "fusion_ms": 0.03, "total_ms": 0.5},
}


# ---------------------------------------------------------------------------
# Tests: parse_telemetry_event
# ---------------------------------------------------------------------------


def test_parse_event_no_graph_impact():
    result = parse_telemetry_event(SAMPLE_EVENT_NO_GRAPH)
    assert result is not None
    assert result.query == "test query no graph impact"
    assert result.graph_candidates_expanded == 0
    assert result.results_with_graph == 0
    assert result.result_share == 0.0
    assert result.graph_ms == 110.0
    assert result.graph_contribution_rate == 0.0


def test_parse_event_with_graph_impact():
    result = parse_telemetry_event(SAMPLE_EVENT_WITH_GRAPH)
    assert result is not None
    assert result.query == "test query with graph impact"
    assert result.graph_candidates_expanded == 2
    assert result.results_with_graph == 1
    assert result.result_share == 0.25
    assert result.graph_ms == 12.5
    assert result.graph_contribution_rate == 0.25


def test_parse_non_graph_event_returns_none():
    event = {"event": "other_event", "query": "test"}
    assert parse_telemetry_event(event) is None


def test_parse_event_config_inference():
    result = parse_telemetry_event(SAMPLE_EVENT_WITH_GRAPH)
    assert result is not None
    assert result.config_name == "default"

    # SAMPLE_EVENT_NO_GRAPH uses d2/w0.12/k10 which now matches "default"
    # (sprint25_original and default were reconciled in T36.4)
    result_s25 = parse_telemetry_event(SAMPLE_EVENT_NO_GRAPH)
    assert result_s25 is not None
    assert result_s25.config_name == "default"


# ---------------------------------------------------------------------------
# Tests: load_telemetry_events
# ---------------------------------------------------------------------------


def test_load_from_jsonl_file():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False
    ) as f:
        f.write(json.dumps(SAMPLE_EVENT_NO_GRAPH) + "\n")
        f.write(json.dumps(SAMPLE_EVENT_WITH_GRAPH) + "\n")
        f.write("\n")  # blank line
        f.write("not valid json\n")  # invalid line
        f.flush()
        path = Path(f.name)

    metrics = load_telemetry_events([path])
    assert len(metrics) == 2
    path.unlink()


def test_load_nonexistent_file():
    metrics = load_telemetry_events([Path("/nonexistent/file.jsonl")])
    assert metrics == []


# ---------------------------------------------------------------------------
# Tests: summarize_config
# ---------------------------------------------------------------------------


def test_summarize_config_empty():
    summary = summarize_config("empty", [])
    assert summary.query_count == 0
    assert summary.graph_impact_rate == 0.0


def test_summarize_config_mixed():
    m1 = parse_telemetry_event(SAMPLE_EVENT_NO_GRAPH)
    m2 = parse_telemetry_event(SAMPLE_EVENT_WITH_GRAPH)
    assert m1 is not None and m2 is not None

    summary = summarize_config("mixed", [m1, m2])
    assert summary.query_count == 2
    assert summary.queries_with_any_graph_impact == 1
    assert summary.graph_impact_rate == 0.5


# ---------------------------------------------------------------------------
# Tests: assess_graph_edges
# ---------------------------------------------------------------------------


def test_assess_empty_graph():
    m = parse_telemetry_event(SAMPLE_EVENT_NO_GRAPH)
    assert m is not None
    assessment = assess_graph_edges([m])
    assert assessment["edge_density_verdict"] == "EMPTY"
    assert assessment["total_candidates_found"] == 0


def test_assess_healthy_graph():
    m = parse_telemetry_event(SAMPLE_EVENT_WITH_GRAPH)
    assert m is not None
    # All queries have graph results → HEALTHY
    assessment = assess_graph_edges([m])
    assert assessment["edge_density_verdict"] == "HEALTHY"
    assert assessment["total_candidates_found"] == 2


def test_assess_sparse_graph():
    m_empty = parse_telemetry_event(SAMPLE_EVENT_NO_GRAPH)
    m_hit = parse_telemetry_event(SAMPLE_EVENT_WITH_GRAPH)
    assert m_empty is not None and m_hit is not None
    # 1 out of 20 queries with results → <10% → SPARSE
    metrics = [m_empty] * 19 + [m_hit]
    assessment = assess_graph_edges(metrics)
    assert assessment["edge_density_verdict"] == "SPARSE"


# ---------------------------------------------------------------------------
# Tests: generate_recommendations
# ---------------------------------------------------------------------------


def test_recommendations_empty_graph():
    edge = {"edge_density_verdict": "EMPTY", "latency_cost_ms_avg": 110.0}
    recs = generate_recommendations(edge, [])
    assert any("CRITICAL" in r for r in recs)
    assert any("110ms" in r for r in recs)


def test_recommendations_healthy_graph():
    edge = {"edge_density_verdict": "HEALTHY", "queries_with_graph_results_pct": 80.0}
    summary = ConfigSummary(
        config_name="default",
        query_count=10,
        graph_depth=1,
        graph_decay=0.7,
        graph_weight=0.08,
        graph_top_k_seeds=5,
        avg_graph_candidates=2.0,
        avg_results_with_graph=1.5,
        avg_result_share=0.15,
        avg_top_5_with_graph=1.0,
        avg_top_5_share=0.2,
        avg_graph_ms=10.0,
        avg_total_ms=100.0,
        avg_graph_contribution_rate=0.15,
        queries_with_any_graph_impact=8,
        graph_impact_rate=0.8,
    )
    recs = generate_recommendations(edge, [summary])
    assert any("Best performing" in r for r in recs)


# ---------------------------------------------------------------------------
# Tests: build_config_comparison
# ---------------------------------------------------------------------------


def test_config_comparison_format():
    summary = ConfigSummary(
        config_name="test",
        query_count=5,
        graph_depth=1,
        graph_decay=0.7,
        graph_weight=0.08,
        graph_top_k_seeds=5,
        avg_graph_candidates=1.0,
        avg_results_with_graph=0.5,
        avg_result_share=0.1,
        avg_top_5_with_graph=0.3,
        avg_top_5_share=0.06,
        avg_graph_ms=5.0,
        avg_total_ms=50.0,
        avg_graph_contribution_rate=0.1,
        queries_with_any_graph_impact=3,
        graph_impact_rate=0.6,
    )
    rows = build_config_comparison([summary])
    assert len(rows) == 1
    assert rows[0]["config"] == "test"
    assert rows[0]["queries"] == 5
    assert rows[0]["impact_rate"] == 0.6


# ---------------------------------------------------------------------------
# Tests: full analyze pipeline
# ---------------------------------------------------------------------------


def test_analyze_telemetry_pipeline():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False
    ) as f:
        for _ in range(5):
            f.write(json.dumps(SAMPLE_EVENT_NO_GRAPH) + "\n")
        for _ in range(3):
            f.write(json.dumps(SAMPLE_EVENT_WITH_GRAPH) + "\n")
        f.flush()
        path = Path(f.name)

    report = analyze_telemetry([path], include_raw=True)
    assert report.total_events_analyzed == 8
    assert report.mode == "analyze"
    assert len(report.config_summaries) >= 1
    assert len(report.recommendations) >= 1
    assert report.raw_metrics is not None
    assert len(report.raw_metrics) == 8

    path.unlink()


# ---------------------------------------------------------------------------
# Tests: helpers
# ---------------------------------------------------------------------------


def test_safe_avg_empty():
    assert _safe_avg([]) == 0.0


def test_safe_avg_values():
    assert _safe_avg([1.0, 2.0, 3.0]) == pytest.approx(2.0)
