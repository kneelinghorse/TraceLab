# Changelog

All notable changes to `@aquex/tracelab-mcp` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

The next release is a **major** bump: the removals below break callers of the
1.2.0 action surface (decision #459, mission ACT-1).

### Removed

- `tracelab_home.attention`, `tracelab_home.inbox_summary` and
  `tracelab_home.inbox_list`; the API no longer serves `GET /home/attention`,
  `GET /inbox` or `GET /inbox/summary`.
- `tracelab_mission.views` (`GET /mission-views` was removed with saved mission
  views).
- The `view` and `reason` parameters of `tracelab_mission.list`; the API no
  longer accepts them.
- `attention` in the `tracelab_home.snapshot` response (the server dropped it
  together with `stalled_after_seconds` and the per-mission `reason`).

### Added

- `tracelab_project.create`: optional `workspace_id` (UUID), the Space to create
  in; omitted means the caller's personal Space. The server requires membership
  of the named Space (403), and owners and admins may name any existing Space
  (404 when missing). `tracelab_project.list` items and the `create` result now
  include `workspace_id` (PERSONAL-2, decision #533).
- `tracelab_home.activity`: `GET /activity` with optional `page` (1) and
  `page_size` (20, max 100). One recency-ordered stream of missions, reports and
  evidence; each item carries `type`, `id`, `title`, `subtitle`, `status`,
  `occurred_at`, `href`, a caller-relative `new` flag and a canonical `url`.
  Server `total` and `new_total` are preserved.
- `tracelab_home.activity_summary`: `GET /activity/summary` with `new_total`
  and `by_type` counts.
- `activity` in the `tracelab_home.snapshot` response, linked like the other
  sections.
- `tracelab_mission.list` accepts optional `sort` (`created_desc` default,
  `created_asc`, `updated_desc`, `updated_asc`), forwarded verbatim; omitting it
  keeps the request URL unchanged.
- Marking activity as viewed (`PUT /activity/viewed`) stays REST/UI-only, like
  the inbox mark-seen it replaced.

## [1.2.0] — 2026-09-15

### Added

- Eleven read actions: home snapshot/favorites, navigation, optional PEDR search,
  project/evidence detail, document list, collection documents/mission seed,
  and persisted mission logs/events (nine clusters total).
- UI parity manifest and AST audit enforced in package CI; traces live page
  consumers, retains dead client code, and rejects unclassified operations.
- Mission view, collection scope/pagination/instructions, evidence source/date
  filters, knowledge source/date filters, and explicit md/json/txt report export.
  Server totals, authored fields and legacy no-format export bytes are preserved.
- Collection list filters work on early Node 18 runtimes without
  `URLSearchParams.size`, preserving the package’s existing Node >=18 contract.
- Evidence filters match the deployed API: calendar dates, UUID source IDs,
  one report/document context at a time, and validated date order.
- PEDR exposes graph controls and diagnostics without changing plain knowledge
  retrieval. These changes ship in 1.2.0, the single Sprint 52 publish that decision #425 called for.

- Canonical browser navigation metadata on every entity response through one
  link helper, with an explicit `TRACELAB_FRONTEND_URL` override for custom
  deployments. Authored URLs, source provenance and export content are preserved.
- A real stdio MCP contract covering all 40 source actions, HTTP verbs, authentication,
  canonical links and content preservation. CI installs an `npm pack` tarball
  in a clean directory and exercises its actual entrypoint.
- MCP-2: six non-destructive actions on research objects that mirror the exact
  web routes: `tracelab_mission_execution` `cancel` (the only status an agent
  may write, enforced by a literal schema) and `promote_report`,
  `tracelab_document` `process`, `tracelab_collection` `update` and
  `add_document`, and `tracelab_report` `update`.
- MCP-2: Sprint 52 surface reads: `tracelab_project` `neighborhood` (canonical
  links for all six node types), `tracelab_home` `attention`, `inbox_summary`
  and `inbox_list`, `tracelab_mission` `views`, and a repeatable `reason`
  filter on `tracelab_mission` `list` that leaves the plain request URL
  byte-identical. Nine clusters now expose 51 actions; the stdio contract
  asserts the count and every new verb, path and query string.

### Changed

- Bumped the public package to 1.2.0: nine clusters now expose 51 actions (up
  from 40 in 1.1.1), an additive public API change released once after every
  Sprint 52 MCP change landed (decision #425).
- Upload `next_steps` now name `tracelab_document(action="process")` and
  `tracelab_search(action="knowledge")` instead of a REST path and the retired
  `search_knowledge` tool.
- The UI parity manifest dispositions every remaining gap: eleven rows closed by
  MCP-2 source actions, and per-user acknowledgements (result review, inbox
  mark-seen, favorites, saved searches, saved views) plus every DELETE route
  recorded as REST/UI-only by decision #426 (no delete approval recorded).

## [1.1.1] — 2026-08-21

### Added

- **Canonical evidence-source metadata.** Evidence entry responses now expose
  the backend-owned `source_id` and `source_sighting_count` fields so agents can
  recognize repeated citations of the same normalized project source. The MCP
  keeps serializing evidence responses wholesale, and its full-response
  contract fixture now requires both fields.

### Changed

- **Search-before-research boundary.** Documented that raw findings remain in
  `tracelab_evidence(action="search")`, while `tracelab_search` remains a
  document-chunk search. `tracelab_evidence(action="promote",
  target="document")` is the explicit path into ingestion, Qdrant, and
  PEDR/preflight. No MCP input schema or action changed.
- Bumped the public package to 1.1.1 for the additive evidence response fields.

### Fixed

- Corrected MCP setup examples to use the production FastAPI origin
  (`https://api.tracelab.aquex.ai`) without an `/api/v1` suffix, and added the
  supported Codex stdio configuration. TraceLab does not expose an SSE MCP
  endpoint at `https://aquex.ai/mcp`.

## [1.1.0] — 2026-08-20

### Added

- **Evidence Ledger MCP surface.** Added the eighth action-clustered tool,
  `tracelab_evidence`, with `capture`, `note`, `list`, `search`, and
  `promote` actions. It uses the authenticated TraceLab REST API to batch
  capture sourced findings, upsert keyed working notes, reuse project-scoped
  evidence across sessions, and promote a session to a report or document.
- **Evidence contract guards.** The package now locks tool-descriptor,
  action-enum, and real CallTool-dispatch parity. Handler-level tests assert
  each evidence action's exact HTTP verb, encoded URL, request body, shared
  API-key forwarding, and full unprojected REST response round-trip.
- **Boundary-safe evidence input.** Required evidence text and tags now mirror
  backend trimming/nonblank validation. Dot-only note keys are rejected before
  WHATWG URL normalization can turn them into navigation, and dispatcher
  lookups ignore inherited object-prototype names.

### Changed

- Bumped the public package to 1.1.0 because the eighth visible MCP tool is an
  additive public API change.

## [1.0.2] — 2026-08-20

### Fixed

- **serverInfo version identity.** The MCP handshake hardcoded
  `version: '1.0.0'` in `serverInfo`, so 1.0.1 installs still introduced
  themselves as 1.0.0. The server now reads the version from
  `package.json` at startup via the same `readPackageVersion()` helper
  the device-code User-Agent already uses — one source of truth, no
  literal to forget on the next bump.

### Added

- **Cross-service lifecycle fields in `tracelab_mission_execution`
  `action: "status"`.** The status projection now passes through
  `deepsearch_job_id`, `lease_expires_at`, `result_document_ids`, and
  `result_report_id` under their REST names (matching
  `GET /api/v1/missions/{id}/status`). The REST API already returned
  them; the MCP projection stripped them, leaving agents unable to
  confirm DeepSearch job identity, lease deadlines, or materialized
  result artifacts for cross-service lifecycle acceptance.

## [1.0.1] — 2026-04-30

### Added (retroactive addendum)

Documented after the fact: the 1.0.1 tarball also carried the post-tag
mission-authoring changes from TraceLab commit `21271b5`.

- **Mission-authoring passthrough (T40.1/T41.2).** The 12 authoring
  columns — `background`, `focus`, `references`, `required_entities`,
  `excluded_entities`, `expected_output_schema`, `coverage_thresholds`,
  `validation_thresholds`, `deliverable_format`, `max_loops`,
  `min_loops`, `constraints` — survive the packaged flow: accepted on
  mission create/update and returned by `action: "get"` instead of
  being stripped by the hand-rolled response shape.
- **Lease-era status typing.** `MissionStatusResponse` in the API client
  gained the lease-lifecycle fields (`deepsearch_job_id`,
  `deepsearch_attempt_count`, `lease_expires_at`,
  `result_document_ids`, `result_report_id`, materialization state,
  `search_ready`) matching the post-lease REST status endpoint.

Hotfix release. The 1.0.0 build crashed on startup for every fresh
install. Anyone who ran `npx -y @aquex/tracelab-mcp` or
`npm install -g @aquex/tracelab-mcp` against the 1.0.0 tarball got an
immediate `ReferenceError: __dirname is not defined` before any
device-code prompt could appear.

### Fixed

- **ESM/CJS mismatch in `auth/device-code.ts`.** The package ships as
  ESM (`"type": "module"`) but `readPackageVersion()` referenced the
  CommonJS-only `__dirname` global. Replaced with the standard ESM
  derivation (`fileURLToPath(import.meta.url)`). The User-Agent string
  sent to `/api/v1/auth/device/code` once again carries the correct
  package version.

Local smoke test against `https://api.tracelab.aquex.ai` confirmed the full
device-code flow now completes: prompt prints → user approves → key
mints → MCP server starts → authenticated `/missions` call returns.

## [1.0.0] — 2026-04-29

First public release on npm. The package shipped previously inside the
TraceLab repo under the un-published name `@tracelab/mcp-server`; v1.0.0
re-publishes it as the public `@aquex/tracelab-mcp` on the post-T42.4
modernized auth base.

### Added

- **RFC 8628 device-code login.** First launch on a fresh machine prints a
  short user code + URL to stderr; the user approves on the TraceLab
  `/device` page and the MCP picks up a freshly minted API key within
  seconds. Persists at `~/.config/tracelab-mcp/credentials.json`
  (`chmod 600`). Replaces the prior hand-paste-an-API-key install UX.
- **Credential store** with stored-vs-effective `TRACELAB_API_URL`
  comparison; switching between deployments forces a fresh login per
  environment instead of leaking credentials across them.
- **Action-clustered tool surface.** Seven tools — `tracelab_search`,
  `tracelab_project`, `tracelab_collection`, `tracelab_report`,
  `tracelab_document`, `tracelab_mission`, `tracelab_mission_execution`
  — each dispatched by an `action` parameter. Replaces the earlier flat
  ~24-tool layout.

### Auth resolution order

1. `TRACELAB_TOKEN` env var (JWT).
2. `TRACELAB_API_KEY` env var (`tl_*` key).
3. Stored credential, only if its `apiBaseUrl` matches the effective URL.
4. Interactive device-code flow.

### Compatibility

- Node ≥ 18.
- Targets the TraceLab FastAPI service (any deployment that ships
  alembic migrations through 029).
- Tool input/output shapes match `cmos/contracts/mission-authoring-contract.md`
  at the pin recorded in the TraceLab repo.

### Migration

If you used the un-published `@tracelab/mcp-server` from a local checkout,
swap the install line to `npm install -g @aquex/tracelab-mcp` (or `npx
@aquex/tracelab-mcp`). Tool names, schemas, and behavior are unchanged.
Calls against legacy flat tool names continue to return a friendly
migration error pointing at the cluster equivalent.

[1.2.0]: https://github.com/kneelinghorse/TraceLab/releases/tag/tracelab-mcp-v1.2.0
[1.1.1]: https://github.com/kneelinghorse/TraceLab/releases/tag/tracelab-mcp-v1.1.1
[1.1.0]: https://github.com/kneelinghorse/TraceLab/releases/tag/tracelab-mcp-v1.1.0
[1.0.0]: https://github.com/kneelinghorse/TraceLab/releases/tag/tracelab-mcp-v1.0.0
