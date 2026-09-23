"""RAG-4 measurement: the cosine similarities text-embedding-3-large gives on production.

Run from anywhere against the deployed build:

    python3 cmos/reports/sprint-59/RAG-4/similarity_distribution.py <label>

Read-only: POST /pedr/search embeds the query and makes no model call and writes
nothing. For each question it searches TraceLab Research with the graph layer
off (so the order is the semantic layer's own) and records the semantic cosine
of every result, which is the value context compression compares with
settings.rag_context_threshold. Questions the project answers sit beside
questions it cannot answer, so the receipt shows where the relevant chunks fall
and where unrelated ones do. The output goes to similarity-<label>.json.

Reads Derek's MCP credential from ~/.config/tracelab-mcp/credentials.json and
sends it as X-API-Key; the key is never printed or written.
"""

import json
import statistics
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.tracelab.aquex.ai/api/v1"
HERE = Path(__file__).resolve().parent
TRACELAB_RESEARCH = "0afcc588-e722-45bd-8320-f486601b877c"
TOP_K = 30

QUESTIONS = [
    # Answered in the project; the answering chunks were picked by reading the documents.
    {
        "id": "A-rag-cost",
        "answered": True,
        "answering": ("b68f0a3e-b8b5-4056-9628-2aeaccd298d0", [10]),
        "query": (
            "According to the RAG cost optimization research, how much cheaper per query "
            "is the architecture with context compression than the naive baseline?"
        ),
    },
    {
        "id": "B-embedding-inversion",
        "answered": True,
        "answering": ("1b6d9489-55ef-4868-b2b4-fa8535e414c4", [14]),
        "query": (
            "What does the PII redaction research say about recovering original text "
            "from embeddings, and how much of a short input could be reconstructed?"
        ),
    },
    {
        "id": "B2-embedding-inversion-reworded",
        "answered": True,
        "answering": ("1b6d9489-55ef-4868-b2b4-fa8535e414c4", [14]),
        "query": (
            "If someone stole the vectors in our database, could they rebuild the sentences "
            "they came from? What share of short inputs did the study recover word for word?"
        ),
    },
    {
        "id": "C-qdrant-railway-cost",
        "answered": True,
        "answering": ("bdc8881c-8747-4b5a-8c98-5d360bc0721e", [8, 9]),
        "query": (
            "What total monthly bill does the Qdrant on Railway report estimate for "
            "self-hosting half a million vectors on the Hobby plan?"
        ),
    },
    # Not answered anywhere in the project.
    {
        "id": "X1-sourdough",
        "answered": False,
        "query": "What is a good recipe for sourdough bread with a crisp crust?",
    },
    {
        "id": "X2-world-cup",
        "answered": False,
        "query": "Who won the 2018 FIFA World Cup final, and what was the score?",
    },
    {
        "id": "X3-kubernetes-autoscaling",
        "answered": False,
        "query": (
            "How should Kubernetes horizontal pod autoscaling be tuned for bursty "
            "GPU inference traffic?"
        ),
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


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: similarity_distribution.py <label>")
        return 2
    report: dict[str, object] = {"top_k": TOP_K, "project_id": TRACELAB_RESEARCH, "questions": []}
    for question in QUESTIONS:
        body = {"query": question["query"], "project_id": TRACELAB_RESEARCH, "top_k": TOP_K, "enable_graph": False}
        status, payload = call("POST", "/pedr/search", body)
        if status != 200 or not isinstance(payload, dict):
            print(f"ABORT: /pedr/search returned {status} for {question['id']}: {payload}")
            return 1
        rows = [
            {
                "rank": position,
                "document_id": result.get("document_id"),
                "chunk_index": result.get("chunk_index"),
                "semantic_cosine": (result.get("layer_scores") or {}).get("semantic"),
                "layers": result.get("contributing_layers"),
            }
            for position, result in enumerate(payload.get("results", []), start=1)
        ]
        cosines = [row["semantic_cosine"] for row in rows if row["semantic_cosine"] is not None]
        entry: dict[str, object] = {
            "id": question["id"],
            "answered_in_project": question["answered"],
            "query": question["query"],
            "results": len(rows),
            "cosine_max": max(cosines, default=None),
            "cosine_top5": cosines[:5],
            "cosine_5th": cosines[4] if len(cosines) >= 5 else None,
            "cosine_median": statistics.median(cosines) if cosines else None,
            "cosine_min": min(cosines, default=None),
            "lexical_results": sum(1 for row in rows if "lexical" in (row["layers"] or [])),
            "rows": rows,
        }
        if question.get("answering"):
            document_id, indexes = question["answering"]
            entry["answering_chunks"] = [
                {"chunk_index": index, "found": next(
                    (row for row in rows if row["document_id"] == document_id and row["chunk_index"] == index),
                    f"not in top {TOP_K}",
                )}
                for index in indexes
            ]
        report["questions"].append(entry)
        print(
            f"{question['id']:34} max {entry['cosine_max']}  5th {entry['cosine_5th']}  "
            f"median {entry['cosine_median']}  min {entry['cosine_min']}"
        )
    (HERE / f"similarity-{sys.argv[1]}.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
