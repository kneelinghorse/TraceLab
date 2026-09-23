"""RAG-3 follow-up diagnosis: where the chunk that answers each probe question ranks.

Run from anywhere against the deployed build:

    python3 cmos/reports/sprint-59/RAG-3/ranking_diagnosis.py

Read-only: POST /pedr/search makes no model call and writes nothing. For each
production-probe question it searches TraceLab Research twice, with the graph
layer on (the default, as /search runs it) and off, and records where the chunk
that answers the question ranks. The answering chunks were picked by reading the
documents: TR-03.RAG-Cost-Optimization.md chunk 10 holds the cost-per-query
table, TR-02.PII-Detection-Redaction.md chunk 14 holds the Vec2Text result.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.tracelab.aquex.ai/api/v1"
OUT = Path(__file__).resolve().parent / "ranking-diagnosis.json"
TRACELAB_RESEARCH = "0afcc588-e722-45bd-8320-f486601b877c"
TOP_K = 20

CASES = [
    {
        "id": "A-rag-cost",
        "query": (
            "According to the RAG cost optimization research, how much cheaper per query "
            "is the architecture with context compression than the naive baseline?"
        ),
        "answering_document": "b68f0a3e-b8b5-4056-9628-2aeaccd298d0",
        "answering_chunk_index": 10,
    },
    {
        "id": "B-embedding-inversion",
        "query": (
            "What does the PII redaction research say about recovering original text "
            "from embeddings, and how much of a short input could be reconstructed?"
        ),
        "answering_document": "1b6d9489-55ef-4868-b2b4-fa8535e414c4",
        "answering_chunk_index": 14,
    },
]


def _credential() -> str:
    return json.loads((Path.home() / ".config/tracelab-mcp/credentials.json").read_text())["key"]


def call(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    request = urllib.request.Request(  # noqa: S310 - fixed https API base
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"X-API-Key": _credential(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()[:2000]


def ranking(query: str, enable_graph: bool) -> list[dict]:
    body = {"query": query, "project_id": TRACELAB_RESEARCH, "top_k": TOP_K, "enable_graph": enable_graph}
    status, payload = call("POST", "/pedr/search", body)
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"/pedr/search returned {status}: {payload}")
    return [
        {
            "rank": position,
            "document_id": result.get("document_id"),
            "chunk_index": result.get("chunk_index"),
            "layer_ranks": result.get("layer_ranks"),
            "semantic_cosine": (result.get("layer_scores") or {}).get("semantic"),
            "rrf_score": result.get("rrf_score"),
        }
        for position, result in enumerate(payload.get("results", []), start=1)
    ]


def main() -> int:
    report = {"top_k": TOP_K, "project_id": TRACELAB_RESEARCH, "cases": []}
    for case in CASES:
        entry = {"id": case["id"], "query": case["query"]}
        for label, enable_graph in (("graph_on", True), ("graph_off", False)):
            rows = ranking(case["query"], enable_graph)
            answering = next(
                (
                    row
                    for row in rows
                    if row["document_id"] == case["answering_document"]
                    and row["chunk_index"] == case["answering_chunk_index"]
                ),
                None,
            )
            entry[label] = {
                "answering_chunk_rank": answering["rank"] if answering else f"not in top {TOP_K}",
                "answering_chunk": answering,
                "top_5": rows[:5],
                "top_5_semantic_ranks": [(row["layer_ranks"] or {}).get("semantic") for row in rows[:5]],
            }
        report["cases"].append(entry)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
