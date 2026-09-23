# RAG-4 receipt: the model sees the chunks that answer the question (2026-09-23)

RAG-4 is the third Sprint 59 mission in build order. RAG-3's production probes found it. With chunk text restored, answers cited real chunks, but not the ones that answer the question. Both came back "the provided context does not state ...". QA-1 Requires this mission: its acceptance needs an answer that states the fact.

PR #378 was squash-merged as `65b11ef`. Session `PS-2026-09-23-006`. The design was recorded as decision #541 before any code.

**In short.** On production, the chunk that answers each question now ranks in the top five with the graph layer on, reaches the model with the other relevant chunks, and the answer states its fact. The reworded PII question gets "92% of 32-token (short) text inputs were recovered word-for-word". A new question about the Qdrant report gets "$48–$63" a month. Every citation opens at its chunk.

## The causes

1. **Graph expansion demoted the best matches.** The graph layer is seeded with the top 10 retrieval results and never ranked a seed itself (`graph_layer.py:273`, `if next_urn not in seed_set`). Under reciprocal rank fusion, a seed's neighbours collected a semantic share and a graph share, and the seed only a semantic share. With production's weights (semantic 0.308, graph 0.12, k 60), a neighbour at semantic rank 11 and graph rank 2 scores 0.00628 against the seed's 0.00505 at semantic rank 1. On production every top-five result had semantic rank 11 to 23. The chunk that answers the PII question was 15th.
2. **One chunk per answer.** Compression keeps a chunk only at cosine `rag_context_threshold` or more. The default was 0.7, and Railway does not set it. text-embedding-3-large gave at most 0.664 on these questions, so only compression's at-least-one survivor reached the model.

## What production similarities look like (measured before the fix)

`similarity_distribution.py` ran seven questions against TraceLab Research through POST /pedr/search, graph layer off and top 30 (read-only, no model call). The results are in `similarity-before-fix.json`. Four are answered in the project; each answering chunk was picked by reading the document. Three are not answered there.

| question | answered in project | top five cosines | where the answering chunk is |
| --- | --- | --- | --- |
| A: RAG-3's cost question | yes | 0.657, 0.638, 0.551, 0.549, 0.536 | chunk 10 (the cost table): rank 25, 0.425 |
| B: RAG-3's PII question | yes | 0.664, 0.650, 0.595, 0.543, 0.526 | chunk 14: rank 1, 0.664 |
| B2: the PII question reworded | yes | 0.492, 0.467, 0.399, 0.388, 0.386 | chunk 14: rank 2, 0.467 |
| C: Qdrant on Railway monthly cost (new) | yes | 0.634, 0.598, 0.553, 0.520, 0.511 | chunks 8 and 9: ranks 1 and 2, 0.634 and 0.598 |
| X1: sourdough bread | no | 0.166 at most | – |
| X2: 2018 World Cup final | no | 0.143 at most | – |
| X3: Kubernetes pod autoscaling | no | 0.374, 0.370, 0.362, 0.359, 0.354 | – |

Every answering chunk scored between 0.425 and 0.664. The highest unrelated chunk was 0.399: B2's third result, a Qdrant configuration chunk. An in-domain question the project cannot answer (X3) sits at 0.35–0.37, and off-topic questions sit near 0.15. The lexical layer returned nothing for all seven question-phrased queries.

**For QA-1.** An unsupported in-domain question (X3) peaks at 0.374 and a supported question can peak at 0.492 (B2). A refusal rule based on the best similarity has a band of about 0.1 to work in on this corpus. The 0.4 floor sits in the gap between 0.399 and 0.425, which is narrow. It was measured on seven questions against one project.

## What changed

| change | where |
| --- | --- |
| **The graph layer ranks its seeds first**, in the order retrieval gave them, then the chunks it reached, by score as before. A seed entry carries depth 0, its own seed score and itself as `seed_urn`. A reached chunk can pass a seed only with a better lexical or semantic rank. Seeds are ordered by position, not score: lexical seeds carry `ts_rank_cd` and semantic seeds carry cosine, so a score order would reorder them between layers. With no reached chunks the layer still returns nothing. Seeds count toward the 100-result cap, so at most 90 reached chunks appear | `app/services/pedr/graph_layer.py` (`_build_results`) |
| **The expanded count still counts reached chunks.** `graph_candidates_expanded` counts results at depth 1 or more, so the seeds now in the graph results do not inflate it. The graph layer's own metadata (`total_candidates`, `depth_stats`) never included them | `app/services/pedr/search_orchestrator.py` |
| **Compression's floor is 0.4.** It is the same setting (`rag_context_threshold`), still an absolute cosine, with no new variable. `.env.example` says the same | `app/core/config.py`, `.env.example` |

**Effect with production's weights.** When lexical returns nothing, the ten seeds hold fused ranks 1–10 in semantic order, and the graph layer reorders only from rank 11 down. On production, all four questions' graph-on top five are semantic ranks 1–5 (below).

## Tests

| test | criterion |
| --- | --- |
| `test_best_match_keeps_first_place_over_its_graph_neighbours`: the production shape, through the orchestrator with the real graph layer. The best match (semantic rank 1) links to a neighbour at semantic rank 11, which the old ranking put at graph rank 2, and first overall. The best match now ranks first, the ten seeds hold the top ten, and the neighbour is still reached | 1 |
| `test_seeds_lead_the_ranking_in_retrieval_order`: a lexical seed (0.05) ranked before a semantic seed (0.66) keeps its place above the semantic seed's neighbour (0.66 × 0.7) | 1 (the position-not-score choice) |
| `test_graph_never_moves_a_chunk_above_its_seeds` (graph e2e, T37.4's 12 queries): the seeds keep the top five on every query | 1 |
| `test_production_similarities_reach_the_model_and_unrelated_chunks_do_not`: four chunks at 0.55–0.66 survive and one at 0.15 is dropped, at the setting's code default (what production runs) | 2 |

**Tests whose meaning changed.** Two graph e2e checks from T37.4 ("the graph impacts results", "the graph changes rankings") passed only because of the defect. On the base commit every rank change in that dataset was the same: the first chunk after the five seeds jumped from sixth to first, in 4 of the 12 queries. After the fix no ranking changed. `test_graph_changes_rankings` became `test_graph_never_moves_a_chunk_above_its_seeds`. `test_graph_impacts_results` now asks a question retrieval only partly finds, and asserts the graph surfaces the chunks it missed. Also updated to the new rule: `test_depth_boundary_keeps_candidates_without_reading_their_edges` (the seed now leads its results), `test_cycle_handling` (the seed appears once, at depth 0) and `test_rag_service_run_query`, whose second chunk (cosine 0.61, inside production's answering range) now reaches the model.

## Mutation proof

`mutation_proof.py` reverts one fix at a time to the pre-fix code, runs nine tests in a fresh pytest process that writes no bytecode, and puts the file back. Each restored snippet is asserted to occur exactly once in `78bbc7e`, main before RAG-4. The script refuses to start unless all three files match HEAD, and checks they match HEAD again at the end.

Run against main at `65b11ef`, after a first run against the branch commit `6654fbc` with the same outcome. Results are in `mutation-proof.json`; logs are in `mutation-logs/`.

| run | what is reverted | red tests (the rest pass) |
| --- | --- | --- |
| baseline, before | nothing | none |
| M1 | seeds ranked in the graph layer | the production-shape test: the top three are (semantic, graph) = (11, 2), (23, 1), (1, none), the neighbour first and the best match third; the retrieval-order test; the e2e seeds test; the three graph-layer tests updated to the new rule |
| M2 | counting only reached chunks as expanded | the production-shape test (12 expanded, not 2) and the integration test `test_orchestrator_graph_candidates_expanded` (3, not 2) |
| M3 | the 0.4 floor (0.7 again) | the compression test: only the 0.66 chunk survives |
| baseline, after | nothing | none |

T7, the graph e2e test that the graph surfaces chunks retrieval missed, passes in every run, including M1: the fix removes no legitimate graph effect.

## Production

**Deploys of `65b11ef`:**

- TraceLab `21bbd7dd-2037-42b4-9d02-4946f98ebd72` and frontend `303c644d-4142-45ec-ac53-d689bcd1cd6d`, both created 16:57:16Z and both SUCCESS on `65b11ef` before the probe.
- `/api/v1/health` reported `65b11ef5e4a1acfbbb757f781dc712c698a9b9bc` on the probe's first check.

**How the probe ran.** `production_probe.py` imports RAG-3's probe and ranking diagnosis, so the requests, credential handling and citation checks are the same code. It asked two questions through POST /search and POST /pedr/search, as Derek (owner) through his MCP credential, against TraceLab Research (`0afcc588`) with `top_k` 5, at 17:03:37Z–17:03:49Z. Neither question had been sent to /search before. Both came back `cache.hit: false`, since the semantic cache still holds RAG-3's answers. Full requests and responses are in `production-probes/`.

| check | B2: the PII question reworded | C: Qdrant on Railway cost (new) |
| --- | --- | --- |
| answering chunk in POST /pedr/search's top five, graph on | chunk 14 at 2 | chunks 8 and 9 at 1 and 2 |
| graph-on top five, by semantic rank | 1, 2, 3, 4, 5 | 1, 2, 3, 4, 5 |
| chunks reaching the model (compression at 0.4) | 2 of 5: chunks 13 (0.492) and 14 (0.467); the third, 0.399, was dropped | 5 of 5 (0.634 to 0.511), all from the Qdrant report |
| answer states the fact | "92% of 32-token (short) text inputs were recovered word-for-word from their embeddings" | "a total monthly bill of approximately $48–$63" |
| citations, and each opens at its chunk through GET /documents/{id}/chunks | 2 (chunks 13 and 14); both resolve | 2 (chunks 8 and 9); both resolve |
| model, quality, cost | gpt-5.1 only, 0.932, $0.0036 | gpt-5.1 only, 0.967, $0.0057 |

**A check of mine failed first, not the answer.** On the first run the probe exited 1. Its "32-token" pattern did not accept the non-breaking hyphen (U+2011) the model wrote in "32‑token". The pattern was widened to U+2010–U+2015 and re-applied to the recorded answers with `--recheck`, sending no request. Asking /search again would only return the cached answer. The first run's output and summary are kept: `first-run-output.txt` and `summary-as-run.json`.

**Where the answering chunks land, graph layer on and off** (top 20, `production-probes/ranking.json`):

| question | graph on, before RAG-4 (RAG-3's diagnosis) | graph on, now | graph off |
| --- | --- | --- | --- |
| B: PII, chunk 14 | 15th | **1st** | 1st |
| A: cost, chunk 9 (opens the cost analysis) | not in the top 5 | **1st** | 1st |
| A: cost, chunk 10 (the cost table, semantic rank 25) | 6th | 16th | not in the top 20 |
| B2: PII reworded, chunk 14 | – | 2nd | 2nd |
| C: Qdrant cost, chunks 8 and 9 | – | 1st and 2nd | 1st and 2nd |

Chunk 10 of the cost document now ranks 16th, below its seeds rather than above them. That was accepted in the design (decision #541), and criterion 3 records it without requiring it. Its cosine to the cost question is 0.425: the table is in the document, but the question's wording barely matches it.

**Criterion 3 is met.** The reworded PII question and a new question, each with its answering chunk identified beforehand by reading the document: that chunk ranks in the top five of POST /pedr/search with the graph layer on, reaches the model, and the answer states its fact. Every citation opens at its chunk. Neither question hit the cache.

## Gates

| gate | result |
| --- | --- |
| ruff 0.8.0 on every changed `.py` (source, tests, the scripts here); Secret Scan on the same files | clean |
| targeted: graph layer, graph and semantic-edge e2e, PEDR unified search and scope, PEDR error handling, recovery diagnostics, compression, RAG service and RAG scope; plus `tests/integration/test_graph_search.py` | 164 passed, 2 skipped (both need a live OpenAI and Qdrant); integration 16 passed |
| CI's backend-suite invocation, run locally | 2827 passed, **1 failed**, 3 skipped, 12 deselected (the required 12), in 17 min. The failure was `test_graph_latency_remains_acceptable` (semantic-edge e2e): average graph latency 5.52 ms against a 5.0 ms limit, with the machine's load average between 5 and 20. It passes alone. Measured with the PEDR cache off, 20 passes each: branch mean 0.69 ms (max 0.88), base `78bbc7e` mean 0.65 ms (max 1.23). The change adds about 0.04 ms (seeds now go through the one chunk-id lookup), about seven times under the limit. It passed in PR #378's backend-suite |
| PR #378 | ten of ten checks green (backend-suite, backend-integration, vitest, type-check, lint, ruff-diff, build-frontend-production, mcp-package, both Secret Scans) |
| main-push runs for `65b11ef` | eight of eight green: Backend Tests `35892301042`, Backend Integration `35892300990`, Backend Lint `35892300973`, Frontend Checks `35892300935`, Frontend Production Build `35892300999`, MCP Package `35892301029`, Secret Scan `35892301081`, Post-Deploy Check `35892301397`, all success |

## Criteria

| # | criterion | result |
| --- | --- | --- |
| 1 | a best match keeps its place with the graph on; design recorded as a decision before code; unit test in the production shape; fails with the fix reverted | met: decision #541 recorded before code; production-shape test red under M1 with exactly that shape |
| 2 | more than one relevant chunk reaches the model; cut set against production similarities through the existing setting; unit test at 0.55–0.66 surviving and an unrelated chunk dropped | met: 0.4 in `rag_context_threshold`, measured in `similarity-before-fix.json`; test red under M3; on production 2 and 5 chunks reached the model |
| 3 | production, reusing RAG-3's scripts: the PII question reworded and a new question with a known answering chunk; top five with the graph on, reaches the model, the answer states the fact, every citation opens; record where cost chunks 9 and 10 land | met (above) |
| 4 | CI's pytest invocation and ruff pass; receipt with main-push run ids and both Railway deployment ids | met, with the one load-induced timing failure in the local run disclosed above; PR #378's backend-suite passed |

## Handed on

- **QA-1 is next and can start.** Answers now state facts from the chunk that holds them. QA-1's refusal rule for unsupported questions has the similarity measurements above to work from: supported questions peaked at 0.49–0.66, an unsupported in-domain question at 0.37, and off-topic questions near 0.15. Compression still keeps at least one chunk, so an unsupported question reaches the model with its nearest chunk. The refusal is QA-1's rule to add.
- **The semantic cache** holds B2's and C's answers until about 17:03Z on 2026-09-24. A later probe needs new wording.
