# RAG-3 receipt: retrieval keeps each chunk's text (2026-09-23)

RAG-3 is the second Sprint 59 mission in build order. RAG-2's production probes found it: on the deployed build, search handed the model chunks with no text, so a real question about a project whose documents answer it came back as "the provided context contains no information". QA-1 Requires this mission, because no answer can cite anything until the model sees the text.

PR #376 was squash-merged as `4d8257d`. Session `PS-2026-09-23-005`.

**In short.** On production the model now reads real text, and every citation opens at its chunk. The same probes found the next problem: the model is shown a neighbour of the chunk that answers the question, not that chunk. Both answers cited real text and still said the fact was not there. That is filed as **RAG-4**, ahead of QA-1 (see Production).

## The cause

PEDR search runs up to three retrieval layers: lexical (Postgres full text), semantic (Qdrant), and graph (edges followed from the top lexical and semantic hits). Reciprocal rank fusion then merges them into one ranked list.

Fusion kept the whole record of whichever layer ranked a chunk best (`fusion.py:160-166` before this change). A graph record carries only the chunk id and traversal fields (`urn`, `score`, `depth`, `seed_urn`, entity fields). So every chunk the graph ranked above semantic came out of fusion with no text, document id, project id, chunk index or embedding.

In RAG-2's probe all five top chunks were in that state (semantic rank 13, graph rank 6, and so on). A chunk found by both layers collects two shares of the fusion score, so these hollow records filled the top five. (Why semantic's own top 10 never make the top five is RAG-4's finding, below.) Compression then scored them by their RRF score (about 0.006), dropped all of them below 0.7, and kept one under its at-least-one rule. The model was asked about `[Document: Unknown, Chunk: N/A]` with nothing under it.

## What changed

| change | where |
| --- | --- |
| **Fusion merges a chunk's records across layers.** One record per chunk: the best-ranked layer's, with every field it lacks filled from the other layers, best rank first. A field counts as missing when it is absent, `None`, or an empty string or collection, so a `chunk_index` of 0 is kept. The best-ranked record still wins every field it did supply (its `score`, the graph's `depth`) | `app/services/pedr/fusion.py` |
| **No chunk without text reaches the model.** `_execute_rag_pipeline` leaves out any retrieved chunk whose content is empty or blank. If none is left, it returns RAG-2's nothing-found result without a model call. Its diagnostic reason now reads "Retrieval returned no chunks with text for this query." | `app/services/rag_service.py` |
| **An explicit project or document filter applies to graph results for every caller.** Graph expansion follows edges across projects. `_filter_graph_payloads_by_scope` used to return graph results untouched for a caller with no scope (owners and admins), so their search of one project could pull in another project's chunks. It now runs its one ownership query whenever there is a scope or an explicit filter, and applies the scope only when there is one. With no scope and no filter nothing changes: no query | `app/services/pedr/search_orchestrator.py` |
| **Lint.** `ruff-diff` lints every changed file, so the file's one existing finding had to go: `zip(..., strict=False)` in `fuse_simple`, which keeps its behaviour | `fusion.py` |

**Graph-only chunks.** A chunk found by the graph alone still carries no text out of fusion; the new rule in `rag_service.py` keeps it from the model. The criterion allowed either filling it from the database or leaving it out. Leaving it out needs no new query, and it rarely matters. With production's layer weights (semantic 0.308, graph 0.12), every chunk the semantic layer returns (60) scores above every graph-only chunk (at most 0.12/61 against 0.308/120). So a graph-only chunk reaches the top five only when semantic and lexical together return fewer than five. POST /pedr/search can still show such a record without text in that case.

**A test changed its meaning.** `test_graph_none_scope_with_explicit_filters_preserves_legacy_results` asserted the old behaviour: with no scope, graph results skipped the explicit filters. It is split in two. `test_graph_none_scope_without_filters_adds_no_resolver` keeps the part that still holds (no scope and no filter: no query). `test_explicit_filters_apply_to_graph_results_for_an_unrestricted_caller` asserts the new rule against real rows.

## Tests (criteria 1-3)

| test | criterion |
| --- | --- |
| `TestRRFFusion::test_graph_ranked_chunk_keeps_the_semantic_text_and_ids`: a full semantic record at rank 18 fused with a graph record for the same chunk at rank 2 keeps the semantic content, document and project ids, chunk index, source type and origin, and embedding | 1 |
| `TestPEDRSearchOrchestrator::test_graph_ranked_chunk_reaches_the_response_with_its_text`: the same through the orchestrator, as POST /pedr/search and RAG receive it | 1 |
| `test_chunk_without_text_never_reaches_the_model`: a hollow chunk scoring above the compression threshold stays out of the prompt; only the chunk with text is sent and cited | 2 |
| `test_retrieval_with_no_text_returns_nothing_found_without_asking_the_model`: all chunks hollow gives the nothing-found result, no model call, nothing cached | 2 |
| `test_explicit_filters_apply_to_graph_results_for_an_unrestricted_caller`: with no scope, a project filter drops another project's graph chunk, and a document filter also drops a sibling document's | 3 |
| `test_graph_none_scope_without_filters_adds_no_resolver`: no scope and no filter still makes no ownership query | 3 |

## Mutation proof

`mutation_proof.py` reverts one fix at a time to the pre-fix code, runs the six tests in a fresh pytest process that writes no bytecode, and puts the file back. Each restored snippet is asserted to occur exactly once in `7167a93`, main before RAG-3. It refuses to start unless all three files match HEAD, and checks they match HEAD again at the end.

Run against main at `4d8257d`, after a first run against the branch commit `8f34d91` with the same outcome. Results are in `mutation-proof.json`; logs are in `mutation-logs/`.

| run | what is reverted | red tests (the rest pass) |
| --- | --- | --- |
| baseline, before | nothing | none |
| M1 | the fusion merge | fusion test: `KeyError: 'content'`, since the kept graph record has no content; orchestrator test: `shared.content` is `''` |
| M2 | leaving hollow chunks out | hollow-chunk test: the prompt contains `[Document: Unknown, Chunk: N/A]`; nothing-found test: the model was asked |
| M3 | the explicit filter for a None scope | owner-filter test: the other project's chunk is in the results |
| baseline, after | nothing | none |

All three files were restored to HEAD after the runs.

## Production (criterion 4)

**Deploys of `4d8257d`:**

- TraceLab `5756e3f3-34ff-4b2a-8885-97a0690f0cbf` and frontend `0a569f5b-c5e2-429c-9edb-78913cdee97e`, both SUCCESS by 14:35:35Z.
- `/api/v1/health` reported `4d8257de36561c8feab34b1a35f3bc80018cce7d` on the probe's first check.

**How the probes ran.** `production_probe.py` asked two questions never asked before, as Derek (owner, so no authorization scope) through his MCP credential. Each went to POST /search and then POST /pedr/search, against TraceLab Research (`0afcc588`) with `top_k` 5. The questions were new because the semantic cache still holds, for 24 hours, answers generated from the empty context this mission fixes; both came back `cache.hit: false`. Full requests and responses are in `production-probes/`, and `summary.json` has the checks. Each search wrote one search-history row and cost events, nothing else.

Each question was written after reading the chunk that answers it:

- **A:** how much cheaper per query the architecture with context compression is than the naive baseline. The answer is TR-03.RAG-Cost-Optimization.md chunk 10, a cost table.
- **B:** what the PII research says about recovering text from embeddings. The answer is TR-02.PII-Detection-Redaction.md chunk 14: 92% of 32-token inputs reconstructed exactly.

| check | A | B |
| --- | --- | --- |
| POST /search: every source has text | yes: 1 source, TR-03 chunk 2 | yes: 1 source, TR-02 chunk 11 |
| compression saw text (`original_tokens`; RAG-2's probe had 0) | 3999 tokens in 5 chunks, 1 kept (826 tokens) | 3941 tokens in 5 chunks, 1 kept (799 tokens) |
| citations, and each opens at its chunk through GET /documents/{id}/chunks | 1 citation; resolves | 1 citation (4 labels in the answer text, all naming chunk 11); resolves |
| POST /pedr/search: all 5 results have text, a document id and a chunk index | yes | yes |
| all 5 results in the requested project (owner's explicit filter, criterion 3) | yes | yes |
| results the graph ranked above semantic, the case that used to come back without text | 4 of 5 | 5 of 5 |

**Criterion 4 is met.** A real question returns sources with text and citations that all resolve and open, and POST /pedr/search returns content on every result, including the nine the graph ranked above semantic, the case RAG-2 saw come back without text.

**Cost.** $0.0048 per search for A (escalated to gpt-5.2, as the quality score was 0.80 before escalation) and $0.0045 for B (gpt-5.1 only). RAG-2's hollow-context probes cost $0.0017–0.0021 with two attempts each. The API reports only the estimated total, not tokens per attempt. The rise fits the model now reading about 800 tokens of text and writing a full answer, but that is inferred, not measured.

### The next problem: the model sees the wrong chunk (filed as RAG-4)

Both answers cite real text, and neither answers the question:

- **A:** "The provided context does not state the per-query cost of a 'naive baseline' architecture or an architecture 'with context compression' ... so this cannot be determined from the excerpt."
- **B:** "... it does **not** address attacks on embeddings or the possibility of reconstructing original text from embeddings."

The model was shown one chunk each: TR-03 chunk 2 (embedding costs) and TR-02 chunk 11 (Faker synthetic data). Neither is the chunk that answers. `ranking_diagnosis.py` (read-only, no model call; results in `ranking-diagnosis.json`) ran the same questions through POST /pedr/search with the graph layer on and off:

| question | graph layer | semantic ranks of the top five | where the answering chunk lands |
| --- | --- | --- | --- |
| A | on (as /search runs) | 11, 13, 15, 12, 20 | chunk 10 at 6th (semantic rank 25, cosine 0.425) |
| A | off | 1, 2, 3, 4, 5 (TR-03 chunks 9, 8, 5, 7, 6; cosine 0.66–0.54) | chunk 10 not in the top 20 (chunk 9, the cost analysis's opening, is first) |
| B | on | 11, 13, 18, 16, 23 | chunk 14 at **15th** (semantic rank 1, cosine 0.664) |
| B | off | 1, 2, 3, 4, 5 | chunk 14 **first** |

Two causes, both outside RAG-3's criteria:

1. **Graph expansion demotes the best matches.** The graph layer is seeded with the top 10 retrieval results (`graph_top_k_seeds`) and never ranks a seed itself (`graph_layer.py:273`). Under fusion, each seed's neighbours collect a semantic and a graph share and outrank the seed. That is why every top-five result above has semantic rank 11 or worse.
2. **One chunk per answer.** Compression keeps a chunk only at cosine 0.7 or more (`rag_context_threshold`, not set on Railway, so the code default). The best cosine seen for either question was 0.664, so only compression's at-least-one survivor reaches the model.

Also seen: the lexical layer returned no results for either question, so semantic and graph were the only rankers.

This is filed as **RAG-4, "The model sees the chunks that answer the question"**, first in line before QA-1, which now Requires it. RAG-2 filed RAG-3 the same way, rather than widening the mission it found it in. RAG-4's production check reuses both scripts here.

## Gates

| gate | result |
| --- | --- |
| ruff 0.8.0 on every changed `.py` (source, tests, the three scripts here); Secret Scan on the scripts | clean |
| targeted: `tests/test_pedr_unified_search.py`, `test_rag_service.py`, `test_pedr_search_scope.py`, `test_rag_service_scope.py` | 82 passed, 2 skipped (both need a live OpenAI and Qdrant) |
| CI's backend-suite invocation, run locally | 2825 passed, 3 skipped, 12 deselected (the required 12), 0 failed, in 23 min 39 s at a load average near 19 |
| PR #376 | ten of ten checks green (backend-suite, backend-integration, vitest, type-check, lint, ruff-diff, build-frontend-production, mcp-package, both Secret Scans) |
| main-push runs for `4d8257d` | eight of eight green: Backend Tests `35874856044`, Backend Integration `35874856049`, Backend Lint `35874856004`, Frontend Checks `35874855971`, Frontend Production Build `35874856152`, MCP Package `35874855933`, Secret Scan `35874856041`, Post-Deploy Check `35874856563`, all success |

## Criteria

| # | criterion | result |
| --- | --- | --- |
| 1 | a chunk found by several layers keeps every field any layer supplied; unit test fusing a full semantic record with a better-ranked graph record; fails with the fix reverted | met: fusion and orchestrator tests, both red under M1 |
| 2 | no chunk without text reaches the model; a graph-only chunk is filled from the database or left out; nothing left gives the nothing-found result; unit test | met, by leaving it out: two tests, both red under M2 |
| 3 | an explicit project or document filter applies to graph results for every caller; unit test with an unrestricted caller | met: red under M3; on production every result of the owner's project search is in the project |
| 4 | production with fresh questions: sources with text and citations that resolve and open; POST /pedr/search results carry content; both recorded | met (above). The same probes show the answers are still wrong, which is RAG-4 |
| 5 | CI's pytest invocation and ruff pass; receipt with main-push run ids and both Railway deployment ids | met (above) |

## Handed on

- **RAG-4, new, next in build order.** The graph layer must stop outranking the best matches with their own neighbours, and compression must let more than one relevant chunk reach the model. The production check is a question whose answering chunk is known in advance, and an answer that states the fact.
- **QA-1's notes carry a correction.** In production the default answer budget is still 350 tokens, not 1500. Railway sets `RAG_DEFAULT_MAX_TOKENS=350` on the TraceLab service (`.env.example` says the same), which overrides the code default PR #348 raised. So saved-search runs and history replays get 350 too, not the 1500 RAG-2's notes assumed. QA-1's per-request budget defaults to that setting.
