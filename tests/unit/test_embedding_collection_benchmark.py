"""Tests for embedding collection benchmark helpers."""

from __future__ import annotations

import pytest

import scripts.embedding_collection_benchmark as bench


def test_precision_recall_ndcg_single_relevant_hit():
    retrieved = ["doc-a", "doc-b", "doc-c", "doc-d", "doc-e"]
    target = "doc-c"

    precision = bench.precision_at_k(retrieved, target, top_k=5)
    recall = bench.recall_at_k(retrieved, target)
    ndcg = bench.ndcg_at_k(retrieved, target)

    assert precision == pytest.approx(0.2)
    assert recall == 1.0
    assert ndcg == pytest.approx(1 / 2.0)  # rank=3 => 1/log2(4)


def test_metrics_when_target_missing():
    retrieved = ["doc-a", "doc-b", "doc-c"]
    target = "doc-z"

    assert bench.precision_at_k(retrieved, target, top_k=5) == 0.0
    assert bench.recall_at_k(retrieved, target) == 0.0
    assert bench.ndcg_at_k(retrieved, target) == 0.0


def test_percentile_interpolates():
    values = [10.0, 20.0, 30.0, 40.0]
    assert bench.percentile(values, 0.95) == pytest.approx(38.5)
