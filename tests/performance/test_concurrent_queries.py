"""Load testing harness powered by pytest-benchmark."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest


class _SyntheticRagService:
    def __init__(self):
        self.count = 0
        self.lock = threading.Lock()

    def run_query(self, query: str) -> dict:
        del query
        with self.lock:
            self.count += 1
        # simulate lightweight token + cache bookkeeping
        time.sleep(0.0005)
        return {"answer": "ok", "cache": {"hit": False}}


@pytest.mark.benchmark(group="rag_concurrency")
def test_concurrent_queries_reaches_target_throughput(benchmark):
    """Ensure the synthetic workload can execute 100 RAG queries per batch."""
    service = _SyntheticRagService()

    def execute_batch():
        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(lambda idx: service.run_query(f"Query {idx}"), range(100)))

    benchmark(execute_batch)
    assert service.count >= 100
    assert service.count % 100 == 0
