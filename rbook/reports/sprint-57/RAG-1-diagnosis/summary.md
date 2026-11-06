# RAG-1: the skipped cited-answer test, diagnosed and running

Observed 2026-09-22 UTC. Decision #523 holds the diagnosis; PR #355 holds the
fix; this file holds the evidence.

## Root cause (criterion 1)

`tests/integration/test_rag_pipeline.py::test_rag_pipeline_generates_cited_answer`
injected a `retrieval_service` stub and asserted it was called. Since Mission
B21.8 (commit `f89e965`, 2025-12-10) `RagService.run_query` retrieves through a
PEDR orchestrator: `_execute_rag_pipeline` calls `self.pedr_orchestrator.search`,
and the constructor builds that orchestrator with `create_pedr_orchestrator()`
whenever none is injected. The injected `retrieval_service` is stored on the
instance and read by nothing on the query path: a dead constructor parameter.

Running the skipped body directly showed the consequence: the stub was never
called, the factory orchestrator's lexical layer failed on SQLite (`unrecognized
token: "@"`, a PostgreSQL full-text query) and its semantic layer called the real
OpenAI embeddings endpoint with the test key (401), retrieval returned zero
chunks, and synthesis ran anyway. T34.1 (`cf0518c`, 2026-03-12) skipped the test
blaming an openai/httpx `proxies` incompatibility that was never the cause. No
SDK change is involved (criterion 3).

## Fix (criterion 2)

Test wiring only. The stub now implements the orchestrator's `search()` and
returns real `PEDRSearchResult` rows with embeddings parallel to the stub query
embedding, so context compression (threshold 0.7) keeps them. The chunks are
ordered so the top-scoring chunk is not the one the model cites; the assertions
check the citation is anchored to the named chunk (`chunk_id`, `chunk_index`,
`score`, `snippet`).

Mutation proof, each run with the RAG result cache cleared first:

| mutation | result |
| --- | --- |
| none (twice) | green |
| citation pattern matches nothing | red at `citation["document_id"] == "doc-1"` (fallback cited doc-2) |
| chunk matcher never matches | red at `citation["chunk_id"] == "chunk-0"` |
| extractor returns nothing | red at the citation-count assertion |

## Escalated finding (criterion 4), confirmed in production

The same run showed synthesis proceeding with no retrieved context, so the
production route was probed with a query that matches nothing
(`production-probe-empty-query.json`). It returned HTTP 200, an answer that
correctly says the material does not cover the query, and this citation:

```json
{"document_id": "Unknown", "chunk_id": null, "chunk_index": null, "score": null, "snippet": null}
```

The model wrote `[Document: Unknown, Chunk: N/A]`; `_extract_citations` accepted
it because `_build_citation` takes an unmatched label as a document id. The
reverse defect also exists: when the model cites nothing but chunks were
retrieved, a citation to the top-scoring chunk is invented. Both contradict
Rule 2 (a citation resolves to real evidence or is not made) and are recorded
as a next-step for the Q&A sprint rather than fixed here, as the mission asked.
