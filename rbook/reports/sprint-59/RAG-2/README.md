# RAG-2 receipt: citations that resolve, or nothing (2026-09-23)

RAG-2 is the first Sprint 59 mission in build order. It came from Derek's hand-off: "create the sprint and missions in cmos so that we can hand this off to a fresh agent session and get this set of work done" (decision #538). It replaces the finding RAG-1 escalated, next-step #417.

The rule it enforces is Rule 2 of the Librarian roadmap: a citation resolves to real evidence, and if it cannot cite, it does not assert.

PR #374 was squash-merged as `949c7a6`. Session `PS-2026-09-23-004`.

The production probes also found a separate defect, filed as **RAG-3**: production search hands the model chunks with no text. It is described under Production below.

## What changed

All code changes are in `app/services/rag_service.py` unless noted.

| change | where |
| --- | --- |
| **Empty retrieval short-circuits.** When no chunk reaches the model's context, `_execute_rag_pipeline` returns the nothing-found result without calling the model. The answer reads "Nothing in this project answers that question." ("…your projects…" when unscoped). The result has no citations, no sources, no routing attempt, no cost, and `no_evidence: true`. It skips the 24-hour semantic cache, so a document indexed later is not hidden behind a cached refusal. `_build_messages` lost its "No relevant context was retrieved" prompt, since no prompt is built without context | `rag_service.py` |
| **A label that names no retrieved chunk is dropped.** `_build_citation` now takes only a retrieved chunk, so a citation can no longer be built from a label. It used to yield `document_id: <label>, chunk_id: null` | `rag_service.py` |
| **The top-chunk fallback citation is removed** | `rag_service.py` |
| **`RagResponse.no_evidence: bool = false`**, the only change to the response shape. `build_empty_scope_result` (a caller with no readable projects) sets it true, since that result also has no evidence and no model call. `run_query` sets the key on every result, cache hits included | `app/schemas/rag.py`, `rag_service.py` |
| **Tests.** Three new tests, one per fix. The two empty-scope tests also assert the flag | `tests/test_rag_service.py`, `tests/test_rag_service_scope.py` |

## Mutation proof (criterion 4)

`mutation_proof.py` does the following for each fix:

1. reverts that one fix;
2. runs the three tests in a fresh pytest process that writes no bytecode;
3. puts the file back.

It refuses to start unless the file matches HEAD, and checks it matches HEAD again at the end.

- **M1 and M2** restore pre-fix code byte for byte. Each restored snippet is asserted to occur exactly once in `659a08a`.
- **M3** restores the fallback through the new one-argument `_build_citation`, which builds the same dict for a retrieved chunk.

Run against main at `949c7a6`. Results are in `mutation-proof.json`; logs are in `mutation-logs/`.

| run | what is reverted | empty retrieval | unresolved label | no fallback |
| --- | --- | --- | --- | --- |
| baseline, before | nothing | pass | pass | pass |
| M1 | the short-circuit, and the old no-context prompt | **fails**: `fake_client.chat.completions.requests == []`, because the model was asked twice with no context | pass | pass |
| M2 | dropping unresolved labels, and the old `_build_citation` | pass | **fails**: `"doc-404" not in {…}` got `{'doc-1', 'doc-404'}` | pass |
| M3 | the top-chunk fallback | pass | pass | **fails**: `result["citations"] == []` got a citation to `chunk-1` |
| baseline, after | nothing | pass | pass | pass |

The file was restored to HEAD after the runs.

## Production (criterion 5)

**Deploys of `949c7a6`:**

- TraceLab `62d8731a-7eef-472c-a8fa-ea83bdfe5ffd` and frontend `794b5683-8ed2-45ba-8616-0aa1ed47f0b6`, both SUCCESS.
- `/api/v1/health` reported healthy at `949c7a61f23ee7a0221d296306d152b796030018`, and every response carried the new `no_evidence` field.

**How the probes ran.** `production_probe.py` sent four fresh questions to POST /search as Derek (owner) through his MCP credential. Every response reported `cache.hit: false`. Full requests and responses are in `production-probes/`; `summary.json` has the checks. Each search wrote one search-history row and cost events, nothing else.

| probe | question | result |
| --- | --- | --- |
| A | a real question against TraceLab Research (`0afcc588`): what signals the tiered LLM routing research recommends for escalating a query | 1 source, **0 citations**. The model's answer carried two `[Document: Unknown, Chunk: N/A]` labels, and both were dropped |
| B | a nonsense question against the same project | 1 source, 0 citations. One `Unknown` label dropped. `no_evidence: false`: retrieval still returned chunks, so this is not the nothing-found case |
| C | a nonsense question against math-funzzz (`d5bdd379`), a project with no documents | **the nothing-found result**: "Nothing in this project answers that question.", `no_evidence: true`, no sources, no citations, **no model attempt**, cost 0, 280 ms |
| D | a nonsense question with no project filter, the shape of RAG-1's probe | 1 source, 0 citations. One `Unknown` label dropped |

RAG-1's production defect was the `{"document_id": "Unknown", "chunk_id": null}` citation. It no longer reaches a response: the label is still in A, B and D's answer text, and none of them returned it as a citation.

### The finding: search hands the model chunks with no text (filed as RAG-3)

In A, B and D, all five retrieved chunks had empty content and no document_id, project_id, chunk_index or embedding. The telltale sign is `compression.original_tokens: 0` with `original_chunks: 5`.

So the model answered a real question about a project whose documents cover it (R2.1, Heuristics for Tiered LLM Routing) with "the provided context contains no information".

**What POST /pedr/search showed.** A read-only call with A's question, with no model call (`pedr-fusion-diagnosis.json`, embeddings removed), found the cause. Every top-five result was found by both the semantic and graph layers, ranked better by graph (for example semantic 18, graph 2), and hollow.

**Why the records are hollow.** `app/services/pedr/fusion.py:160-166` keeps the whole record from the best-ranked layer. The graph layer's records carry only `urn`, `score`, `depth`, `seed_urn`, entity fields and `chunk_id` (`app/services/pedr/graph_layer.py:394-414`).

**Why exactly one chunk reaches the model.** With no embedding, context compression scores each chunk by its RRF score (about 0.006), drops them all below 0.7, and keeps one under its at-least-one rule.

> **Corrected at the Sprint 59 close (2026-09-24, session `PS-2026-09-23-009`,
> receipt re-verification per decision #509).** These two paragraphs describe
> the code at `949c7a6`, and later Sprint 59 missions fixed what they found.
> RAG-3 (PR #376, `4d8257d`, decision #540) made fusion merge a chunk's
> records across layers, so `fusion.py:160-166` now holds that merge
> (`_merge_layer_records`), not the whole-record rule. The graph layer's
> records still carry no chunk text. RAG-4 (PR #378, `65b11ef`,
> decision #542) put the seeds first, which moved the code that builds those
> records to `graph_layer.py:409-415`. RAG-4 also lowered compression's floor
> from 0.7 to 0.4.

**This is not new.** RAG-1's 2026-09-22 probe shows the same zero-token signature and was read then as an irrelevant match. RAG-2 does not touch retrieval.

**Criterion 5 against this.** Its first half, "only resolving citations" on a real project, holds only in the empty sense: with no text to cite, none were made. The real demonstration moves to RAG-3, whose criteria require a real question on this project to come back with citations that open. Its second half holds where retrieval is empty (C). Against a populated project, a nonsense question still retrieves nearest neighbours: Qdrant search has no score threshold, and compression keeps one chunk. So B gets a model answer, not the refusal. That case belongs to QA-1's "refused when unsupported" rule, not to this flag.

**A cost of the fix while RAG-3 is open.** An answer with no resolving citation scores 0.80 against the 0.85 escalation threshold, where the invented citation used to hold it above. So every hollow-context search now makes a second model call:

- $0.0017–0.0021 per search against $0.0008 in RAG-1's probe;
- latency 3.0–4.6 s against 3.6 s.

This ends when retrieval returns text.

**Semantic cache.** Answers cached before the deploy, up to 24 hours old and generated from the same hollow context, can still be served until they expire. The probes asked new questions to avoid them.

## Gates

| gate | result |
| --- | --- |
| ruff 0.8.0 on every changed `.py` (source, tests, both scripts here); `check_format_only_changes.py`; Secret Scan on this folder | clean |
| targeted: `tests/test_rag_service.py`, `test_rag_service_scope.py`, `tests/integration/test_rag_pipeline.py` | 21 passed |
| CI's backend-suite invocation, run locally | 2819 passed, 3 skipped, 12 deselected (the required 12), **1 failed**. The failure is `tests/performance/test_qdrant_performance.py::test_parameter_sweep_finds_configuration_with_latency_headroom`, a timing test that recommended `hnsw_ef` 128 instead of 96 at a load average near 24. It imports only `scripts/qdrant_parameter_sweep`, not the RAG code, and passed three runs of three on its own on the branch. CI's own backend-suite passed |
| PR #374 | ten of ten checks green (backend-suite, backend-integration, vitest, type-check, lint, ruff-diff, build-frontend-production, mcp-package, both Secret Scans) |
| main-push runs for `949c7a6` | eight of eight green: Backend Tests `35822943066`, Backend Integration `35822943067`, Backend Lint `35822943012`, Frontend Checks `35822943097`, Frontend Production Build `35822943068`, MCP Package `35822942977`, Secret Scan `35822943061`, Post-Deploy Check `35822943236` |

## Criteria

| # | criterion | result |
| --- | --- | --- |
| 1 | empty retrieval returns an explicit nothing-found result, the model is not called, and a unit test asserts it | met: `test_empty_retrieval_returns_nothing_found_without_asking_the_model`; production probe C, zero attempts |
| 2 | a label matching no retrieved chunk is dropped, `_build_citation` cannot yield an unmatched id, and a test proves it | met: `test_citation_to_an_unretrieved_document_is_dropped`; in production, A, B and D dropped every `Unknown` label |
| 3 | the top-chunk fallback is removed, with a test | met: `test_uncited_answer_gets_no_citation_to_the_top_chunk` |
| 4 | each test fails with its fix reverted, recorded | met (table above) |
| 5 | nothing else changes shape; CI's pytest invocation and ruff pass; production shows only resolving citations on a real project and the nothing-found result for a nonsense query; receipt with run and deploy ids | met, with two limits stated under Production. Only `no_evidence` was added, and CI and ruff are green. On a real project no citation came back that does not resolve, but none came back at all, because retrieval returned no text (RAG-3 now carries that demonstration). The nothing-found result holds where retrieval is empty, not for a nonsense question against a populated project (QA-1's refusal rule) |

## Handed on

- **RAG-3, new, first in line before QA-1.** Fusion keeps each chunk's text. No chunk without text reaches the model. An explicit project filter applies to graph results for every caller: today, for owner and admin, graph expansion ignores it. Production acceptance is a real question with citations that open.
- **QA-1's notes now carry three findings.**
  - The Search page's answer budget is 350 tokens, not 1500. `RagQuery.max_tokens` defaults to 350 and is capped at 1024 (`app/schemas/rag.py:17-22`), and POST /search always passes it (`app/api/v1/search.py:59`), so PR #348's raise never reached that page. Found by reading the code; the API does not expose per-attempt usage to confirm it from production.
  - `no_evidence` covers empty retrieval only.
  - Citations are rendered from the list, not by linking labels in the answer text.

> **Corrected at the Sprint 59 close (2026-09-24, session `PS-2026-09-23-009`,
> receipt re-verification per decision #509).** QA-2 (PR #383, `814c166`)
> retired the Search page. QA-1 (PR #380, `ccade35`) made the answer budget
> per request: the Librarian sends 600 or 2000. `RagQuery.max_tokens` still
> defaults to 350 with a cap of 1024 for POST /search. After MCP-6's imports
> (PR #385, `0bff859`), that field sits at `app/schemas/rag.py:19-22` and the
> route passes it at `app/api/v1/search.py:63`. `no_evidence` now covers more
> than empty retrieval. It is also set when every retrieved chunk lacks text
> (RAG-3), and when QA-1's Q&A service refuses a question because no chunk
> reaches the 0.4 floor.
