# Evidence Ledger Boundary Contract

This document is the single source of truth for the LEDGER-1 agent-writer
surface and the LEDGER-3 retrieval boundary:

**`tracelab_evidence` MCP input → TypeScript API client → authenticated REST
request → REST response → MCP response.**

The public package version for this contract is `@aquex/tracelab-mcp` 1.1.1.
This response-only revision adds canonical source metadata to the eighth
action-clustered tool introduced in 1.1.0; it does not change tool inputs or
legacy-name mappings.

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
