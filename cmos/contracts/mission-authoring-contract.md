# Mission-Authoring Boundary Contract

Single source of truth for every mission-authoring field's full round-trip:
**MCP param → Pydantic schema → DB column → REST response → DS worker
visibility.** When DeepSearch's worker SELECT or TraceLab's create/update
surface gains/loses/renames a field, this doc is the one place to update.

Origin: DeepSearch asked for this verbatim in message
`3cf143ee-8cb9-43ac-bc22-f0029fcdd3ae` (2026-04-27): *"we'd like a
documented contract for which top-level params round-trip end-to-end so
this stops being something we discover via paid smoke regressions."*

## Commit pins (versions for which this contract is valid)

| Project | Commit | Branch | Date |
| --- | --- | --- | --- |
| TraceLab | sprint-49 T49.1 working tree (lease-v2 runtime boundary in migration 039; commit pending) | `RBAC-updates` | 2026-08-14 |
| DeepSearch.alpha | `b7009c6` + uncommitted Sprint 91 lease-v2 working tree (evidence pending) | `contract-driven-pipeline` | 2026-08-14 |

The vendored DS contract compiler at `app/services/contract_compiler/` is
pinned separately to DS commit `24e8810`; see
`cmos/contracts/deepsearch-compiler-vendor.md` for that ritual.
Contract-preview responses expose `contract_version`, `compiler_revision`, and
`fidelity`; the current value is `structural_only` because the pinned 1.0
compiler is intentionally held until DeepSearch publishes a deterministic 1.1
manifest and golden fixtures.

## How to use this doc

- **Adding a field to mission authoring?** Add a row to the table below
  AND update both vendor docs if applicable.
- **DS worker SELECT changed?** Update the "DS worker SELECT" column.
- **A field stopped round-tripping in production?** Use this doc to
  bisect which layer is broken. The T41.2 incident — MCP `_serialize_mission`
  silently dropped 12 T40.1 fields — would have been caught here if this
  doc had existed and a CI check enforced parity.

## MCP tool surface (T41.7 foundation; LEDGER-1 extension)

The TS MCP package exposes **8 action-clustered tools**, not the prior
~24 flat tools. LEDGER-1 added `tracelab_evidence` without changing the
mission-authoring calls documented here; its separate field/verb contract is
[`evidence-ledger-contract.md`](evidence-ledger-contract.md). The MCP-param
column below uses the legacy names
(`create_mission`, `get_mission`, …) for readability — the over-the-wire
calls now go through:

| Legacy tool | New cluster call | New action |
| --- | --- | --- |
| `create_mission` | `tracelab_mission` | `create` |
| `list_missions` | `tracelab_mission` | `list` |
| `get_mission` | `tracelab_mission` | `get` |
| `update_mission` | `tracelab_mission` | `update` |
| `submit_mission` | `tracelab_mission_execution` | `submit` |
| `get_mission_status` | `tracelab_mission_execution` | `status` |
| `preview_mission_contract` | `tracelab_mission_execution` | `preview` |

Hard-cut migration — legacy names are not registered as tools but the
dispatcher returns a friendly error pointing to the cluster + action
target. Full mapping for the rest of the legacy surface (project, collection,
report, document, search) is in
`packages/tracelab-mcp/src/index.ts::LEGACY_TO_CLUSTER`.

Field shapes are unchanged: every parameter listed below is passed as a
top-level key alongside `action` in the cluster call. The Pydantic /
DB / REST / DS-worker columns are unaffected by the cluster refactor.

## Top-level field map

Listed in MCP `create_mission` argument order — for clusters this means
`tracelab_mission(action="create", ...)`. Every field is documented in
both create and update flows unless noted.

### Identity & core

| MCP param | MCP type | Required (create) | Pydantic field | DB column | DB type | REST response field | DS worker SELECT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `mission_id` | string (1-50 chars) | ✓ | `MissionCreate.mission_id` | `mission_id` | `String(50)` UNIQUE | `mission_id` | ✓ |
| `title` | string (3-255 chars) | ✓ | `MissionCreate.title` | `title` | `String(255)` | `title` | ✓ |
| `objective` | string (≥10 chars) | ✓ | `MissionCreate.objective` | `objective` | `Text` | `objective` | ✓ |
| `success_criteria` | array of strings (min 1) | ✓ | `MissionCreate.success_criteria` | `success_criteria` | `CrossDBJSON` (JSONB on Postgres) | `success_criteria` | ✓ |
| `project_id` | UUID string | **✓ (T41.6)** | `MissionCreate.project_id` (UUID) | `project_id` | `GUID` FK→projects.id | `project_id` | ✗ — DS resolves project context via TL API, not SELECT |

### Authoring fields (T40.1) — DeepSearch contract compiler input

| MCP param | MCP type | Pydantic field | DB column | DB type | REST response field | DS worker SELECT |
| --- | --- | --- | --- | --- | --- | --- |
| `background` | string | `MissionCreate.background` | `background` | `Text` nullable | `background` | ✗ |
| `focus` | string | `MissionCreate.focus` | `focus` | `Text` nullable | `focus` | ✗ |
| `references` | array of `{title}` objects | `MissionCreate.references` | `"references"` | `CrossDBJSON` nullable | `references` | ✗ |
| `required_entities` | array of strings | `MissionCreate.required_entities` | `required_entities` | `CrossDBJSON` nullable | `required_entities` | **✓** (added in DS S59.1) |
| `excluded_entities` | array of strings | `MissionCreate.excluded_entities` | `excluded_entities` | `CrossDBJSON` nullable | `excluded_entities` | **✓** (added in DS S59.1) |
| `expected_output_schema` | object (DS OutputSchema) | `MissionCreate.expected_output_schema` | `expected_output_schema` | `CrossDBJSON` nullable | `expected_output_schema` | ✗ |
| `coverage_thresholds` | object (string→number) | `MissionCreate.coverage_thresholds` | `coverage_thresholds` | `CrossDBJSON` nullable | `coverage_thresholds` | ✗ |
| `validation_thresholds` | object (string→number) | `MissionCreate.validation_thresholds` | `validation_thresholds` | `CrossDBJSON` nullable | `validation_thresholds` | ✗ |
| `deliverable_format` | string | `MissionCreate.deliverable_format` | `deliverable_format` | `Text` nullable | `deliverable_format` | ✗ |
| `max_loops` | integer ≥1 | `MissionCreate.max_loops` | `max_loops` | `Integer` nullable | `max_loops` | ✗ |
| `min_loops` | integer ≥1 | `MissionCreate.min_loops` | `min_loops` | `Integer` nullable | `min_loops` | ✗ |
| `constraints` | array of strings | `MissionCreate.constraints` | `constraints` | `CrossDBJSON` nullable | `constraints` (with fallback) | ✗ |

**Constraints fallback behavior:** Pre-T40.1 missions stored constraints
inside `context['constraints']`. The REST `_to_response`, MCP
`_serialize_mission`, and `build_mission_context_from_mission` all check
`mission.constraints` first; if empty/null they fall back to
`mission.context['constraints']`. New writes always go to the column.

### Operational / output fields (not authoring)

| MCP param | Pydantic field | DB column | DS worker SELECT |
| --- | --- | --- | --- |
| `context` (deprecated for new authoring) | `MissionCreate.context` | `context` | ✓ |
| `deliverables` | `MissionCreate.deliverables` | `deliverables` | ✓ |
| `research_phases` | `MissionCreate.research_phases` | `research_phases` | ✓ |
| `tags` | `MissionCreate.tags` | `tags` | ✗ |
| `metadata` (column: `mission_metadata`) | `MissionCreate.metadata` | `mission_metadata` | ✗ |
| `status` | `MissionCreate.status` | `status` | ✓ (filter only) |
| `created_by` | `MissionCreate.created_by` | `created_by` | ✗ |

`queued_at`, `started_at`, `completed_at`, `deepsearch_job_id`,
`execution_metadata`, `result_document_ids`, `result_report_id`,
`result_markdown`, `result_protocol`, `error_message`, `created_at`,
`updated_at` are server-managed lifecycle fields — present in the REST
response and MCP serializers but not in `create_mission`/`update_mission`
input.

`owner_id` and `workspace_id` (added to the `missions` table in Alembic
migration `030_add_owner_workspace_columns`, Sprint 43 T43.2) are internal
ownership/tenancy columns: nullable, server-set, never accepted as
`create_mission`/`update_mission` input, absent from the MCP/REST authoring
surface, and NOT in the DS worker SELECT. As of Sprint 43 nothing reads them
(zero enforcement); they back the RBAC ownership model wired up in later
sprints.

### DeepSearch lease fields (internal operational boundary)

Alembic migration `039_deepsearch_lease_v1` makes the worker's fenced-claim
schema reproducible from a clean TraceLab checkout. These fields are never
accepted from mission authors. Opaque ownership/result proofs remain absent
from REST and MCP; the authorized lightweight status surface exposes only the
attempt count and lease expiry needed to diagnose a stranded run.

| DB column | PostgreSQL type/default | DeepSearch use | Public REST/MCP |
| --- | --- | --- | --- |
| `deepsearch_lease_owner` | `text` nullable | claim, heartbeat, terminal fencing | ✗ |
| `deepsearch_lease_token` | `text` nullable; unique while non-null | opaque per-attempt ownership proof | ✗ |
| `deepsearch_leased_at` | `timestamptz` nullable | claim audit | ✗ |
| `deepsearch_heartbeat_at` | `timestamptz` nullable | liveness/recovery | ✗ |
| `deepsearch_lease_expires_at` | `timestamptz` nullable | claim/recovery/terminal fencing | authorized status telemetry only |
| `deepsearch_attempt_count` | `integer NOT NULL DEFAULT 0` | bounded retry and stale-token fencing | authorized status telemetry only |
| `deepsearch_result_key` | `text` nullable; unique while non-null | idempotent terminal persistence | ✗ |

Runtime contract identifier: `tracelab-missions-lease-v2`. The Alembic revision
name remains `039_deepsearch_lease_v1` to preserve the immutable migration
chain; its converged DDL implements the lease-v2 nullability, defaults, index
predicates, and global claim policy. The frozen claim policy is
global across non-orphan projects, matching audited DeepSearch `b7009c6`
`CLAIM_MISSION_SQL`; RBAC controls human visibility, not worker dispatch. The
claim index is therefore `(status, deepsearch_lease_expires_at, queued_at)` and
must not lead with `project_id`. DeepSearch must remove the stale
`TRACELAB_PROJECT_ID`-scoped wording from its S87 coordination report before
deployment.

One TraceLab mission represents one fenced DeepSearch execution. Only pristine
`draft` missions may be submitted; terminal missions are immutable and another
run requires a new mission ID. This prevents an exhausted attempt counter or an
old result link from contaminating a later run. A terminal database row is
authoritative when processing the current minimal HMAC completion receipt.
DeepSearch's current uncommitted Sprint 91 working tree persists
`deepsearch_job_id` alongside `deepsearch_result_key` in each fenced terminal
write. Treat that correlation as implemented-but-unverified until DeepSearch
returns a commit SHA and passing boundary evidence. The unpaid deployed smoke
must prove the minimal signed receipt's `job_id` exactly matches the persisted
terminal row; any future multi-run/versioned mission design must retain an
equivalent fenced correlation proof.

Lease-v2 rollout is deliberately ordered:

1. Drain and stop every legacy/unfenced DeepSearch worker; verify no old worker
   can still claim or finish a mission.
2. Deploy TraceLab migration `038_backfill_mission_report`, then
   `039_deepsearch_lease_v1`. Migration 039 intentionally makes legacy
   `in_progress` rows without a lease token immediately reclaimable.
3. Verify the seven lease columns, nullable terminal-clear fields, partial
   uniqueness predicates, and global claim index in the deployed database.
4. Only then start the lease-v2 DeepSearch worker and exercise an unpaid
   create → claim → heartbeat → terminal receipt smoke. Never overlap old and
   lease-v2 workers; overlap can execute a tokenless legacy mission twice.
5. Paid CAT dispatch remains a separate explicit authorization after the
   deployed lifecycle and artifact-search convergence checks pass.

The completion receipt uses one rotated HMAC value under intentionally inverse
environment names: TraceLab reads `DEEPSEARCH_TRACELAB_SERVICE_SECRET`, while
DeepSearch signs with `TRACELAB_DEEPSEARCH_SERVICE_SECRET`. Both deployed
services must hold the exact same value. `DEEPSEARCH_WEBHOOK_SECRET` is a
TraceLab-only transitional fallback and must not be the steady-state production
configuration. TraceLab fails closed on a missing production secret. Before
worker acceptance, exercise an unpaid live receipt and prove both signature
validation and persisted `job_id` correlation; a local unit test or merely
setting one side is insufficient. Unsigned callbacks are allowed only in an
explicit `test`/`testing` environment or local `development`/`dev`/`local`
mode with `DEBUG=true`; missing `ENVIRONMENT` plus the default `DEBUG=false`
therefore fails closed.

TraceLab's public `GET /api/v1/health` response exposes
`deepsearch_receipt_receiver_configured`. This boolean proves only that the
TraceLab receiver resolved a canonical or transitional secret; it cannot prove
value equality with the worker. DeepSearch acceptance preflight must fail
closed when the field is false, missing, malformed, or unreachable, then still
require a signed live receipt with persisted `job_id` correlation.

TraceLab owns the durable fallback when DeepSearch exhausts receipt retries or
crashes after its terminal database write. The production rollout is not
convergent until a separate Railway scheduled service is live with:

- start command `python -m app.cli.reconcile_mission_results --limit 100`;
- schedule `*/15 * * * *` (UTC), using the same `DATABASE_URL`, embedding, and
  Qdrant configuration as the API service;
- no public domain and no long-running process—the command must exit after one
  bounded pass;
- an alert on non-zero exit and on absence of a successful run for 30 minutes.

Immediately after migrations and before worker acceptance, run the targeted
backfill
`python -m app.cli.reconcile_mission_results --mission-id pedr-retrieval-evaluation-R001`,
then repeat `--limit 500` passes until output reports `eligible: 0`. DeepSearch
must continue retrying TraceLab receipt `5xx` responses; a durable DS receipt
outbox can later replace this fallback, but the current in-memory retry queue
cannot. The cron service, one-time backfill evidence, and alert are TraceLab
deployment responsibilities.

### Update-only fields

| MCP param | Pydantic field | Notes |
| --- | --- | --- |
| `project_id` (T41.5) | `MissionUpdate.project_id` | Re-parents the mission. Route validates target project exists (404 if not). Pre-T41.5 was immutable after create. |

`mission_id`, `id`, `created_at` are immutable. Pydantic silently drops
them from `MissionUpdate` payloads.

## Postgres reserved-word quoting

`references` is a Postgres reserved word. SQLAlchemy quotes it
automatically when emitting SQL. Hand-written SQL (DS worker, raw
Alembic migrations, ad-hoc psql) MUST quote it as `"references"`. The DS
worker's CLAIM_MISSION_SQL doesn't currently SELECT `references` so the
quoting requirement isn't yet exercised on the DS side, but adding it
later requires the quoted form. TraceLab's existing migration 027
demonstrates the pattern.

## Two MCP serialization surfaces (T41.4 critical learning)

TraceLab has TWO independent MCP-side serialization paths:

1. **Python MCP server** at `app/mcp_server/tools/missions.py::_serialize_mission`
   — runs ONLY when `python -m app.mcp_server` is exposed externally.
   Railway runs the FastAPI REST API, not the Python MCP server, so this
   path is **dark in production**.
2. **TS MCP package** at `packages/tracelab-mcp/src/index.ts::handleGetMission`
   / `handleListMissions` — calls the FastAPI REST endpoint and shapes
   the response client-side. **This is the load-bearing path** for all
   real users (Claude Desktop, Claude Code).

Implication for this contract: when a field gains/loses, BOTH serializers
must be updated. T41.2 was discovered when the Python serializer was
fixed but not the TS one (both had hand-rolled object literals stripping
the same 12 fields). After T41.4 split slim/full payloads, BOTH apply
the trim with matching thresholds (5KB).

## How to update this doc

Whenever any of these fire, edit this doc as part of the same commit:

1. **`MissionCreate` or `MissionUpdate` Pydantic schema** gains/loses a
   field → add/remove a row in the table above.
2. **MCP `create_mission` or `update_mission` tool input schema** changes
   in either `app/mcp_server/tools/missions.py::MISSION_TOOLS` or
   `packages/tracelab-mcp/src/index.ts` → confirm the row matches the
   new schema; both the JSON schema and Zod schema are derived from
   this doc.
3. **`MissionResponse` schema or REST `_to_response`** changes → update
   the "REST response field" column; if the field was renamed, both
   serializers need updating too.
4. **Mission ORM model** gains/loses a column → update the "DB column"
   and "DB type" columns; check that all serializers and the DS worker
   SELECT are accounted for.
5. **DS worker `CLAIM_MISSION_SQL`** changes → update the "DS worker
   SELECT" column. This is the one column DS owns; coordinate via the
   message bus when this changes upstream.
6. Bump the **commit pins** in the header table to point at the
   commits that match the doc's current state.

Treat the rule the same way as the T40.0 MCP contract-guard rule (now
in `CLAUDE.md`): a mission-shape change isn't done until this doc is
updated and a commit-time CI check (future T-something) enforces the
parity.

## Related docs

- `cmos/contracts/deepsearch-compiler-vendor.md` — the vendored DS
  contract compiler in TraceLab and its resync ritual. The compiler
  reads `mission_context` (the dict built by
  `build_mission_context_from_mission`); this doc tells you what's
  in that dict.
- `CLAUDE.md` — links here for any agent touching mission shape.
- TraceLab `app/api/v1/missions.py::_to_response` — the canonical REST
  serializer; mirror its field list when adding new authoring fields.
- TraceLab `app/mcp_server/tools/missions.py::_serialize_mission` — the
  Python MCP serializer (production-dark per the T41.4 learning).
- TraceLab `packages/tracelab-mcp/src/index.ts::handleGetMission` — the
  load-bearing TS MCP shaper.
- DeepSearch `deepsearch/worker/poller.py::CLAIM_MISSION_SQL` — the
  worker SELECT; if it doesn't include a column, that field is invisible
  to DS at runtime even if it's correctly persisted.
