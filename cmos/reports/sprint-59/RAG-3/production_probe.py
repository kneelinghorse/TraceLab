"""RAG-3 production probe: real questions to POST /search and POST /pedr/search on the deployed build.

Run from anywhere once the RAG-3 merge is deployed:

    python3 cmos/reports/sprint-59/RAG-3/production_probe.py <merge sha>

Waits until /api/v1/health reports the given commit, then asks each question
twice against TraceLab Research, once through POST /search (answer and
citations) and once through POST /pedr/search (the ranked chunks). Reads Derek's
MCP credential from ~/.config/tracelab-mcp/credentials.json and sends it as
X-API-Key; the key is never printed or written. Everything here is a read: POST
/search writes one search-history row and cost events, nothing else.

The questions were never asked before the deploy, because the semantic cache
(24 hours) still holds answers generated from the empty context RAG-3 fixes;
each record keeps cache.hit to show it.

Checks, per question:
  /search       every source has text, compression saw tokens, at least one
                citation, and every citation names a chunk in the sources and
                opens in its document's chunk list at the same index
  /pedr/search  every result has text, a document id and a chunk index, and
                belongs to the requested project (an owner's graph results
                used to skip that filter)
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.tracelab.aquex.ai/api/v1"
OUT = Path(__file__).resolve().parent / "production-probes"
LABEL_RE = re.compile(r"\[Document:\s*([^\],]+),\s*Chunk:\s*([^\]]+)\]", re.IGNORECASE)

TRACELAB_RESEARCH = "0afcc588-e722-45bd-8320-f486601b877c"  # 25 documents, Derek-Private

QUESTIONS = [
    {
        # Answered in TR-03.RAG-Cost-Optimization.md, chunk 10 (the cost-per-query table).
        "id": "A-rag-cost",
        "query": (
            "According to the RAG cost optimization research, how much cheaper per query "
            "is the architecture with context compression than the naive baseline?"
        ),
    },
    {
        # Answered in TR-02.PII-Detection-Redaction.md, chunk 14 (Vec2Text inversion).
        "id": "B-embedding-inversion",
        "query": (
            "What does the PII redaction research say about recovering original text "
            "from embeddings, and how much of a short input could be reconstructed?"
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


def document_chunks(document_id: str) -> dict[str, int | None]:
    """chunk_id -> chunk_index for every chunk of a document, through the public API."""
    found: dict[str, int | None] = {}
    page = 1
    while True:
        status, payload = call("GET", f"/documents/{document_id}/chunks?page={page}&page_size=100")
        if status != 200 or not isinstance(payload, dict):
            return found
        for chunk in payload.get("data", []):
            found[str(chunk["id"])] = chunk.get("chunk_index")
        if page >= (payload.get("pagination") or {}).get("pages", 1):
            return found
        page += 1


def check_search(response: dict) -> dict:
    sources = response.get("sources", [])
    by_chunk = {source["chunk_id"]: source for source in sources}
    citations = response.get("citations", [])
    compression = response.get("compression") or {}
    resolved = []
    for citation in citations:
        source = by_chunk.get(citation.get("chunk_id"))
        in_document = document_chunks(citation["document_id"]) if citation.get("document_id") else {}
        resolved.append(
            {
                "document_id": citation.get("document_id"),
                "chunk_id": citation.get("chunk_id"),
                "chunk_index": citation.get("chunk_index"),
                "in_response_sources": source is not None
                and source.get("document_id") == citation.get("document_id"),
                "opens_in_document_chunk_list": citation.get("chunk_id") in in_document
                and in_document[citation.get("chunk_id")] == citation.get("chunk_index"),
            }
        )
    return {
        "cache_hit": (response.get("cache") or {}).get("hit"),
        "no_evidence": response.get("no_evidence"),
        "sources": len(sources),
        "every_source_has_text": bool(sources) and all((s.get("content") or "").strip() for s in sources),
        "compression": {
            key: compression.get(key)
            for key in ("original_chunks", "filtered_chunks", "original_tokens", "filtered_tokens", "threshold")
        },
        "labels_in_answer_text": len(LABEL_RE.findall(response.get("answer", ""))),
        "citations": len(citations),
        "citation_resolution": resolved,
        "every_citation_resolves": bool(resolved)
        and all(item["in_response_sources"] and item["opens_in_document_chunk_list"] for item in resolved),
        "model_attempts": [attempt.get("model") for attempt in (response.get("routing") or {}).get("attempts", [])],
        "quality_composite": (response.get("quality") or {}).get("composite_score"),
    }


def check_pedr(response: dict) -> dict:
    results = response.get("results", [])
    rows = [
        {
            "chunk_id": result.get("chunk_id"),
            "document_id": result.get("document_id"),
            "project_id": result.get("project_id"),
            "chunk_index": result.get("chunk_index"),
            "content_chars": len(result.get("content") or ""),
            "contributing_layers": result.get("contributing_layers"),
            "layer_ranks": result.get("layer_ranks"),
            # semantic is Qdrant's cosine similarity, the value compression compares with 0.7
            "layer_scores": result.get("layer_scores"),
        }
        for result in results
    ]
    graph_ranked_better = [
        row["chunk_id"]
        for row in rows
        if (row["layer_ranks"] or {}).get("graph")
        and (row["layer_ranks"] or {}).get("semantic")
        and row["layer_ranks"]["graph"] < row["layer_ranks"]["semantic"]
    ]
    return {
        "results": len(rows),
        "every_result_has_text": bool(rows) and all(row["content_chars"] > 0 for row in rows),
        "every_result_has_document_and_index": bool(rows)
        and all(row["document_id"] and row["chunk_index"] is not None for row in rows),
        "every_result_in_requested_project": bool(rows)
        and all(row["project_id"] == TRACELAB_RESEARCH for row in rows),
        "graph_ranked_better_than_semantic": graph_ranked_better,
        "rows": rows,
        "layers_used": (response.get("metadata") or {}).get("layers_used"),
        "cache_hit": (response.get("metadata") or {}).get("cache_hit"),
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: production_probe.py <merge sha>")
        return 2
    expected_commit = sys.argv[1]
    OUT.mkdir(exist_ok=True)
    health: object = None
    for attempt in range(60):
        status, health = call("GET", "/health")
        commit = health.get("commit") if isinstance(health, dict) else None
        print(f"health attempt {attempt}: status {status}, commit {commit}")
        if status == 200 and commit == expected_commit:
            break
        time.sleep(10)
    else:
        print("ABORT: /api/v1/health never reported the expected commit")
        return 1

    summary: dict[str, object] = {"deployed_commit": health.get("commit")}
    for question in QUESTIONS:
        record: dict[str, object] = {"question": question["id"]}
        search_request = {"query": question["query"], "project_id": TRACELAB_RESEARCH, "top_k": 5}
        record["search_sent_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        status, search = call("POST", "/search", search_request)
        record["search"] = {"request": search_request, "status": status, "response": search}
        if status == 200 and isinstance(search, dict):
            record["search"]["checks"] = check_search(search)

        pedr_request = {"query": question["query"], "project_id": TRACELAB_RESEARCH, "top_k": 5}
        record["pedr_sent_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        status, pedr = call("POST", "/pedr/search", pedr_request)
        record["pedr"] = {"request": pedr_request, "status": status, "response": pedr}
        if status == 200 and isinstance(pedr, dict):
            record["pedr"]["checks"] = check_pedr(pedr)

        (OUT / f"{question['id']}.json").write_text(json.dumps(record, indent=2) + "\n")
        summary[question["id"]] = {
            "search_status": record["search"]["status"],
            "search": record["search"].get("checks"),
            "pedr_status": record["pedr"]["status"],
            "pedr": {
                key: value
                for key, value in (record["pedr"].get("checks") or {}).items()
                if key != "rows"
            },
        }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
