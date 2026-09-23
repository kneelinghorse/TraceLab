# QA-1 receipt: ask the Librarian a question about the research (2026-09-23)

QA-1 is the fourth Sprint 59 mission in build order, after RAG-2, RAG-3 and RAG-4 made the answers it serves cite real chunks that state the fact. On the Librarian page a user can now ask a question about a project's documents. Every citation in the answer opens the chunk it came from. A question the project cannot support is refused ("Nothing in this project answers that question."), never guessed. The answer budget is chosen per request.

Two PRs, both squash-merged: #380 (`ccade35`), the feature, and #381 (`b140085`), two fixes found by the first production run. Session `PS-2026-09-23-007`. The design was recorded as decision #543 before any code.

**In short.** On the deployed build, three questions about TraceLab Research got answers citing the chunks that hold their facts. Every citation link opened its document at that chunk, and the question the project cannot answer was refused before any model call. The first production run found two defects, both fixed in #381 and verified by a second run:
- A range citation ("Chunks: 9–10") was left in the answer as raw text.
- A long cited chunk's header was scrolled off screen.

## What changed

| change | where |
| --- | --- |
| **One Q&A path.** `answer_question(db, user, project_id, question, max_tokens)` applies the caller's scope exactly as POST /search does: accessible projects, and out of scope means the empty-scope result with no pipeline call. It runs the RAG pipeline with `top_k` 5 and splits the answer on blank lines into passages. A passage cites only chunks the model read, resolved with the pipeline's own matcher, and only in documents that still exist. Labels are removed from the text. A paragraph that is only labels lends them to the one before it. A label naming several chunks (`Chunks: 9–10`, `Chunk: 10, 12`) cites each of them (#381). It returns passages, citations with `href`, the chunk ids the model read, `no_evidence`, and per-attempt usage (none on a cache hit). The Librarian calls it now; MCP-6 will call it too | `app/services/corpus_qa.py` (new) |
| **Refusal before the model.** `run_query(refuse_unsupported=True)` returns the nothing-found result, without a model call, when no retrieved chunk reaches the compression floor on its own. By default compression still hands the model its best chunk, so the Search page is unchanged. A semantic-cache hit with nothing at the floor is a miss for a refusing caller. The application cache key gains a component only when the flag is set, so every other key is byte-identical | `app/services/rag_service.py`, `app/services/cache_manager.py` |
| **Refusal when nothing is cited.** An answer whose passages resolve no citation is replaced by the refusal. It is never shown as prose | `app/services/corpus_qa.py` |
| **The model is told its length.** The RAG prompt now says "Keep the answer within about N words; citations do not count toward that", with N = max_tokens / 4 (350 → 87, 600 → 150, 2000 → 500). A citation label costs 33 tokens because it carries the document UUID. RAG-3's answer B spent 341 of 350 tokens on 157 words and four labels. This applies to every caller, /search included | `app/services/rag_service.py` |
| **The semantic cache matches on the budget.** It filtered on project, document, source type and filters only, so a full synthesis could be served an earlier short answer. `max_tokens`, already stored on every entry, is now a filter, with an integer payload index | `app/services/semantic_cache.py` |
| **The Librarian turn in answer mode.** `POST /librarian/turns` accepts `mode: "answer"` and `max_tokens` (64 to 4000, answer mode only; default `settings.rag_default_max_tokens`). Answer mode needs a project, authorizes it for read like any turn, takes the last user message as the question, and never calls the Librarian's model. A cited passage becomes a `corpus_claim` segment citing chunk ids; an uncited one becomes `prose`. The LIB-1 validator runs against the chunks the answer was written from and withholds any violation. The response gains `chunks` and `no_evidence`. Each paid model call is recorded as a `librarian_turn` usage row (METER-0) | `app/schemas/librarian.py`, `app/services/librarian.py`, `app/api/v1/librarian.py` |
| **The page.** "Talk it through" / "Ask the documents" (disabled without a project) and, when asking, "Short answer" (600 tokens) / "Full synthesis" (2000), sent with the request. A cited passage shows "From this project's documents" and links named `<document> #<chunk>`. Uncited text renders as plain prose. A refusal renders as a note that asserts nothing, and stays one after a reload | `frontend/src/pages/librarian.tsx`, `frontend/src/lib/api/librarian.ts`, `frontend/src/lib/librarian/storage.ts` |
| **The chunk link.** `/documents/{id}?chunk={chunk_id}&index={chunk_index}` opens the Chunks tab on the page holding that index (the chunker numbers chunks from 0). The chunk is expanded, marked "Cited", and its card's top is scrolled into view (#381), clear of the sticky top bar. If that chunk id is not there, the page says the chunk is no longer in the document rather than show another passage | `frontend/src/pages/documents/[id].tsx` |

**Not changed.**
- No MCP route. MCP-6 adds `tracelab_search` ask over this service and reclassifies the parity manifest.
- The Search page keeps RagQuery's 350-token default; QA-2 retires the page.
- Production's `RAG_DEFAULT_MAX_TOKENS=350` stays. It now reaches only callers that send no budget, and the length line keeps their answers inside it.
- `top_k` stays 5.

## Tests

| test | what it holds |
| --- | --- |
| `tests/test_corpus_qa.py` (12) | passages cite only chunks the model read and drop a fabricated label; a paragraph of labels lends them to the one before it; a label naming several chunks cites each and leaves no raw text (#381); an answer that cites nothing is refused, its paid call still reported; the pipeline's nothing-found result is the refusal; a citation into a deleted document is dropped; a cached answer reports no paid usage; a blank question is rejected; a member gets nothing from a project they cannot read, and the pipeline is never asked; a member who can read it is answered within their scope; through the real pipeline with a fake model, a supported question (cosine 0.63) is answered with resolving citations, and one at 0.374 is refused before the model |
| `tests/test_rag_service.py` (5 new) | a refusing caller is not answered from a chunk below the floor, while the same question without the flag still is; a cached answer below the floor is a miss for a refusing caller and still served to an ordinary one; the model is told its budget; the application cache key is byte-identical without the flag; the semantic cache filters on `max_tokens` and indexes it |
| `tests/test_librarian_api.py::TestAnswer` (7) | answer mode goes to the Q&A service and never the Librarian's model; every rendered citation passes the LIB-1 validator; a citation the answer was not written from is withheld; nothing found renders the refusal and asserts nothing; request rules (answer mode needs a project and a question, `max_tokens` only in answer mode, bounds); a project the user cannot read is 403 before retrieval; each paid model call is metered and a cached answer is not |
| `frontend/src/lib/api/librarian.test.ts` (3) | the wire contract: an answer turn carries `mode` and `max_tokens`; a chunk citation resent in the transcript is named by document and number |
| `frontend/src/__tests__/librarian.test.tsx` (4 new) | the chosen budget goes out and each citation links to its chunk; a short answer by default; the refusal is a note that asserts nothing, also after a reload; no asking without a project |
| `frontend/src/__tests__/document-detail.test.tsx` (3 new) | a citation link opens the Chunks tab on the right page with the chunk expanded and marked; the card's top scrolls into view (#381); a missing chunk is said aloud |

## Mutation proof

`mutation_proof.py` disables one QA-1 rule at a time and runs the QA-1 tests. QA-1 is mostly new code, so a mutation switches a rule off in place rather than restoring pre-QA-1 code. Each run uses 19 backend tests in a fresh pytest process that writes no bytecode, plus 8 frontend tests through vitest's JSON reporter, and then restores the file. Every mutated snippet occurs exactly once. A run counts as expected only when its set of red tests equals the expected set exactly. The script refuses to start unless every target file matches HEAD, and checks they match HEAD again at the end.

Run against main at `b140085`, all 20 runs as expected (`mutation-proof.json`, logs in `mutation-logs/`). A first run against the branch commit `7d732d7`, before #381, had the same outcome for the 15 mutations it had (`mutation-proof-branch-7d732d7.json`).

| run | what is disabled | red tests (the rest pass) |
| --- | --- | --- |
| baseline, before | nothing | none |
| M1 | the relevance floor as a refusal | the pipeline's floor test, the cached-answer test, and the unsupported question through the pipeline |
| M2 | a cached answer below the floor counts as a miss | the cached-answer test |
| M3 | telling the model its length | the budget test, and the supported question through the pipeline (it checks "within about 150 words") |
| M4 | the semantic cache filtering on `max_tokens` | the same-budget test |
| M5 | a separate application-cache entry for a refusing caller | the cache-key test, and both floor tests: a refusing caller's nothing-found result was served to an ordinary caller and back |
| M6 | refusing an answer that cites nothing | the uncited-answer test, and the deleted-document test |
| M7 | the search route's scope rule in the service | the member-without-access test (the route still answers 403 on its own) |
| M8 | citing only chunks in documents that still exist | the deleted-document test |
| M9 | the provenance validator on answer turns | the stray-citation test |
| M10 | routing answer mode to the Q&A service | five of the seven route tests; the 403 and request-rule tests stay green, since they do not depend on routing |
| M11 | reading a label that names several chunks | the multi-chunk label test |
| M12 | expanding a range or list into its chunks | the multi-chunk label test |
| F1 | sending the budget with an answer turn | the client's wire test |
| F2 | the user's budget choice (always short) | the page's budget-and-links test |
| F3 | linking a chunk citation to its chunk (to the evidence page instead, as LIB-1 did) | the page's budget-and-links test |
| F4 | rendering a refusal as a note | the refusal test |
| F5 | reading a citation's chunk from the link | all three deep-link tests |
| F6 | scrolling the cited card's top into view | the header test |
| baseline, after | nothing | none |

## Production

**Deploys.**

| merge | TraceLab | frontend | `/api/v1/health` |
| --- | --- | --- | --- |
| `ccade35` (#380) | `a93d2819-8f46-4a75-8188-c883be41f307` | `e2af52cb-9c7b-4131-a483-0dd0046f3d84` | `ccade354…` at 19:39:21Z |
| `b140085` (#381) | `9472f4c1-9318-4876-b75a-da1f0cc3eb62` | `433f7e45-cb94-41ae-88b3-42b701ca35e9` | `b140085b…` at 20:05:36Z |

**How it ran.** `production_acceptance.mjs` drives https://tracelab.aquex.ai in Playwright as Derek (owner), through his MCP credential sent only to the production API. The clock is America/Chicago. The only write it allows is POST /librarian/turns. For each question it first records the chunks' semantic similarities through POST /pedr/search (read-only, graph layer off). It then picks TraceLab Research on the Librarian page, chooses "Ask the documents" and a budget, asks, and records the request and response. It captures the answer in both themes at 1440 and 390, then opens every citation link. A link passes when the chunk id sits at that index in the document's chunk list, the Chunks tab is selected, exactly one card is marked cited, and its expanded text is that chunk. Each question's answering chunk was picked beforehand by reading TRACE-SHARE-58 (document `04ffc800`, 14 chunks).

**Run 1, on `ccade35`, 19:39–19:40Z** (`production/run-1/`).

| question | budget | similarity | answer | links |
| --- | --- | --- | --- | --- |
| Q1: "When a Miro board is shared at more than one level at the same time, which access level does a user actually get?" | short (600) | answering chunk 6 ranks 1st, 0.584 | cited chunk 6: "the more permissive level applies"; 112 output tokens | 1 of 1 opens |
| Q2: "Compare the workspace-inheritance and project-level sharing archetypes from the research, and explain which option it recommends for TraceLab and why." | full (2000) | answering chunks 9 and 10 rank 2nd and 5th, 0.614 and 0.588 | cites chunks 0, 9 and 10: "recommends a hybrid, project-bounded model as Option 1"; 1,052 output tokens | 3 of 3 open |
| R1: "How should Kubernetes horizontal pod autoscaling be tuned for bursty GPU inference traffic?" (RAG-4's X3) | short | 0.374 at most, below the 0.4 floor | "Nothing in this project answers that question.", no model call, no citations, a note in the page | none |

Two defects, both from this run:
1. **Q2 ended with the raw label** "[Document: 04ffc800-…, Chunks: 9–10]" in plain text (`run-1/Q2-sharing-options-synthesis-light-1440.png`). The model had cited a range, which the service's label reader (the pipeline's single-chunk form) did not read. On that code, an answer whose every label named several chunks would have resolved nothing and been refused.
2. **Opening chunk 9 (771 tokens) centred its text**, which scrolled the card's "#9 Cited" header off screen (`run-1/Q2-sharing-options-synthesis-link-9.png`).

Both are fixed in #381.

**A check of mine was too loose.** My fact check first matched anywhere in the answer. Q1's opening line, "Miro uses a 'highest access wins' rule", carried no label, so it rendered as prose, and that uncited line is what matched. The checks now require the fact in a cited passage and fail on any raw label. `--recheck` re-applied them to run 1's recorded responses without sending anything (`run-1/results-recheck.json`): Q1 and R1 meet every check, and Q2 fails only `no_raw_citation_labels`. The first output is kept as `run-1/output-as-run.txt`.

**A question dropped before asking.** A first wording of Q2 ("What sharing model options does the TRACE-SHARE-58 report lay out ...") was never sent. The similarity pre-check put its answering chunks 6th and 15th, behind the report's reference list, where `top_k` 5 would not reach them.

**Run 2, on `b140085`, 20:07–20:08Z** (`production/run-2/`). All four questions meet every check.

| question | served | what it shows |
| --- | --- | --- |
| Q1, same wording | semantic cache | run 1's answer, word for word; the link opens chunk 6 |
| Q2, same wording | semantic cache | run 1's words (labels aside). The closing paragraph that showed the raw label is now a cited claim linking chunks 9 and 10, with no label left (`run-2/Q2-sharing-options-synthesis-light-1440.png`). The chunk-9 link lands with its header visible (`run-2/Q2-sharing-options-synthesis-link-9.png`) |
| Q3: "Out of the box, does Airtable's workspace setting that restricts adding new collaborators start switched on or off?" (new) | model, 151 output tokens | both passages cited, chunks 5 and 10 (the answering chunks, ranked 1st and 2nd at 0.512 and 0.492): "off by default"; both links open |
| R1, same wording | refused before the model | as run 1 |

Q1 and Q2 were meant to come from the cache: they show the fixed build rendering the exact answer that failed, without a model call. Q3 exercises the model on the final build.

**Cost.** Run 1 made two paid calls (3,978 and 5,784 tokens) and run 2 one (3,975). Each is a `librarian_turn` usage row under Derek's account. The refusals made none.

**The /librarian baseline** (`librarian-baseline/`, `frontend/scripts/ui-shell-smoke.mjs` with `UI_ROUTE=/librarian`, America/Chicago, read-only): Light and Dark at 1440 and 390, 4 checks, 0 failures, no overflow, no axe violations, no page errors. The visual review covered these four captures and every answer capture in both runs:
- With no project, "Ask the documents" is disabled and muted.
- Cited passages carry "From this project's documents" and their links wrap at 390.
- The refusal is a muted note.
- No layout breaks in either theme.

## Found on the way

- **My first tests reached production's Qdrant** (learning #256). Two tests that run the real pipeline passed `cache_service=None`, which RagService reads as "use the shared semantic cache". The repository's local `.env` points that at the same Qdrant Cloud instance production uses (compared by hash), and the collection name is the same. Locally they passed by reaching it; in CI, with no Qdrant, they failed (`FF` in the first PR run of `7d732d7`). What the local runs did to production, checked read-only afterwards:
  - They created the new `max_tokens` integer index on production's `semantic_cache` collection before QA-1 deployed. That is benign; the deployed code creates the same index at startup.
  - Their 3-number fake vectors were rejected by the 3072-dimension collection before any write or delete step, so nothing was written or deleted.
  - The collection was not recreated: its size is 3072, matching the test settings.

  `4799c57` gives those tests a cache that never hits. With Qdrant pointed at a dead port the new tests pass, and the old version fails. Any test that builds a RagService without a cache can still do this; that broader hazard is not fixed here.
- **Production's semantic cache was empty** at about 19:15Z, although RAG-4's notes assumed it still held that afternoon's answers. After run 1 it held two entries, run 1's answers, so writes work now. The cause is unknown. `GET /api/v1/admin/dashboard/data`, which would show the cache counters, returns 500. Both are left as a next-step.
- **Uncited opening lines.** The model can open with an uncited summary line: Q1's did, and run 2 served that same answer from the cache. It renders as plain prose, under-claiming its provenance rather than over-claiming it, which is the direction Rule 2 allows.

## Gates

| gate | result |
| --- | --- |
| ruff 0.8.0 and Secret Scan on every changed file, receipt scripts included | clean |
| CI's backend-suite invocation, run locally on `7d732d7` | 2851 passed, 3 skipped, the required 12 deselected, 0 failed (21 minutes under a load average of 23–80). The two Qdrant-reaching tests passed here only because they reached production's Qdrant; see above |
| integration: `tests/integration/test_rag_pipeline.py` and `test_deepsearch_integration.py` against Postgres | 12 passed |
| frontend: vitest, type-check, lint (zero warnings), production build | 267/267 on #380, 268/268 on #381; the rest clean |
| PR #380 | 10 of 10 checks on `4799c57`; the first run on `7d732d7` was cancelled by the push, with the two Qdrant tests failed (`FF`) |
| PR #381 | 10 of 10 checks |
| main-push runs for `ccade35` | eight of eight green: Backend Tests `35910152303`, Backend Integration `35910152247`, Backend Lint `35910152477`, Frontend Checks `35910152241`, Frontend Production Build `35910152366`, MCP Package `35910152257`, Secret Scan `35910152216`, Post-Deploy Check `35910152649` |
| main-push runs for `b140085` | eight of eight green: Backend Tests `35913054181`, Backend Integration `35913054175`, Backend Lint `35913054266`, Frontend Checks `35913054267`, Frontend Production Build `35913054123`, MCP Package `35913054143`, Secret Scan `35913054188`, Post-Deploy Check `35913054535` |

## Criteria

| # | criterion | result |
| --- | --- | --- |
| 1 | one Q&A service function, the only Q&A path, calling the RAG pipeline and returning answer text, resolved citations and the nothing-found flag; scope as the search route; a test proves a member gets no answer from a project they cannot read | met: `app/services/corpus_qa.py::answer_question`; `TestScope` in `tests/test_corpus_qa.py` (the pipeline is never asked), and 403 at the route (`TestAnswer`) |
| 2 | a Librarian turn that asks about the corpus routes to the service; citations render as links that open the chunk; corpus claims and world knowledge visibly separated; the LIB-1 validator accepts every rendered citation; an empty retrieval renders the refusal and asserts nothing; unit tests for routing, the nothing-found rendering and validator acceptance | met: answer mode, chunk links, "From this project's documents" passages beside plain prose, the validator run on every answer turn, the refusal note; tests above; on production every link opened its chunk |
| 3 | an explicit `max_tokens` per request, short answer or full synthesis (default `settings.rag_default_max_tokens`); the frontend sends it; a test asserts the outbound request carries it | met: 600 / 2000 from the page, asserted at the wire (`librarian.test.ts`) and in the page tests; on production each request carried its budget, and the full synthesis wrote 1,052 tokens inside 2000 |
| 4 | on the deployed build, a real question answered with citations that all resolve, each link opened and checked, and a question with no support refused; request and response recorded; the /librarian baseline in both themes at 1440 and 390 with a non-UTC visual review | met by run 2 (all four questions) and the baseline above; run 1 found the two defects #381 fixed |
| 5 | design recorded as a decision before code; receipt with the main-push run ids and both Railway deployment ids; the roadmap's Sprint 59 section updated | met: decision #543; this receipt; the roadmap updated in this receipt's PR |
