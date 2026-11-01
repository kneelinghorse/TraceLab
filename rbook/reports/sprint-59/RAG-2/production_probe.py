"""RAG-2 production probe: POST /search on the deployed build, recorded with its checks.

Run from anywhere once the RAG-2 merge is deployed:

    python3 cmos/reports/sprint-59/RAG-2/production_probe.py

Reads Derek's MCP credential from ~/.config/tracelab-mcp/credentials.json and
sends it as X-API-Key; the key is never printed or written. Every probe is a
read (POST /search writes one search-history row and cost events, nothing else).

  A  a real question against a real project: every citation must name a chunk in
     the response's sources, and opening its document's chunk list must find it.
  B  a nonsense query against the same project: recorded as it comes back.
  C  a nonsense query against a project with no documents: must be the
     nothing-found result (no_evidence, no citations, no model attempt).
  D  a nonsense query with no project filter, the shape of RAG-1's probe: any
     citation returned must resolve.
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
MATH_FUNZZZ = "d5bdd379-ce47-475b-af7a-1876db30b105"  # no documents, Derek-Private

PROBES = [
    {
        "id": "A-real-question",
        "request": {
            "query": (
                "What signals does the tiered LLM routing research recommend for "
                "deciding when to escalate a query to a stronger model?"
            ),
            "project_id": TRACELAB_RESEARCH,
            "top_k": 5,
        },
    },
    {
        "id": "B-nonsense-populated-project",
        "request": {
            "query": "How many zorblax quintals of mauve krellium did the Vantor expedition harvest in 1873?",
            "project_id": TRACELAB_RESEARCH,
            "top_k": 5,
        },
    },
    {
        "id": "C-nonsense-empty-project",
        "request": {
            "query": "What did the Vantor expedition conclude about krellium yields and zorblax tides?",
            "project_id": MATH_FUNZZZ,
            "top_k": 5,
        },
    },
    {
        # The shape of RAG-1's production probe (no project filter), which came back
        # citing {"document_id": "Unknown", "chunk_id": null}.
        "id": "D-nonsense-unscoped",
        "request": {
            "query": "Summarize the qwibbet flensing ratios recorded at Dornhollow station.",
            "top_k": 5,
        },
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


def check(response: dict) -> dict:
    citations = response.get("citations", [])
    sources = {source["chunk_id"]: source for source in response.get("sources", [])}
    labels = LABEL_RE.findall(response.get("answer", ""))
    checks = {
        "deployed_build_has_no_evidence_field": "no_evidence" in response,
        "cache_hit": (response.get("cache") or {}).get("hit"),
        "no_evidence": response.get("no_evidence"),
        "sources": len(sources),
        "citations": len(citations),
        "labels_in_answer_text": len(labels),
        "model_attempts": len((response.get("routing") or {}).get("attempts", [])),
        "completion_tokens": [
            (attempt.get("usage") or {}).get("completion_tokens")
            for attempt in (response.get("routing") or {}).get("attempts", [])
        ],
    }
    resolved = []
    for citation in citations:
        source = sources.get(citation.get("chunk_id"))
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
    checks["citation_resolution"] = resolved
    checks["every_citation_resolves"] = all(
        item["in_response_sources"] and item["opens_in_document_chunk_list"] for item in resolved
    )
    return checks


def main() -> int:
    OUT.mkdir(exist_ok=True)
    health: object = None
    for _ in range(30):
        status, health = call("GET", "/health")
        if status == 200:
            break
        time.sleep(10)
    else:
        print("ABORT: /api/v1/health never returned 200")
        return 1

    summary: dict[str, object] = {
        "deployed_commit": health.get("commit") if isinstance(health, dict) else None
    }
    for probe in PROBES:
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        status, response = call("POST", "/search", probe["request"])
        record = {"probe": probe["id"], "sent_at_utc": started, "request": probe["request"], "status": status}
        if status == 200 and isinstance(response, dict):
            record["checks"] = check(response)
        record["response"] = response
        (OUT / f"{probe['id']}.json").write_text(json.dumps(record, indent=2) + "\n")
        summary[probe["id"]] = {"status": status, **record.get("checks", {})}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
