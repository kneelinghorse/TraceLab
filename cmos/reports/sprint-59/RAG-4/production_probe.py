"""RAG-4 production probe: the chunk that answers the question reaches the model.

Run from anywhere once the RAG-4 merge is deployed:

    python3 cmos/reports/sprint-59/RAG-4/production_probe.py <merge sha>

Reuses RAG-3's probe and ranking diagnosis (imported from ../RAG-3, so the
requests, the credential handling and the citation and chunk checks are the
same code). Waits until /api/v1/health reports the given commit, then:

  1. asks each question through POST /search (answer and citations) and POST
     /pedr/search (the ranked chunks, graph layer on, as /search runs it);
  2. checks the answering chunk, picked beforehand by reading the document,
     ranks in the top five, reaches the model (is one of /search's sources),
     and that the answer states its fact, with every citation opening at its
     chunk (RAG-3's check_search);
  3. records, graph layer on and off, where each answering chunk ranks in the
     top 20, including TR-03 chunks 9 and 10 for RAG-3's cost question.

`--recheck` re-applies the fact patterns to the recorded answers without
sending anything (see recheck()).

Reads Derek's MCP credential from ~/.config/tracelab-mcp/credentials.json; the
key is never printed or written. Each /search writes one search-history row and
cost events, nothing else; /pedr/search writes nothing. The questions were never
sent to /search before the deploy, and each record keeps cache.hit, because the
semantic cache holds RAG-3's answers for 24 hours.
"""

import importlib.util
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "production-probes"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rag3 = _load("rag3_probe", HERE.parent / "RAG-3" / "production_probe.py")
diagnosis = _load("rag3_diagnosis", HERE.parent / "RAG-3" / "ranking_diagnosis.py")

TRACELAB_RESEARCH = rag3.TRACELAB_RESEARCH
PII_DOCUMENT = "1b6d9489-55ef-4868-b2b4-fa8535e414c4"  # TR-02.PII-Detection-Redaction.md
QDRANT_DOCUMENT = "bdc8881c-8747-4b5a-8c98-5d360bc0721e"  # TR-04Optimizing-Qdrant-on-Railway.md
COST_DOCUMENT = "b68f0a3e-b8b5-4056-9628-2aeaccd298d0"  # TR-03.RAG-Cost-Optimization.md

QUESTIONS = [
    {
        # RAG-3's PII question reworded. Chunk 14: "One study found that 92% of
        # 32-token text inputs could be reconstructed exactly from their embeddings."
        "id": "B2-embedding-inversion-reworded",
        "query": (
            "If someone stole the vectors in our database, could they rebuild the sentences "
            "they came from? What share of short inputs did the study recover word for word?"
        ),
        "answering": (PII_DOCUMENT, [14]),
        # Hyphens include U+2010-U+2015: the model wrote "32\u2011token" (non-breaking).
        "fact": [r"92\s*(%|percent)", r"32[\s\-\u2010-\u2015]*token"],
    },
    {
        # New. Chunks 8 and 9 both hold the cost table (chunks overlap):
        # "Total  Hobby  $48 - $63", and chunk 9 repeats "$48-$63" in prose.
        "id": "C-qdrant-railway-cost",
        "query": (
            "What total monthly bill does the Qdrant on Railway report estimate for "
            "self-hosting half a million vectors on the Hobby plan?"
        ),
        "answering": (QDRANT_DOCUMENT, [8, 9]),
        "fact": [r"\$\s*48", r"\$?\s*63\b"],
    },
]

# Where the answering chunks land, graph layer on and off (top 20). The RAG-3
# questions are only ranked here: their /search answers are still cached.
DIAGNOSIS = [
    {"id": "A-rag-cost", "query": diagnosis.CASES[0]["query"], "answering": (COST_DOCUMENT, [9, 10])},
    {"id": "B-embedding-inversion", "query": diagnosis.CASES[1]["query"], "answering": (PII_DOCUMENT, [14])},
    *({"id": q["id"], "query": q["query"], "answering": q["answering"]} for q in QUESTIONS),
]


def _position(rows: list[dict], document_id: str, chunk_index: int) -> int | None:
    return next(
        (
            position
            for position, row in enumerate(rows, start=1)
            if row.get("document_id") == document_id and row.get("chunk_index") == chunk_index
        ),
        None,
    )


def recheck() -> int:
    """Re-run the fact check on the recorded answers, with no request sent.

    The first run's "32-token" pattern missed the non-breaking hyphen the model
    wrote. /search cannot be asked again (the semantic cache now holds these
    answers), so the corrected patterns are applied to the recorded responses;
    the first run's summary is kept as summary-as-run.json.
    """
    summary = json.loads((OUT / "summary.json").read_text())
    if not (OUT / "summary-as-run.json").exists():
        (OUT / "summary-as-run.json").write_text(json.dumps(summary, indent=2) + "\n")
    for question in QUESTIONS:
        record = json.loads((OUT / f"{question['id']}.json").read_text())
        answer = record["search"]["response"].get("answer", "")
        checks = record["checks"]
        checks["answer_states_fact"] = {
            pattern: bool(re.search(pattern, answer, re.I)) for pattern in question["fact"]
        }
        checks["met"] = (
            checks["cache_hit"] is False
            and any(rank is not None for rank in checks["answering_chunk_top5_rank"].values())
            and any(checks["answering_chunk_reached_model"].values())
            and all(checks["answer_states_fact"].values())
            and checks["every_citation_resolves"]
        )
        (OUT / f"{question['id']}.json").write_text(json.dumps(record, indent=2) + "\n")
        summary["questions"][question["id"]].update(checks)
    summary["rechecked_from_recorded_responses"] = (
        "The first run's 32-token pattern missed the model's non-breaking hyphen (U+2011); "
        "the corrected patterns were applied to the recorded answers, no request was sent. "
        "The first run's summary is summary-as-run.json."
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: value.get("met") for key, value in summary["questions"].items()}, indent=2))
    return 0 if all(q.get("met") for q in summary["questions"].values()) else 1


def main() -> int:
    if sys.argv[1:] == ["--recheck"]:
        return recheck()
    if len(sys.argv) != 2:
        print("usage: production_probe.py <merge sha> | --recheck")
        return 2
    expected_commit = sys.argv[1]
    OUT.mkdir(exist_ok=True)
    health: object = None
    for attempt in range(60):
        status, health = rag3.call("GET", "/health")
        commit = health.get("commit") if isinstance(health, dict) else None
        print(f"health attempt {attempt}: status {status}, commit {commit}")
        if status == 200 and commit == expected_commit:
            break
        time.sleep(10)
    else:
        print("ABORT: /api/v1/health never reported the expected commit")
        return 1

    summary: dict[str, object] = {"deployed_commit": health.get("commit"), "questions": {}}
    for question in QUESTIONS:
        document_id, indexes = question["answering"]
        record: dict[str, object] = {"question": question["id"], "answering": question["answering"]}

        search_request = {"query": question["query"], "project_id": TRACELAB_RESEARCH, "top_k": 5}
        record["search_sent_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        status, search = rag3.call("POST", "/search", search_request)
        record["search"] = {"request": search_request, "status": status, "response": search}

        pedr_request = {"query": question["query"], "project_id": TRACELAB_RESEARCH, "top_k": 5}
        record["pedr_sent_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        pedr_status, pedr = rag3.call("POST", "/pedr/search", pedr_request)
        record["pedr"] = {"request": pedr_request, "status": pedr_status, "response": pedr}

        checks: dict[str, object] = {}
        if status == 200 and isinstance(search, dict) and pedr_status == 200 and isinstance(pedr, dict):
            search_checks = rag3.check_search(search)
            pedr_checks = rag3.check_pedr(pedr)
            record["search"]["checks"] = search_checks
            record["pedr"]["checks"] = pedr_checks
            cosine = {row["chunk_id"]: (row["layer_scores"] or {}).get("semantic") for row in pedr_checks["rows"]}
            sources = search.get("sources", [])
            answer = search.get("answer", "")
            checks = {
                "cache_hit": search_checks["cache_hit"],
                "answering_chunk_top5_rank": {
                    index: _position(pedr.get("results", []), document_id, index) for index in indexes
                },
                "answering_chunk_reached_model": {
                    index: _position(sources, document_id, index) is not None for index in indexes
                },
                "chunks_reaching_model": [
                    {
                        "document_id": source.get("document_id"),
                        "chunk_index": source.get("chunk_index"),
                        "semantic_cosine": cosine.get(source.get("chunk_id")),
                    }
                    for source in sources
                ],
                "compression": search_checks["compression"],
                "answer_states_fact": {pattern: bool(re.search(pattern, answer, re.I)) for pattern in question["fact"]},
                "citations": search_checks["citations"],
                "every_citation_resolves": search_checks["every_citation_resolves"],
                "pedr_top5_semantic_ranks": [(row["layer_ranks"] or {}).get("semantic") for row in pedr_checks["rows"]],
                "model_attempts": search_checks["model_attempts"],
            }
            checks["met"] = (
                checks["cache_hit"] is False
                and any(rank is not None for rank in checks["answering_chunk_top5_rank"].values())
                and any(checks["answering_chunk_reached_model"].values())
                and all(checks["answer_states_fact"].values())
                and checks["every_citation_resolves"]
            )
        record["checks"] = checks
        (OUT / f"{question['id']}.json").write_text(json.dumps(record, indent=2) + "\n")
        summary["questions"][question["id"]] = {
            "search_status": status,
            "pedr_status": pedr_status,
            "answer": search.get("answer") if isinstance(search, dict) else None,
            **checks,
        }

    ranking: list[dict] = []
    for case in DIAGNOSIS:
        document_id, indexes = case["answering"]
        entry: dict[str, object] = {"id": case["id"], "query": case["query"]}
        for label, enable_graph in (("graph_on", True), ("graph_off", False)):
            rows = diagnosis.ranking(case["query"], enable_graph)
            entry[label] = {
                "answering_chunk_rank": {
                    index: _position(rows, document_id, index) or f"not in top {diagnosis.TOP_K}"
                    for index in indexes
                },
                "top_5_semantic_ranks": [(row["layer_ranks"] or {}).get("semantic") for row in rows[:5]],
                "top_5": rows[:5],
            }
        ranking.append(entry)
    (OUT / "ranking.json").write_text(json.dumps(ranking, indent=2) + "\n")
    summary["ranking"] = [
        {
            "id": entry["id"],
            "graph_on": entry["graph_on"]["answering_chunk_rank"],
            "graph_off": entry["graph_off"]["answering_chunk_rank"],
            "graph_on_top_5_semantic_ranks": entry["graph_on"]["top_5_semantic_ranks"],
        }
        for entry in ranking
    ]
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if all(q.get("met") for q in summary["questions"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
