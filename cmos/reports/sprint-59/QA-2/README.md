# QA-2 receipt: search absorbed into the Librarian (2026-09-23)

QA-2 is the fifth Sprint 59 mission in build order, after QA-1 gave the Librarian its "Ask the documents" answer mode. Searching now happens inside the Librarian. Next to asking a question, the Librarian can list the ranked chunks that match a phrase, which is a different job: scanning twenty chunks for a quote you half remember. Each chunk opens at its place in its document. A list can be saved as a collection, and the phrase can be saved as a saved search. The standalone Search page is gone, and `/search` redirects to the Librarian with its query. The `/search` service and the MCP `tracelab_search` tool are unchanged.

The feature merged as PR #383 (`814c166`, squash). This receipt PR also carries a one-line fix to a flaky Sprint 58 test, described under "Found along the way". Session `PS-2026-09-23-008`. The design was recorded as decision #545 before any code was written.

**In short.** On the deployed build, `/search?q=…` answers 308 and lands on the Librarian's list of 20 chunks for that phrase. Every row names its document, and the first link opened its chunk marked in its document. No page under `/search` answers with a page any more, and the deployed build manifest has no `/search` page. The production baseline of `/search`, `/librarian` and the list passed all 12 checks (Light and Dark, 1440 and 390 px, America/Chicago clock). The browser sent no write.

## What changed

| change | where |
| --- | --- |
| **"List the chunks", a third reply mode.** A phrase goes into the URL (`/librarian?q=<phrase>&project=<id>`), so a reload, a link or the `/search` redirect lands on the same list. The list is never a transcript turn, so it never reaches the Librarian's model or a mission draft. It calls `POST /pedr/search` with `top_k` 20, in the selected project or in every project the user can read. Each row shows rank, document name, score (4 decimals, because RRF scores cluster around 0.01) and the chunk's text. Each row links to QA-1's chunk link `/documents/{id}?chunk=<chunk_id>&index=<chunk_index>` and has the existing "+ Collection" picker. A chunk with no document is shown without a link | `frontend/src/components/librarian/ChunkList.tsx` (new), `frontend/src/pages/librarian.tsx` |
| **Saved as a collection.** "Save N chunks as a collection" creates one collection, named after the phrase by default, through the existing `POST /collections`. It then adds the chunks in rank order through `POST /collections/{id}/chunks`. If an add fails, the created collection is kept, and "Add the remaining N" adds only the chunks still missing | `ChunkList.tsx` |
| **Saved searches run in the Librarian.** "Run now" on `/saved-searches`, and a saved search picked in the command palette, open `/librarian?saved=<id>`. The Librarian calls the existing execute endpoint, the only call that counts a run and sets "Last run", and lists the ranked chunks it returns. The answer the endpoint also returns is not shown. The list is never refetched on focus, because each execute call counts a run and pays for a model call. "Save current search" in the list saves the phrase with its project and `top_k` 20 | `ChunkList.tsx`, `frontend/src/pages/saved-searches.tsx`, `frontend/src/components/CommandPalette.tsx` |
| **The Search page is retired.** Deleted: `pages/search/index.tsx`, `features/search/SearchExperience.tsx` and its test, and the four components only that page used (`SearchBar`, `ResultCard`, `RagSynthesis`, `PEDRMetadataPanel`). Navigation no longer has a Search entry. `/search` is a permanent 308 redirect to `/librarian`, and Next carries the query string. The route map and the roadmap's migration table both gain the row | `frontend/src/lib/route-migrations.json`, `cmos/foundational-docs/roadmap-sprints-50-53-ux-overhaul.md` |
| **Recent searches are gone from the palette.** Search history was only ever written by `POST /search` and by saved-search runs. The chunk list records none, so the palette would have listed only agents' probe questions and never the user's own lists. The palette's typed search now goes to `/librarian?q=` | `CommandPalette.tsx` |
| **Dead client code removed.** Six `search.ts` calls lost their only consumer: RAG answers, plain retrieval, facets, and history list, clear and replay. They were deleted along with their parity-manifest rows (reconciliation block `qa2`). The backend routes stay | `frontend/src/lib/api/search.ts`, `frontend/src/types/search.ts`, `cmos/contracts/mcp-parity-manifest.json` |
| **The UI baseline covers the list.** The read-only smoke treats `POST /pedr/search` as a read, in place of the retired facets call, and adds `/librarian?q=Qdrant&project=<TraceLab Research>` to its routes | `frontend/scripts/ui-shell-smoke.mjs` |
| **Docs** | `docs/frontend_architecture.md` (routes table, palette, redirect count), `docs/saved-searches.md` (the frontend integration) |

**Why `POST /pedr/search`, not `POST /search`.** The mission's first criterion said "the existing POST /search retrieval", and its notes asked the build to decide. `POST /search` returns only the compressed chunks, meaning those with cosine 0.4 or more, or the single best one. A query therefore returns only a handful, and each one costs a model call. The list's job needs the full ranked list and PEDR's lexical layer, which is what finds a remembered phrase, with no model call. `POST /pedr/search` was already the Search page's own list call. On production it returned 20 chunks, all with text, for "Qdrant" in TraceLab Research. All 20 chunk ids resolved to the same chunk and index in their documents, which is what the links and collection adds rely on.

**Not changed.**
- `POST /search`, `/retrieval/search`, the history routes and the MCP `tracelab_search` tool.
- The `/saved-searches` management page, apart from its Run link.
- The document page keeps QA-1's "Cited" marker, including for a chunk opened from the list.

## Tests

| test | what it holds |
| --- | --- |
| `frontend/src/__tests__/librarian.test.tsx`, "listing the chunks" (7 new) | a listed phrase goes into the URL and never to the Librarian's model; the URL's phrase lists ranked chunks, each linking to its place in its document, and a chunk with no document is not a link; no project means every readable project; saving as a collection makes one collection in rank order, and a retry adds only the missing chunks; "Save current search" keeps the project and a `top_k` of 20; a saved search runs once through execute, shows no answer, and does not rerun on focus; a deleted saved search says so and offers no retry |
| `frontend/src/components/AppShell.test.tsx` | the palette submits to `/librarian?q=`; no navigation link points at a redirecting or retired alias (derived from the route map) |
| `frontend/src/components/CommandPalette.test.tsx` | a saved search opens `/librarian?saved=`; there is no Recent searches section |
| `frontend/src/lib/route-migrations.test.ts`, `route-migration-links.test.ts` | two live redirects (`/inbox`, `/search`), each bound to the roadmap table; a link to `/librarian` is canonical |
| `frontend/tests/e2e/search-command.spec.ts` (rewritten), `app-shell.spec.ts` | palette keyboard reach from the Librarian; `/search?q=` lands on the list, the list is saved as a collection and as a search, and that search reruns from `/saved-searches` and from the palette (Light and Dark at 390, 820 and 1440); loading, no match, failure and a missing saved search stay distinct |

## Mutation proof

`mutation_proof.py` disables one chunk-list rule at a time and runs the Librarian tests through vitest's JSON reporter. Each run must turn exactly its expected tests red. The script refuses to start unless the target files match HEAD, restores each file after its run, and checks them against HEAD again at the end. On `39887d7` (main plus this receipt's test fix and the script as committed), all 8 runs came out as expected (`mutation-proof.json`, logs in `mutation-logs/`).

| run | what is disabled | red tests (the rest pass) |
| --- | --- | --- |
| baseline, before | nothing | none |
| Q1 | a saved search's list is never refetched on focus | the saved-search test |
| Q2 | a retry adds only the missing chunks | the collection test |
| Q3 | a retry reuses the collection it created | the collection test |
| Q4 | a listed phrase goes to the URL, not the model | the URL test |
| Q5 | the list asks for 20 chunks | the list test, the all-projects test and the save-search test |
| Q6 | a chunk link names its index | the list test and the saved-search test |
| baseline, after | nothing | none |

The first run, on main `814c166` before the fix, had one unexpected red in its "before" baseline. That was the flaky Sprint 58 test described below, not a chunk-list test. The six mutations came out as expected in that run too.

## Before merge

- vitest: 260 passed in 36 files. `type-check` and `lint --max-warnings=0` clean. Both parity audits and their node tests exit 0: 103 operations, 98 live, 9 tools, 49 actions.
- CI's exact production-build lane, run in a clean worktree of `c188188`: `npm ci --omit=dev`, `npm run build` (the Route (pages) table has `/librarian` and no `/search`, `pre-merge/production-build-routes.txt`), then `npm ci --include=dev` and Playwright against `next start --workers=1`. 58 passed (`pre-merge/production-build-playwright.log`), and the route migration check covered 10 of 10 rows with 20 of 20 checks passing. Curled against that build: `/search?q=scope%20%26%20provenance` gave 308 to `/librarian?q=scope%20%26%20provenance`, while `/search/anything` and `/search/results` gave 404.
- PR #383: all ten checks green, including the eight required contexts.

## Production

| fact | value |
| --- | --- |
| merge commit | `814c1668791f420287550dea5f62a8a04998a5cc` |
| Railway TraceLab (backend) | deployment `de9f9ecb-882d-4e09-9d5e-3122a332f92c`, SUCCESS on `814c166` |
| Railway frontend | deployment `5c9908ef-b092-469f-a54b-beb7427cb3d7`, SUCCESS on `814c166`; `/api/version` serves `814c166…` |
| main-push runs on `814c166`, all success | Backend Tests `35922825982`, Backend Integration `35922826343`, Backend Lint `35922826071`, Frontend Checks `35922826173`, Frontend Production Build `35922826273`, MCP Package `35922826034`, Secret Scan `35922826142`, Post-Deploy Check `35922827162`; scheduled Production Smoke `35924901034` also ran on it and passed |
| public smoke | `tests/e2e/production-smoke.spec.ts`, 4 of 4 (`production/public-smoke.log`) |

**The ALIAS-1 trap, checked on production** (`production_check.mjs`, results in `production/check.json`). In Sprint 54, deleting a page did not retire its URL, because a sibling dynamic route kept answering 200. So every URL under `/search` was requested without following redirects:

| request | answer |
| --- | --- |
| `/search` | 308 → `/librarian` |
| `/search?q=scope%20%26%20provenance` | 308 → `/librarian?q=scope%20%26%20provenance` |
| `/search?q=Qdrant&project=0afcc588-…` | 308 → `/librarian?q=Qdrant&project=0afcc588-…` |
| `/search?saved=00000000-…` | 308 → `/librarian?saved=00000000-…` |
| `/search/results?q=scope`, `/search/anything`, `/search/index`, `/features/search` | 404, served by `/_error` |

The deployed build manifest lists `/librarian` and no `/search` page. The only page with "search" in its name is `/saved-searches`. `/librarian?q=…` is served by the Librarian page.

**The list, signed in, read-only.** A browser with the API key (every write was blocked, and none was attempted) opened `/search?q=Qdrant&project=<TraceLab Research>` and landed on `/librarian?q=Qdrant&project=…`. The page requested `top_k` 20 in that project and showed "20 chunks match “Qdrant”", with every row naming its document. The first link, "TR-04Optimizing-Qdrant-on-Railway.md #12", opened that document at chunk #12, expanded and marked (`production/librarian-list-1440.png`, `production/chunk-opened-1440.png`).

**Baseline** (`frontend/scripts/ui-shell-smoke.mjs` from `814c166`, direct against production, America/Chicago clock, `production-baseline/`). `/search`, `/librarian` and `/librarian?q=Qdrant&project=…` passed all 12 checks: status 200, no axe violations, no overflow, no transport or client errors, and no link to a legacy alias. `/search` lands on `/librarian`. The full run made 128 checks over 32 routes, with 12 writes suppressed and no legacy internal links. Its only 6 failures come from two causes that predate QA-2, each failing in both themes (see below). Visual review of the 12 captures: the list reads in both themes at both widths, long document names wrap at 390, and the save controls sit under the list.

## Found along the way

- **Fixed here: a flaky Sprint 58 test.** "drafts a mission from the transcript…" asserted the draft panel's focus the instant the panel appeared, but focus is set in an effect a moment later. It failed on the first, cold run of the mutation proof twice, and passed 25 warm runs in a row. The assertion now waits for focus (`waitFor`), and it still fails when the panel never takes focus (checked by removing the `focus()` call).
- **The full baseline fails on `/evidence`** (both themes and widths). The Evidence page marks its groups seen with `PUT /api/v1/activity/viewed/evidence` (BADGE-1, Sprint 58), and the smoke harness suppresses only `PUT /api/v1/activity/viewed`, so it counts the evidence write as a forbidden one. That's a gap in the harness, not a product defect.
- **One document fails axe at 390 px.** Document `d472fbab-…` has wide code blocks and a table, and its horizontally scrollable regions are not keyboard-focusable (`scrollable-region-focusable`, serious). This comes from the document reader and the document's content, not from QA-2.
- **Two app-shell theme-bootstrap Playwright tests fail under `next dev`,** on main as well as on the branch. They pass against `next start`, which is what CI runs.
- **Observed, left as is:** a bare `/search` (no query) lands on the Librarian in its default "Talk it through" mode, because there is no phrase to list. `SaveSearchButton`'s `preset` props now have no caller (the Search page's "save from history" was the only one). `docs/frontend_architecture.md` still lists "saved mission views" in the palette and `/missions/queue` among the routes, both removed in earlier sprints.
