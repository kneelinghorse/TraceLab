# Evidence Ledger Boundary Contract

This document is the single source of truth for the LEDGER-1 agent-writer
surface and the LEDGER-3 retrieval boundary:

**`tracelab_evidence` MCP input → TypeScript API client → authenticated REST
request → REST response → MCP response.**

The public package version for the MCP portion of this contract is
`@aquex/tracelab-mcp` 1.1.1. The LEDGER-2 service-writer channel documented
below is deliberately REST-only and does not add an MCP action, tool input, or
legacy-name mapping.

## Runtime ownership

The load-bearing MCP implementation is the published TypeScript package:

- tool schema, validation, handlers, and dispatch:
  `packages/tracelab-mcp/src/index.ts`
- HTTP client and public TypeScript types:
  `packages/tracelab-mcp/src/api-client.ts`
- contract regressions:
  `packages/tracelab-mcp/src/index.test.ts`

The Python MCP server under `app/mcp_server/` is production-dark and retains
its intentionally flat mission-only surface. LEDGER-1 does not expose a
parallel Python evidence tool. The FastAPI REST implementation remains the
server-side authority for authentication, authorization, persistence, and
validation.

## LEDGER-2 DeepSearch service-writer channel

DeepSearch triggers one server-owned projection after its result is durably
completed in TraceLab:

```http
POST /api/v1/missions/{mission_uuid}/evidence
X-API-Key: <service-principal API key>
Content-Type: application/json

{
  "schema_version": 1,
  "deepsearch_job_id": "persisted-job-id"
}
```

The request rejects additional fields. It contains no claims, sources,
dispositions, ownership values, or workspace identifiers. This is not an MCP
surface: the published `tracelab_evidence` cluster remains the human/agent
writer and retrieval surface described below. DeepSearch calls this
authenticated REST route directly. Both fields are required; the job id is
matched exactly and surrounding whitespace is rejected rather than normalized.

`authorize_service_or_403(..., enforce_when_disabled=True)` runs before mission
lookup. Regardless of the global RBAC rollout flag, only `role = service`
passes; human owner and admin roles do not. The server then
requires a terminal reviewable mission whose status is exactly `completed` or
`validation_failed`, a byte-matching persisted `deepsearch_job_id`, and an
existing mission project with `deleted_at IS NULL`. Every other mission status
is ineligible.

Projected entries are stamped from server state:

- `project_id = mission.project_id` and `mission_id = mission.id`;
- `session_key = "deepsearch:" + mission.deepsearch_job_id`;
- `origin = "deepsearch-worker"`;
- `owner_id = mission.owner_id`, falling back to `project.owner_id` only when
  the mission owner is null;
- `workspace_id = project.workspace_id`;
- `query = null`.

The caller cannot override these values. The projection never invents a
`contradicting` disposition, research query, loop number, or other provenance.

### Authoritative projection

Only these persisted paths participate:

- `mission.result_protocol.sources_collected`;
- `mission.result_protocol.citations`;
- `mission.result_markdown` for citation spans;
- `mission.execution_metadata.synthesis_telemetry.critique_telemetry.annotations`;
- `mission.execution_metadata.synthesis_telemetry.tool_outcomes.ledger_records`
  and `ledger_records_truncated`.

`execution_metadata.synthesis_telemetry`, its `tool_outcomes` object, and the
`ledger_records` and `ledger_records_truncated` keys are required active-result
envelopes. An explicit empty `ledger_records` list with
`ledger_records_truncated = 0` is valid; a missing key is malformed persisted
data rather than an implicit empty audit. Generic diagnostic `records` and
`records_truncated` are not projection inputs, and there is no legacy fallback
or historical reconstruction.

DeepSearch must derive `ledger_records` before applying the generic diagnostic
250-record cap, preserve each relevant full URL up to the 4,096-character
consumer limit, sanitize `error_category` into the bounded taxonomy rather than
persisting raw errors, and merge relevant attempts recovered across
checkpoints. The producer must impose and test an attempt budget compatible
with the 1,000-entry projection ceiling; it may never silently clip this audit.
If completeness cannot be proved, a nonzero `ledger_records_truncated` makes
TraceLab fail the handoff loudly.

The similarly named
`result_protocol.report_metadata.forensic.critique_telemetry` summary is not a
second writer. Raw collected-source `body` text is never copied into an entry
and never included in the idempotency digest. Source claims use title and
snippet, then the source URL as a non-invented fallback.

| Persisted fact | Ledger projection |
| --- | --- |
| Citation with `live = true` | `supporting`; `claim` is exactly `result_markdown[start_index:end_index]`. |
| Citation with `live = null` | `background` with tag `liveness-unknown`; the exact markdown span remains the claim, and any failed outcome remains a separate rejected attempt. |
| Citation with `live = false` | `rejected`; summary preserves the liveness rationale and structured failed outcome for the URL. |
| Uncited collected source with `alive = true` or absent | `background`; claim is `title: snippet`, title, snippet, or URL in that order. |
| Uncited collected source with `alive = false` | `rejected`; the source claim and structured rejection rationale are retained. |
| Applied critique annotation with verdict `unsupported` or `hallucinated` | One `rejected` claim per `citation_url`; claim is the exact anchor and summary preserves note and reason. |
| Failed `source_fetch` or `url_liveness` record | One distinct `rejected` attempt claim per distinct structured outcome, preserving `tool`, `status`, `status_code`, `error_category`, and `alive` when present. Raw free-form `error` is not copied because it can contain secrets. |

A failure for an already-rejected collected or cited URL enriches that claim
instead of creating a duplicate. Otherwise the rejected attempt remains beside
any live or background evidence claim: one URL can truthfully support a claim
while also recording a failed retrieval attempt. Applied critique claims remain
distinct for the same claim-level reason.

Every source, citation, critique, and relevant tool-outcome URL is normalized
through the same `AnyHttpUrl` boundary before any map, set, hash, or source
upsert. URLs containing username or password userinfo are rejected so embedded
credentials cannot reach the ledger or MCP; query parameters remain part of
the source identity. Canonical-equivalent collected-source rows collapse deterministically:
null and non-null metadata merge, while conflicting nonempty title, snippet,
or liveness values fail the entire projection. Canonical-equivalent URLs across
citations, critiques, and tool outcomes therefore enrich and sight the same
ledger source. Critique anchors are exact claims and surrounding whitespace is
rejected rather than silently stripped.

Relevant `source_fetch` and `url_liveness` records require `status = ok|error`
and a canonical URL. Optional `status_code` is null or a non-boolean integer
from 0 through 599 (zero is an upstream timeout/connect sentinel), optional
`error_category` is null or a string of at most 200 characters, and optional
`alive` is null or boolean; `url_liveness` requires a non-null `alive` value.
The exact allowed key subset is `tool`, `url`, `status`, `status_code`,
`error_category`, and `alive`. An unknown tool or any extra key, including raw
`error`, fails the trusted ledger envelope; no extra value is copied or hashed.
Generic diagnostic records remain outside the projection contract entirely.

Every projected record is validated against the `CaptureItem` limits. Active
envelopes, records, URLs, liveness values, citation spans, applied-critique
verdicts, and structured outcome fields fail loudly when malformed. A nonzero
`tool_outcomes.ledger_records_truncated` fails rather than capturing a partial
ledger.
Exact duplicate projected items are removed; distinct claims sharing a URL are
retained. The canonical projection must contain 1–1,000 entries after exact
deduplication, with no truncation.

### Atomicity and replay

`deepsearch_ledger_batches` owns the idempotency claim. It stores a unique
`(mission_id, deepsearch_job_id)`, `session_key`, SHA-256 `payload_hash`,
`entry_count`, and timestamps. Each projected `ledger_entries` row links to its
batch through nullable `deepsearch_batch_id`; interactive MCP entries leave the
column null. The link uses `ON DELETE SET NULL`: deleting a mission cascades to
its batch without deleting the durable evidence rows.
SQLite referential-action tests explicitly enable `PRAGMA foreign_keys=ON`;
the production core database is PostgreSQL, and LEDGER-2 does not change the
global SQLite engine policy.

Validated items are normalized, sorted by their complete serialized fields,
and exact-deduplicated before hashing and insertion. The canonical SHA-256
payload includes schema version, project UUID, mission UUID, job ID, session
key, and every projected item. Array reordering does not create false drift;
a material claim, source, disposition, or rationale change does.

The service locks the mission on PostgreSQL and claims the batch with a
dialect-specific `INSERT ... ON CONFLICT DO NOTHING`. The batch, canonical
source upserts, and ledger entries commit in one transaction. PostgreSQL
concurrent callers converge on one batch and one entry set.

- Initial capture returns HTTP 201 with `status = "captured"`.
- An exact replay returns HTTP 200 with `status = "already_processed"`, the
  same lexically ordered `entry_ids`, and the same `entry_count`. Replay exits
  before source upsert and does not increment `source_sighting_count`.
- A replay whose canonical payload differs returns HTTP 409 and changes
  nothing.

Successful responses contain exactly `status`, `mission_id`,
`deepsearch_job_id`, `session_key`, `entry_ids`, and `entry_count`. Request
schema errors (including unsupported schema version or an extra field) are HTTP
422. Malformed persisted result data is HTTP 400, missing mission or live
project is HTTP 404, and state, job, or replay conflicts are HTTP 409.

### Durable terminal delivery outbox

`deepsearch_evidence_outbox` makes the trigger durable without changing the
REST request or MCP surface. Its composite identity is
`(mission_id, deepsearch_job_id)`. The immutable enrollment snapshot stores a
nonempty `deepsearch_result_key`, positive `mission_attempt_count`, terminal
status (`completed` or `validation_failed`), and `schema_version = 1`. Delivery
state stores `pending|leased|acked|dead_letter`, attempt count, next-attempt
time, lease token and expiry, acknowledgement time, last HTTP status/error
code, and timestamps. Database checks enforce coherent leases and
acknowledgements; the dispatcher index is `(state, next_attempt_at,
created_at)`.

DeepSearch enrolls the outbox row in the same fenced terminal SQL CTE that
persists a `completed` or `validation_failed` result, using `ON CONFLICT DO
NOTHING`. A conflict is successful only when the existing result key, mission
attempt count, terminal status, and schema version exactly match; any reused
job identity with a different snapshot fails closed. There is no history scan
or migration backfill.

Dispatchers claim at most 25 due `pending` rows or expired `leased` rows with
`FOR UPDATE SKIP LOCKED`, write a unique lease token/expiry, and set
`next_attempt_at = lease_expires_at` so that the single delivery index supports
both cases. They use bounded backoff for at most 12 delivery attempts. Ack,
retry release, and dead-letter updates are fenced by mission ID, job ID,
`state = leased`, and the exact lease token. Any 2xx response acknowledges the
row. Network failures, HTTP 429, and HTTP 5xx retry. Deterministic HTTP 400,
401, 403, 404, 409, and 422 responses move the row to `dead_letter` and alert.
The projection endpoint remains callable by an authorized service principal
without an enrollment row, so manual recovery is possible.

The outbox mission foreign key uses `ON DELETE CASCADE`. An authorized mission
hard-delete therefore cancels unacknowledged delivery; this is intentional
because that deletion also destroys the persisted result that is the sole
authoritative projection source. Migration 043 refuses downgrade while either
outbox rows or DeepSearch batch rows exist, preventing silent loss of delivery
or replay ownership.

## Tool surface

`tracelab_evidence` dispatches on one of five actions:

| Action | HTTP contract | Purpose |
| --- | --- | --- |
| `capture` | `POST /api/v1/evidence/capture` | Store 1–100 sourced findings in one batch. |
| `note` | `PUT /api/v1/evidence/notes/{note_key}` | Create or replace one keyed working note. |
| `list` | `GET /api/v1/evidence` | Page through entries and notes within an authorized project. |
| `search` | `GET /api/v1/evidence/search` | Search prior evidence claims within an authorized project. |
| `promote` | `POST /api/v1/evidence/promote` | Roll one session into a report and, optionally, a searchable document. |

`note_key` is trimmed and encoded as one path segment with
`encodeURIComponent`. Dot-only keys `.` and `..` are rejected before fetch:
WHATWG URL parsers normalize those values as navigation segments even though
`encodeURIComponent` leaves them unchanged. GET filters are encoded with
`URLSearchParams`. GET requests never carry a body.

## LEDGER-3 retrieval boundary

Raw ledger entries and document chunks deliberately remain separate search
surfaces:

- `tracelab_evidence(action="search")` searches raw, project-scoped ledger
  claims and returns their complete source, disposition, session, and ownership
  metadata. Agents use this action before external research to reuse prior
  findings without losing provenance.
- `tracelab_search(action="knowledge")` remains semantic search over ingested
  document chunks. It does not query `ledger_entries`, embed raw ledger claims,
  or assign them synthetic document identifiers.
- `tracelab_evidence(action="promote", target="document")` is the explicit
  bridge between the surfaces. Promotion first creates the provenance-linked
  report, then sends that report through the canonical document ingestion,
  chunking, embedding, and Qdrant pipeline. Only promoted document material can
  enter document-backed `tracelab_search` and downstream PEDR/preflight flows.

This boundary is intentional. A raw ledger entry can be supporting,
contradicting, rejected, or background evidence, while PEDR preflight makes a
mission-level reuse decision over governed document results. Directly mixing
raw claims into the document-chunk result contract would either discard that
disposition and source provenance or require a new heterogeneous result and
durable vector-indexing lifecycle. LEDGER-3 does neither implicitly.

## Input contract

### `capture`

```json
{
  "action": "capture",
  "project_id": "uuid",
  "session_key": "string",
  "mission_id": "optional uuid",
  "entries": [
    {
      "claim": "string",
      "summary": "optional string",
      "source_url": "https://example.com/source",
      "snippet": "optional string",
      "query": "optional string",
      "disposition": "supporting",
      "tags": ["optional", "tags"]
    }
  ]
}
```

The REST body is the MCP input with `action` removed. Required text and tags
are normalized as described below. Each item explicitly admits only the seven
fields shown above.

### `note`

```json
{
  "action": "note",
  "project_id": "uuid",
  "session_key": "string",
  "note_key": "stable-key",
  "content": "working note",
  "mission_id": "optional uuid",
  "tags": ["optional", "tags"]
}
```

`note_key` is used only in the encoded URL path. The REST body contains
`project_id`, `session_key`, `content`, and the optional `mission_id` and
`tags` fields.

### `list`

Required query parameter: `project_id`.

Optional query parameters: `session_key`, `mission_id`, `disposition`,
`page` (default 1), and `page_size` (default 20, maximum 100).

### `search`

Required query parameters: `project_id` and `q`.

It accepts the same optional filters and pagination parameters as `list`.

### `promote`

```json
{
  "action": "promote",
  "project_id": "uuid",
  "session_key": "string",
  "title": "optional artifact title",
  "target": "report"
}
```

`target` is optional at the MCP and REST boundary and defaults to `report`.
Allowed values are `report` and `document`. Both targets create a report;
`document` additionally promotes that report into a searchable document.

### Validation limits

| Field | Limit |
| --- | --- |
| `session_key` | 1–255 characters before trimming; must remain nonblank |
| capture `entries` | 1–100 items |
| `claim`, `summary`, `snippet` | at most 20,000 characters each (`claim` is trimmed and nonblank) |
| `source_url` | absolute HTTP(S) URL, at most 4,096 characters |
| capture `query` and search `q` | at most 4,000 characters (`q` is trimmed and nonblank) |
| `note_key` | 1–100 characters before trimming; must remain nonblank and cannot be `.` or `..` |
| note `content` | 1–50,000 characters before trimming; must remain nonblank |
| `tags` | at most 50 tags; each is trimmed, must remain nonblank, and is at most 64 characters after trimming; duplicates are removed in first-seen order |
| promotion `title` | 1–255 characters before trimming and nonblank when provided |
| `page_size` | 1–100 |

The MCP mirrors these limits and backend-style trimming for immediate agent
feedback. FastAPI remains authoritative and must reject invalid direct REST
requests independently.

## Server-owned fields and enums

Clients must never send `origin`, `source_id`, `source_sighting_count`,
`owner_id`, or `workspace_id`.

- Interactive MCP writes are stamped `origin = "mcp-agent"` by the server.
- `deepsearch-worker` is reserved for the separate service-writer channel.
- `source_id` identifies the canonical project source derived from the
  normalized source URL. `source_sighting_count` reports how many captures have
  cited that source and is always at least one.
- Ownership and workspace are derived from the authenticated principal and
  project; callers cannot self-assign tenancy.

Allowed dispositions are:

- `supporting`
- `contradicting`
- `rejected`
- `background`

Allowed origins in responses are `mcp-agent` and `deepsearch-worker`.

## Exact response shapes

### Entry

Every entry returned through capture, list, or search contains every field:

| Field | Type |
| --- | --- |
| `id` | UUID string |
| `project_id` | UUID string |
| `mission_id` | UUID string or `null` |
| `session_key` | string |
| `origin` | `mcp-agent` or `deepsearch-worker` |
| `claim` | string |
| `summary` | string or `null` |
| `source_url` | string |
| `source_id` | UUID string |
| `source_sighting_count` | integer, at least 1 |
| `snippet` | string or `null` |
| `query` | string or `null` |
| `disposition` | evidence disposition |
| `tags` | string array |
| `owner_id` | UUID string or `null` |
| `workspace_id` | UUID string or `null` |
| `created_at` | ISO datetime string |
| `updated_at` | ISO datetime string |

### Note

Every note returned through note or list contains every field:

`id`, `project_id`, `mission_id`, `session_key`, `origin`, `note_key`,
`content`, `tags`, `owner_id`, `workspace_id`, `created_at`, `updated_at`.

`mission_id`, `owner_id`, and `workspace_id` may be `null`; `tags` is always
an array. `origin` is always present.

### Action envelopes

| Action | Exact response envelope |
| --- | --- |
| `capture` | `{ entries, count }` |
| `note` | the full Note object |
| `list` | `{ entries, notes, entry_total, note_total, page, page_size }` |
| `search` | `{ entries, total, page, page_size }` |
| `promote` | `{ project_id, session_key, target, report_id, document_id, title, entry_count, note_count, status }` |

Promotion always returns a non-null `report_id`. `document_id` is `null` for
`target = "report"` and non-null after successful document promotion. The
response `target` is always explicit even when the request used its default.
`status` is `created` for a report-only promotion and `completed` after a
document promotion finishes.

## Serialization invariant

Evidence MCP handlers serialize the typed REST response object wholesale.
They must not rebuild entries, notes, or promotion results with hand-written
field projections. This prevents a repeat of T41.2, where the REST client
received fields that the MCP handler silently discarded.

The regression fixture must include every public Entry and Note field,
including nullable fields, canonical source identity and sighting count,
tenancy identifiers, `origin`, and timestamps, and must compare the parsed MCP
payload to the complete REST fixture with exact equality. Capture, note, list,
search, and promote tests also lock their exact URL, HTTP method, encoded
query/path, and request body through
`handleTracelabEvidence`, which is the published MCP handler path.

Tool-list parity is a three-way invariant:

1. the exported `TOOLS` descriptor list;
2. the exported `CLUSTER_ACTIONS` action enums; and
3. the exported `CLUSTER_HANDLERS` registry used by the real CallTool handler.

Their tool-name sets must remain identical.

The CallTool dispatcher must resolve both cluster and legacy names with an
own-property check. Plain-object prototype names such as `toString`,
`constructor`, and `__proto__` are unknown tools, never inherited handlers or
migration records.

## Update ritual

Any evidence request field, endpoint, HTTP verb, input enum, default, or
validation-limit change must update in the same commit:

1. the FastAPI schema and route;
2. `api-client.ts` types and method;
3. the MCP JSON Schema and Zod schema in `index.ts`;
4. the exact handler-level contract fixture in `index.test.ts`; and
5. this document.

A response-only field addition does not change the MCP input schema. It must
update the FastAPI response schema, the `api-client.ts` response type, the full
handler-level response fixture, and this document in the same commit.

Before publishing, follow the repository package smoke gate: build, test,
`npm pack`, install the tarball in a clean directory, start the real entrypoint,
invoke the evidence tool once against the deployed API, and confirm no CommonJS
globals (`__dirname`, `__filename`, `require(`) leaked into the ESM source.
