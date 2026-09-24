# MCP-6 receipt: corpus Q&A over the MCP, @aquex/tracelab-mcp 2.1.0 (2026-09-23)

MCP-6 is the last of Sprint 59's seven missions. An agent using the MCP can now ask a project a question and get the answer the Librarian's "Ask the documents" mode gives. That is either cited passages whose citations open their chunks, or a plain refusal when the project cannot support the question. Both go through QA-1's one Q&A service. Derek published 2.1.0 with his one-time code, and everything before and after that was the agent's. Session `PS-2026-09-23-009`. The design was recorded as decision #547 before any code was written.

**In short.** The published 2.1.0 is byte-identical to the agent's dry run. Installed fresh with `npx` from an empty directory, it passed 19 of 19 checks against production. It asked TraceLab Research whether Airtable's restriction on adding collaborators starts on or off. The answer was "…is off by default out of the box", with one citation to the TRACE-SHARE-58 report that opens its chunk. A question the project cannot support came back as the nothing-found result, and a project that does not exist came back as the API's 404.

## What changed

| change | where |
| --- | --- |
| **`POST /api/v1/search/ask`**, beside `POST /search`. The body has `project_id`, `question` and an optional `max_tokens`. The question must be 1–20,000 characters and not blank, the Librarian's message bound. The budget must be 64–4000, QA-1's bounds, and an omitted budget means the server default. The route loads the project (404 when unknown or deleted) and authorizes it for read with the caller's own principal (403). It then calls `corpus_qa.answer_question` and nothing else | `app/api/v1/search.py`, `app/schemas/rag.py` |
| **The response** has `answer`, `passages` (each passage's text and the chunk ids it cites), `citations` (`chunk_id`, `document_id`, `document_name`, `chunk_index`, `snippet`, `href`), `no_evidence` and `model`. Passages are returned because the service strips the citation labels from the text, and without them an agent could not tell which statement a citation backs | `app/schemas/rag.py` |
| **Metering.** Each paid model call writes one `usage_records` row under a new kind, `search_ask`, attributed to the caller, through the existing writer. A cache hit or a refusal before the model writes none. `kind` is a free 32-character string, so no migration | `app/models/usage_record.py`, `app/services/usage_recorder.py` (docstrings) |
| **The MCP action.** `tracelab_search` gains `ask` beside `knowledge`, `navigate` and `pedr`, taking `project_id`, `question` and `max_tokens`. The input is checked against the API's bounds before any request. The client sends `POST /api/v1/search/ask`. The handler returns the API's body plus `project_url`, and gives each citation a browser `url`, which is its `href` made absolute on the frontend origin. The `href` is kept. The surface is 9 tools and 50 actions | `packages/tracelab-mcp/src/index.ts`, `src/api-client.ts` |
| **Parity manifest.** No new UI operation: the Librarian's answer mode calls `POST /librarian/turns`, and nothing in the frontend calls the new route. The `librarianApi.turn` row stays REST-only by design, since the conversation is LIB-1's, and now maps to `tracelab_search.ask`, as the `createMission` row maps to `tracelab_mission.create`. The reconciliation block `mcp6` records the totals | `cmos/contracts/mcp-parity-manifest.json` |
| **Release 2.1.0**, a minor release because it only adds. It covers the version in `package.json` and the lockfile and the CHANGELOG entry `[2.1.0] — 2026-09-23`. The README and `docs/mcp-tools.md` now say 50 actions, with an ask section and example, and `agents.md`'s surface line says the same. The installed-tarball check (`check-canonical-links.mjs`) expects 50 and has an ask case | `packages/tracelab-mcp/`, `docs/mcp-tools.md`, `agents.md` |

**Service principals are refused.** The shared authentication gate refuses them on every human route, and the UI's only Q&A path refuses them too. An answer is a paid model call metered to a person. A real service account with an API key gets 403 in the tests.

**Not changed:** QA-1's service, the Librarian's routes, `POST /search`, and the other `tracelab_search` actions.

## Tests

| test | what it holds |
| --- | --- |
| `tests/test_search_ask.py` (10, new): `TestMcpContract` | the TestMissionVerbContract pattern (MCP Contract Guard). The npm client's source sends `POST /api/v1/search/ask` and the `ask` dispatch calls it. On the server, GET is 405 and a request with no credential is 401 |
| `TestAccess` | with an X-API-Key, the MCP's credential. A user who cannot read the project gets 403, and retrieval never runs. The owner gets an answer whose citations resolve, with retrieval scoped to that one project. A service principal gets 403. An unknown or soft-deleted project gets 404 |
| `TestAnswer` | the nothing-found result passes through and asserts nothing. An answer that cites nothing is refused, not shown. Eight malformed requests get 422, and retrieval never runs. Each paid call is one `search_ask` row for the caller with its model and tokens, and a cached answer adds none |
| `packages/tracelab-mcp/src/ask.test.ts` (12, new) | the tool posts the trimmed question with the API key and gives every citation the browser url of its chunk. An omitted budget is not sent. The refusal passes through as it is. A refused project surfaces as the API error, never as an empty answer. The same eight malformed inputs are rejected before any HTTP call |
| `packages/tracelab-mcp/src/index.test.ts`, `packages/tracelab-mcp/scripts/check-canonical-links.mjs` | 9 tools and 50 actions, with descriptors aligned to the action enums. The installed tarball, driven through a real stdio client against a fake API, posts the ask body and returns the citation urls and `project_url` |

Every backend test uses a fake retrieval service, never production Qdrant (learning #256). An autouse fixture makes the route module's own `get_rag_service` raise, so a parallel path to retrieval fails every test that reaches it.

## Mutation proof

`mutation_proof.py` breaks one ask rule at a time. After each break it runs three suites: the backend tests for the route, the MCP package's ask and cluster-surface tests, and the UI parity audit. Each mutation must turn exactly its expected checks red, and nothing else. The script refuses to start unless the target files match HEAD, restores each file after its run, and checks them against HEAD again at the end. It ran on `2d66c8f`, the PR's head, whose tree is identical to the merge commit's. All 13 runs came out as expected, each over 10 backend tests and 74 package tests (`mutation-proof-2d66c8f.json`, logs in `mutation-logs/`).

| run | what is disabled | red (the rest pass) |
| --- | --- | --- |
| baseline, before | nothing | none |
| M1 | the project is authorized for the caller before the service runs | the cannot-read test |
| M2 | a soft-deleted project is 404, like an unknown one | the 404 test |
| M3 | the route reaches retrieval only through `answer_question` | the four tests that reach retrieval: the owner's answer, nothing-found, cites-nothing and metering |
| M4 | each paid model call is recorded | the metering test |
| M5 | asks are metered under their own kind, apart from Librarian turns | the metering test |
| M6 | the answer budget is bounded 64–4000 | the request-rules test |
| M7 | a blank question is refused before retrieval | the request-rules test |
| M8 | the npm client sends POST, the verb the server serves | the backend contract test and the package's ask test |
| M9 | each citation gains the browser url of its chunk | the package's ask test |
| M10 | the MCP rejects a budget the API would refuse, before any request | the three budget cases (63, 4001, 600.5) |
| M11 | `ask` is a registered `tracelab_search` action | the cluster-surface test, and the parity audit, whose Librarian turn row now maps to a missing action |
| baseline, after | nothing | none |

The first run (`mutation-proof-2d66c8f-first-run.json`) reported M8–M11 as unexpected, though their red tests were exactly the predicted ones. vitest reports an empty file-level ancestor title, so each package test name gained a leading space and failed to match. The script now drops empty ancestors, and the rerun matched all 13. The first run is kept for the record.

## Before merge

- **Backend:** `tests/test_search_ask.py` 10 passed, and `ruff` 0.8.0 is clean on every changed Python file. The full suite ran as CI's `backend-suite` on PR #385. A local attempt at the same command was mis-scoped (see "Found along the way") and stopped.
- **MCP package:** it builds, and vitest passed 160 tests in 7 files. The installed-tarball check passed its 63 checks. `src` defines `__dirname` only in the ESM-safe way from the 1.0.1 fix.
- **Parity:** both parity audits exit 0 with no errors: 103 operations, 98 live, 9 tools, 50 actions, and 125 advertised arguments with no gaps. Their node tests pass, 4 of 4 and 7 of 7.
- **PR #385:** all ten checks green, including the eight required contexts. Merged at 23:44:19Z as `0bff859`.

## Release

| step | result |
| --- | --- |
| version, CHANGELOG and docs | in PR #385, merged as `0bff859` |
| tag | `tracelab-mcp-v2.1.0` (annotated) on `0bff859` |
| clean worktree of the tag: `npm ci`, build, `npm pack`, `npm publish --dry-run` | 24 files, 73,997 bytes, shasum `797087ef59c1c39b670fd49281fcc04725dfa36e` |
| publish, by Derek | 2026-09-23T23:58:41Z; `latest` is 2.1.0 |
| registry check | `npm view` gives shasum `797087ef…`, the dry run's sha512 integrity, and 24 files. The tarball the registry serves was downloaded and compared byte for byte with the dry-run tarball: identical |

## Production

| fact | value |
| --- | --- |
| merge commit | `0bff85992f16222ca253e0f7f1870b7cc84ada9f` (PR #385, squash; its tree is identical to the PR head `2d66c8f`) |
| Railway TraceLab (backend) | deployment `b4e6bae5-6316-4b5a-8b2e-3c80a553bf6a`, SUCCESS on `0bff859`; `/health` 200 |
| Railway frontend | deployment `5fc5c165-1831-4521-9e5d-a3c561a94c40`, SUCCESS on `0bff859` |
| main-push runs on `0bff859`, all success | Backend Tests `35935071875`, Backend Integration `35935071818`, Backend Lint `35935071838`, Frontend Checks `35935071821`, Frontend Production Build `35935071828`, MCP Package `35935071849`, Secret Scan `35935071817`, Post-Deploy Check `35935072079` |
| route probe | `POST /api/v1/search/ask` without a credential gives 401 and GET gives 405. The production OpenAPI lists the path with POST only |
| usage | the tarball run's answer wrote exactly one `search_ask` row at 23:48:34Z: caller attribution, TraceLab Research, gpt-5.1, 3,824 input and 74 output tokens (3,898 total), one request, status completed |

## The published package, end to end (DoD-1)

`npx-smoke.mjs` is MCP-5's smoke, extended for 2.1.0:

- it expects 50 actions and the `ask` surface;
- it asks TraceLab Research an answerable question, QA-1's third, about the TRACE-SHARE-58 report. It sends no budget, so the server default applies, as it does for an agent that sends none;
- it asks RAG-4's unsupported Kubernetes question with a 600-token budget, which must get the nothing-found result;
- it asks a project that does not exist, which must come back as the API's 404;
- it checks every generated link, the citation links included, for HTTP 200 on the public frontend. MCP-5's cap on the number of links is removed, so the ask links, which are collected last, are never cut off.

It used Derek's existing API key, passed only to the child process and never written to a receipt. Both reports and the log were scanned for it. The only writes are the usage rows a paid ask records.

| run | command | result |
| --- | --- | --- |
| before the publish, the local tarball, 23:48Z | `npx -y --package aquex-tracelab-mcp-2.1.0.tgz tracelab-mcp` (learning #245) | 19 of 19 (`tarball-smoke/`) |
| after the publish, 2026-09-24 04:34Z | `npx -y @aquex/tracelab-mcp@2.1.0` | 19 of 19 (`published-smoke/`) |

Both runs gave the same results:

- The server reported 2.1.0 with 9 tools and 50 actions, and its surface matched the parity manifest. One read-only call per tool succeeded.
- The Airtable question got one cited passage, "…is off by default out of the box". Its citation url is the frontend origin plus its `href`, which opens `/documents/<id>?chunk=<chunk_id>`.
- The Kubernetes question got "Nothing in this project answers that question." with no citations.
- The unknown project got `API Error (404)` with "Project not found."
- All 28 generated links, the citation's included, returned 200.

**The published run's answer came from the cache, so it was not metered.** Production still holds one `search_ask` row, the tarball run's. The published run asked the identical question 4 h 46 min later, inside the semantic answer cache's 24-hour lifetime, and no service variable overrides that lifetime. `answer_question` reports no paid usage on a cache hit. Production's log for that window shows the three asks (200, 200, 404) and no usage-write warning, and the same log carries the app's own INFO lines, so a warning would have shown. The latency agrees: 2.2 s, against 4.1 s for the paid call. The package does the same on both paths: the cache is on the server, and the package sends the same request and handles the same response either way. The paid path and its metering are covered by the tarball run and the backend tests.

## Criteria

| # | criterion | result |
| --- | --- | --- |
| 1 | `tracelab_search(action='ask')` with `project_id`, `question` and an optional `max_tokens`, calling QA-1's service and never a parallel path. The response carries the answer, citations with `document_id`, `chunk_id` and a canonical link, and the nothing-found flag | met. The argument names are the service's own, so nothing was renamed. M3 proves the one path. Each citation carries its `href` and its absolute `url` |
| 2 | citations resolve only to retrieved evidence, and empty retrieval returns the nothing-found result | met. The route adds no citation logic, and the service's rules pass through (the cites-nothing and nothing-found tests). On production the citation opened its chunk and the unsupported question was refused |
| 3 | the caller's RBAC scope applies as in the UI, proven through the MCP client in the TestMissionVerbContract pattern | met. A caller who cannot read the project gets 403 and retrieval is never called (M1). A service principal gets 403, and an unknown or deleted project gets 404 (M2). The client's verb is pinned on both sides (M8) |
| 4 | the parity manifest classifies the operation, both audits exit 0, and the README and `docs/mcp-tools.md` state the count | met. Every surface says 50 actions, and M11 shows the audit catches a missing action |
| 5 | released as 2.1.0 on Derek's publish, DoD-1 against the published package, and a receipt with the run and deployment ids | met. Published at 23:58:41Z, byte-identical to the dry run, and 19 of 19 on both the tarball and the published package |

## Found along the way

- **A metering test that could not fail.** Its first version compared the rows' kind with the `USAGE_KIND_SEARCH_ASK` constant itself, so changing the constant's value would still have passed. It now pins the literal `"search_ask"`, and M5 shows it goes red.
- **A local run of CI's backend command matched none of its 12 deselects.** Each line of the quarantine file ends in ` # reason`. CI strips that (`${line%% \#*}`), and the local attempt did not. The attempt was stopped, and CI's own `backend-suite` run on PR #385 is the full-suite result.
- **Railway's config-as-code files have a deadline.** Railway CLI 5.45.7 warns that `railway.json` is deprecated and that existing files keep working until 2026-12-01. Both services' deploy settings live in those files. The backend's start command is the one that runs `alembic upgrade head` before uvicorn, and the frontend's sets its build command and health check. It is recorded as a next-step: migrate, or confirm the services keep those settings, before that date.
