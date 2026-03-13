#!/usr/bin/env python3
"""CLI script to collect Qdrant performance metrics."""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.embedding_service import get_embedding_service
from app.services.qdrant_service import get_qdrant_service
from app.services.retrieval_service import get_retrieval_service


def collect_metrics() -> dict[str, Any]:
    """
    Collect performance metrics for Qdrant and embedding operations.

    Returns:
        Dict with metrics including:
            - collection_info: Qdrant collection stats
            - query_latency: Sample query latency measurements
            - embedding_latency: Sample embedding generation latency
            - token_usage: Estimated token counts
    """
    metrics: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "collection_info": {},
        "query_latency": [],
        "embedding_latency": [],
        "token_usage": {},
    }

    try:
        qdrant_service = get_qdrant_service()

        # Get collection info
        collection_info = qdrant_service.client.get_collection(
            qdrant_service.collection_name
        )
        metrics["collection_info"] = {
            "points_count": collection_info.points_count,
            "vectors_count": collection_info.vectors_count,
            "config": {
                "vector_size": collection_info.config.params.vectors.size,
                "distance": collection_info.config.params.vectors.distance.value
                if hasattr(collection_info.config.params.vectors.distance, "value")
                else str(collection_info.config.params.vectors.distance),
                "on_disk": getattr(
                    collection_info.config.params.vectors, "on_disk", None
                ),
                "quantization": "scalar_int8"
                if collection_info.config.quantization_config
                else None,
            },
        }

        # Sample query latency (if collection has data)
        if collection_info.points_count > 0:
            try:
                embedding_service = get_embedding_service()
                retrieval_service = get_retrieval_service()

                # Generate test query embedding
                test_query = "test query for performance measurement"
                start = time.time()
                query_embedding = embedding_service.generate_embedding(test_query)
                embedding_time = time.time() - start
                metrics["embedding_latency"].append(
                    {
                        "operation": "generate_embedding",
                        "latency_ms": embedding_time * 1000,
                    }
                )

                # Perform sample searches
                for top_k in [5, 10, 20]:
                    tuned_hnsw_ef = retrieval_service.recommend_hnsw_ef(top_k)
                    start = time.time()
                    results = qdrant_service.search_chunks(
                        query_vector=query_embedding, top_k=top_k, hnsw_ef=tuned_hnsw_ef
                    )
                    query_time = time.time() - start
                    metrics["query_latency"].append(
                        {
                            "top_k": top_k,
                            "latency_ms": query_time * 1000,
                            "results_returned": len(results),
                            "hnsw_ef": tuned_hnsw_ef,
                        }
                    )

            except Exception as e:
                metrics["query_error"] = str(e)

        # Token usage (estimated based on collection size)
        # Approximate: each chunk is ~750 tokens on average
        avg_chunks_per_doc = 10  # Rough estimate
        avg_tokens_per_chunk = 750
        if collection_info.points_count > 0:
            metrics["token_usage"] = {
                "estimated_total_chunks": collection_info.points_count,
                "estimated_tokens_per_chunk": avg_tokens_per_chunk,
                "estimated_total_tokens": collection_info.points_count
                * avg_tokens_per_chunk,
                "estimated_openai_cost_usd": (
                    collection_info.points_count * avg_tokens_per_chunk * 0.02
                )
                / 1_000_000,
            }

    except Exception as e:
        metrics["error"] = str(e)

    return metrics


def main():
    """Main CLI entry point."""
    print("Collecting Qdrant performance metrics...")

    metrics = collect_metrics()

    # Save to reports directory
    reports_dir = Path("cmos/reports/sprint-01")
    reports_dir.mkdir(parents=True, exist_ok=True)

    output_file = reports_dir / "qdrant_performance.json"

    with open(output_file, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"Metrics saved to {output_file}")
    print(
        f"Collection points: {metrics.get('collection_info', {}).get('points_count', 0)}"
    )
    if metrics.get("query_latency"):
        avg_latency = sum(q["latency_ms"] for q in metrics["query_latency"]) / len(
            metrics["query_latency"]
        )
        print(f"Average query latency: {avg_latency:.2f}ms")


if __name__ == "__main__":
    main()
