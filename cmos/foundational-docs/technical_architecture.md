# TraceLab Technical Architecture (as built)

As of main `bf750cb70550a33f179b0ca4c2518454122ff87c` (2026-09-15, end of the Sprint 52 build). This document describes the
platform that runs today; it follows `cmos/foundational-docs/tech_arch_template.md` and links out
rather than duplicating contracts. Intent and sprint history are in
`cmos/foundational-docs/roadmap-sprints-50-53-ux-overhaul.md`; CMOS holds mission status.

## System overview

| Component | Where | Notes |
| --- | --- | --- |
| API | `app/` (FastAPI, Python 3.11) | Railway service `TraceLab`, `https://api.tracelab.aquex.ai` |
| Web UI | `frontend/` (Next.js 16 pages router) | Railway service `frontend`, `https://tracelab.aquex.ai`; see `docs/frontend_architecture.md` |
| Relational store | PostgreSQL 15 | Railway service; schema owned by Alembic (head `049_recent_activity`) |
| Vector store | Qdrant | Railway service; PEDR retrieval layers |
| Research worker | DeepSearch (separate repository) | Railway service `worker-service deepSearch`; reached only through the mission lifecycle |
| Agent surface | `packages/tracelab-mcp` | Local stdio MCP server published as `@aquex/tracelab-mcp` |
| Planning workbench | `cmos/` | Missions, sessions, decisions and receipts; never application code |

Every merge to `main` rebuilds both Railway services, so each mission records both deployment ids
after SUCCESS and only then runs its production checks.

## Application layout (hexagonal)

- `app/api/v1/` routers stay thin and call services. Mounted routers include auth and device-code
  auth, projects, documents, collections and collection context, reports, missions, mission events,
  home, activity, graph neighborhood, relationships, navigation search, evidence, search,
  retrieval, PEDR search/preflight/related, facets, saved searches, search history, synthesize, quality
  and automated quality, admin,
  admin users, spaces, project admin, corrections, decision links, monitoring, redaction, cache,
  Qdrant admin, DeepSearch and webhooks, and health.
- `app/services/` holds orchestration (mission service, webhook handler, result materialization,
  document policy, evidence scope, home, activity, report promotion, the vendored
  DeepSearch contract compiler under `app/services/contract_compiler/`).
- `app/ports/` are `typing.Protocol` contracts; `app/adapters/` implement them (SQLAlchemy
  repositories, OpenAI and Qdrant adapters); `app/dependencies.py` is the composition root wired
  through `FastAPI Depends()`. ADRs 001–005 in `docs/adr/` record these choices.
- `app/core/` holds config, database, security, authorization, rate limiting and the in-process
  mission event bus; `app/models/` and `app/schemas/` hold SQLAlchemy models and Pydantic contracts.
- `app/mcp_server/` is the Python MCP kept for local development and serializer parity; it is
  production-dark. The supported agent surface is the TypeScript package below.

## Authentication and authorization

- Authentication is router-level: `protected_dependencies = [Depends(require_authenticated_user)]`
  in `app/main.py` guards every mounted router except health, which is unauthenticated.
  `require_authenticated_user` accepts a JWT bearer or an `X-API-Key` and rejects service principals
  (`role=service`) unconditionally; explicit service routes use their own dependency.
- Human credentials come from password login, invite codes, personal API keys and the RFC 8628
  device-code flow (`/device`), which the MCP package uses on first launch.
- RBAC is live in production behind the environment-driven `RBAC_ENABLED` (the code default is
  `False`, so the deploy configuration is the guard). Access is granted by Space membership
  (`workspaces`, `space_members`) with downward inheritance to child rows through `project_id`, plus
  owner and admin allow paths.
- `app/core/authorization.py` is the single policy: `authorize` and `authorize_or_403` for per-id
  reads and writes, `accessible_filter` for list queries (applied before count and pagination),
  `accessible_project_ids` for non-relational stores such as Qdrant, and `POLICY_VERSION = "1.1"`.
  Version 1.1 (SEC-2, decision #424) keeps a project's owner able to read every document in that
  project without Space membership; `app/services/document_policy.py` is the shared document read
  policy used by document lists, collection detail and export, reports and synthesis.
- Onboarding `POST /api/v1/documents` authorizes the parent project before any filesystem access or
  write (SEC-1, decision #423).
- `scripts/rbac_verify.py` is the live role-by-route verification harness (anonymous-401 sweeps,
  per-id and alternate-route matrices); `tests/test_rbac_verify_harness.py` and
  `tests/integration/test_e2e_rbac_live.py` keep its route inventory in lockstep with the mounted app.
- Rate limiting keys on the rightmost trusted proxy hop (`rate_limit_trusted_proxy_hops`, default 1)
  because the API is reached directly at the Railway edge.

## Data model and migrations

- Core tables: `projects`, `documents`, `document_chunks`, `document_processing_statuses`, `tags` and
  `document_tags`, `insights` and `insight_sources`, `missions` and `mission_logs`, `quality_checks`,
  `reports` and `report_sources`, `collections`, `collection_items` and `collection_documents`,
  `ingestion_jobs`, `idempotency_records`, `api_keys`, `users`, `invite_codes`,
  `device_authorization_grants`, `workspaces`, `space_members`, `project_tags`, `sync_states`,
  `saved_searches`, `search_history`, `synthesis_cache`, `graph_edges`.
- Evidence ledger (`app/models/evidence_ledger.py`): `ledger_sources`, `ledger_entries`,
  `ledger_notes`, `deepsearch_ledger_batches` and `deepsearch_evidence_outbox`; the contract is
  `cmos/contracts/evidence-ledger-contract.md`.
- Per-user operator state: `user_favorites` and `user_item_views` (one row per opened mission, report
  or evidence group, keyed by type and id and stamped with the revision that was viewed; migration
  `049_recent_activity` replaced `user_mission_reviews`, `user_saved_views` and `user_inbox_state`).
- Missions carry the DeepSearch lease boundary (`deepsearch_lease_*`, `deepsearch_attempt_count`,
  `deepsearch_result_key`, migration `039_deepsearch_lease_v1`) and the twelve compiler
  fields mapped in `cmos/contracts/mission-authoring-contract.md`.
- **Alembic is the sole schema authority.** The runtime no longer calls `create_all`, and
  `tests/integration/test_migration_coverage.py` proves a migrations-only database contains every
  model table. Revision ids must stay at or under 32 characters, the width of
  `alembic_version.version_num`. The current head is `049_recent_activity`.

## Retrieval and search

- Documents are parsed, redacted, chunked and embedded through the ingestion pipeline
  (`docs/document-processing.md`, `docs/ingestion_pipeline_developer_guide.md`); chunks live in
  PostgreSQL and vectors in Qdrant.
- `GET /api/v1/documents/{id}` returns metadata, chunk stats, a 500-character preview, the
  provenance columns (`source_report_id`, `source_mission_id`, `source_origin`) and caller-readable
  `links` to the source report and mission; it no longer serializes `content` or `raw_content`.
  `GET /api/v1/documents/{id}/content` serves the extracted text on demand under the same
  authorization (DOCV-1, decision #459); the original bytes stay behind `/download`. Evidence
  detail links flag the capturing mission's result report with `mission_result`, so the evidence
  page offers the same Open report link for it.
- PEDR, Protocol-Enhanced Deep Research (`docs/architecture/PEDR-search.md`, `docs/pedr-search.md`),
  fuses lexical and semantic retrieval layers plus optional graph expansion through Reciprocal Rank
  Fusion; `POST /api/v1/pedr/search` and the plain
  `POST /api/v1/retrieval/search` are both scoped by `accessible_project_ids`. Facets, hybrid search,
  the evidence browser and the relationship neighborhood (`GET /api/v1/graph/neighborhood`, computed
  from the live relational tables; it does not read `graph_edges`) are RBAC-scoped reads.
- Operator aggregates (`/home`, `/activity`, `/activity/summary`, `/navigation/search`,
  `/graph/neighborhood`, collection context and admin stats) are computed per request with server-side
  totals, answer with `Cache-Control: private, no-store`, and are never cached, so a revoked membership takes effect on
  the next request (learning #167). Home and the activity stream share one ledger scope in
  `app/services/evidence_scope.py`; the stream orders by when each item last happened
  (`app/adapters/repositories/sqlalchemy_activity_repo.py`) and status never affects order (decision #459).

## Missions and DeepSearch

- Lifecycle: `draft → queued → in_progress → completed | blocked | validation_failed | cancelled`.
  `POST /missions/{id}/submit` queues a mission; the DeepSearch worker claims it under a fenced
  lease, writes terminal state directly to the database, and reports through the HMAC-signed webhook
  (`app/api/v1/webhooks.py`, `app/services/webhook_handler.py`, idempotent on replays). Result
  materialization turns reports and markdown into searchable documents.
- The contract the worker receives is compiled by the vendored compiler
  (`cmos/contracts/deepsearch-compiler-vendor.md` describes the resync ritual); `GET
  /missions/{id}/contract-preview` compiles without spending a run.
- `app/core/mission_events.py` is an in-memory, per-process ring buffer; `GET /missions/events/recent`
  and the SSE stream are snapshots, not delivery guarantees. Operator surfaces therefore poll: the
  activity stream reads rows, so completions written directly by the worker appear on the next poll.
- Per-user acknowledgements (viewed marks, favorites and saved searches) are explicit human actions
  and stay REST/UI-only (decision #426). Viewed marks are per user and per item revision, so a changed
  item becomes new again (decision #459 replaced the review and inbox models of decisions #395 and #409).

## MCP package

- `packages/tracelab-mcp` is the supported agent surface: a stdio server exposing nine
  action-clustered tools (`tracelab_search`, `tracelab_project`, `tracelab_collection`,
  `tracelab_report`, `tracelab_document`, `tracelab_mission`, `tracelab_mission_execution`,
  `tracelab_evidence`, `tracelab_home`) with 51 actions in source at version 1.2.0 (`docs/mcp-tools.md`,
  `packages/tracelab-mcp/README.md`). The published npm version is 1.1.1 until the
  Sprint 52 single publish (MCP-3, decision #425) runs; `npm view @aquex/tracelab-mcp version` is
  authoritative for what installs.
- Generated browser links go through `packages/tracelab-mcp/src/canonical-link.ts` only; authored
  URLs and content are preserved byte for byte.
- `cmos/contracts/mcp-parity-manifest.json` classifies every frontend API operation
  (covered, closed by MCP-1 or MCP-2, REST/UI-only by design, or dead client code);
  `scripts/mcp_parity_audit.mjs` rebuilds the inventory from the TypeScript AST and fails on any
  unclassified operation. Deletes stay REST/UI-only until approved.
- Contract guard: any MCP surface change needs a regression test through the real stdio client
  (`packages/tracelab-mcp/scripts/check-canonical-links.mjs`, also run from an installed tarball).

## CI and deployment

- Required contexts on `main` (CI-5, `.github/ci/README.md`): `backend-suite`, `vitest`,
  `type-check`, `ruff-diff`, `build-frontend-production`, `Secret Scan`, `backend-integration`
  and `lint`. `mcp-package` is advisory and follows the five-run promotion ratchet. There is no
  formatting gate and no Python type gate; `ruff check` runs on changed Python files only.
- `backend-suite` runs every non-integration test with exactly twelve quarantined deselections
  (`.github/ci/backend-quarantine.txt`); `backend-integration` runs `tests/integration` on a
  PostgreSQL 15 testcontainer; `build-frontend-production` builds, gates tokens and runs Playwright
  against `next start`.
- Railway hosts the API, the frontend, PostgreSQL, Qdrant and the DeepSearch worker in one project;
  the API is reached directly at the Railway edge. Each mission's receipt under `cmos/reports/sprint-N/` cites the
  post-merge main push run ids and both deployment ids (learnings #176 and #177).

## Security notes

- No secrets in logs or receipts; `scripts/check_no_credential_literals.py` runs as the Secret Scan
  context. Database access goes through SQLAlchemy with bound parameters.
- Authentication and CORS guidance: `docs/authentication.md`, `docs/auth_and_cors_guidance.md`;
  data protection: `docs/data-protection-audit.md`.

## Historical note

The original 2025-11-08 version of this file was a pre-build proposal: a Presidio redaction
pipeline, a semantic cache, a tiered LLM strategy, a monthly cost estimate and an unversioned
`/api/*` endpoint list. It is preserved in git history
(`git show b9e3ee9:cmos/foundational-docs/technical_architecture.md`) and summarized in
`cmos/reports/white-papers/tracelab-technical-architecture.md`; none of it is a description of the
running system.
