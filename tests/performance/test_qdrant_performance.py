"""Tests for the Qdrant parameter sweep benchmark."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

import scripts.qdrant_parameter_sweep as sweep


class _StubSweepService:
    def __init__(self):
        self.collection_name = "research_chunks"
        self.vector_size = 8

    def search_chunks(self, *, query_vector, top_k, hnsw_ef, **_kwargs):
        del query_vector
        quality = top_k if hnsw_ef >= 96 else max(top_k - 2, 1)
        stable_ids = [f"chunk-{idx}" for idx in range(top_k)]
        blended = stable_ids[:quality] + [f"approx-{idx}" for idx in range(top_k - quality)]
        time.sleep(0.001 + hnsw_ef / 50000.0)
        return [
            {"chunk_id": chunk_id, "score": 1.0 - (idx * 0.01)}
            for idx, chunk_id in enumerate(blended)
        ]

    def get_collection_diagnostics(self):
        return {
            "collection": self.collection_name,
            "collection_exists": True,
            "points_count": 500_000,
            "vectors_count": 500_000,
            "payload_indexes": [],
            "hnsw": {
                "m": 16,
                "ef_construct": 100,
                "full_scan_threshold": 20_000,
                "on_disk": False,
            },
            "quantization": {
                "enabled": True,
                "type": "ScalarType.INT8",
                "always_ram": True,
                "quantile": 0.99,
            },
            "optimizer": {"indexing_threshold": 20_000},
            "vector_size": self.vector_size,
            "memory_estimate_bytes": 750_000_000,
            "memory_estimate_gb": 0.7,
            "error": None,
        }


@pytest.fixture
def sample_vectors() -> list[list[float]]:
    return [[0.01 * idx for _ in range(8)] for idx in range(12)]


def test_parameter_sweep_finds_configuration_with_latency_headroom(tmp_path: Path, sample_vectors):
    service = _StubSweepService()
    output = tmp_path / "qdrant-sweep.json"
    payload = sweep.run_sweep(
        top_k=5,
        trials=len(sample_vectors),
        ef_values=[64, 96, 128],
        output_path=output,
        service=service,
        sample_vectors=sample_vectors,
    )

    assert output.exists()
    assert payload["recommendation"]["hnsw_ef"] == 96
    low_recall = next(entry for entry in payload["results"] if entry["hnsw_ef"] == 64)
    assert low_recall["recall"] < 1.0
    fast_result = payload["recommendation"]
    slow_result = next(entry for entry in payload["results"] if entry["hnsw_ef"] == 128)
    assert slow_result["p99_latency_ms"] > fast_result["p99_latency_ms"]
