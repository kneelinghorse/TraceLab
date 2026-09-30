# Mission log delivery v2

LOG-1, Sprint 61. Guiding templates: [architecture](../foundational-docs/tech_arch_template.md) and [roadmap](../foundational-docs/roadmap_template.md). TraceLab owns persistence; DeepSearch owns emission. Shared example wire payload: `tests/fixtures/mission-logs-v2/batch.json`. CMOS records the design decision and rollout status.

## Negotiation and authorization

A service principal first calls `GET /api/v1/missions/{mission_uuid}/logs/capabilities`. The response must contain `contract_version: "tracelab-mission-logs-v2"`, `max_batch_entries: 200`, `max_message_chars: 2048`, `final_flush: "terminal_result_key"`, and `legacy: "retired"` (or the transitional `"terminal_only_until_LOG-2_cutover"` marker before cutover). A 404, missing marker or different contract is **not ready**. No timer delivery starts until this proof and lease ownership are available.

Use `POST /api/v1/missions/{mission_uuid}/logs/v2`. Both capability and write routes require a service principal even with RBAC disabled; human admins/owners are denied. GET of saved logs retains existing human resource authorization. Raw ownership proof belongs only in the authenticated HTTPS request body. Never put it in URLs, log messages, telemetry, errors, GET/MCP responses or receipts. The receiver rejects entries whose message/source contains the submitted raw lease token. Validation errors omit submitted values. No response echoes the request body.

## Request

The root object accepts only `contract_version`, `mission_id`, `attempt_count`, `lease_owner`, `lease_token`, and `logs`. Mission UUID must equal the path; attempt is a positive 32-bit integer. Owner/token are nonempty, at most 256/512 characters. Token uses a secret-valued input type. The batch contains 1–200 entries from that one attempt. Unknown fields, mixed-attempt entry fields, duplicate event IDs or duplicate sequences fail the entire batch.

Each entry accepts only:

| Field | Contract |
| --- | --- |
| `event_id` | Stable UUID allocated before enqueue; reuse across retries |
| `sequence` | Positive 32-bit integer, increasing per attempt; gaps after bounded queue overflow are allowed |
| `level` | DEBUG, INFO, WARNING, ERROR or CRITICAL |
| `message` | Nonempty text, at most 2048 characters; sender's existing allowlisted projection, never raw prompts/errors/credentials |
| `source` | Null or at most 100 characters |
| `logged_at` | Required timezone-aware instant, canonicalized to UTC microseconds |

Do not regenerate IDs, sequences, timestamps or messages when retrying. Reordering a batch is allowed; changing a stored event is not.

## Atomic ownership and final flush

The receiver locks the mission row and holds it through insertion/commit. The worker's claim, heartbeat, release, reclaim and terminal UPDATEs serialize on that same row. PostgreSQL reads `clock_timestamp()` after acquiring the lock, avoiding a pre-wait timestamp. SQLite starts a fresh `BEGIN IMMEDIATE`; it does not pretend `FOR UPDATE` works there.

Every request, including an all-replay request, must match the persisted owner and attempt count, then satisfy either:

1. Active: status `in_progress`, constant-time equality of the private token and live lease token, and lease expiry strictly later than the locked check's database time.
2. Terminal: status `completed`, `validation_failed` or `blocked`, active token cleared, and constant-time equality of the durable result key with SHA256 of UTF-8 `tracelab-missions-lease-v2:{canonical-mission-uuid}:{attempt_count}:{lease_token}`. This is the existing DeepSearch `LeaseAttempt.persistence_key`, not a new claim mechanism. The durable owner remains on terminal writes.

Wrong mission, forged/expired/released/requeued/reclaimed proof and terminal rows without that matching result identity reject with 409. Cancellation is not terminal permission to append. Expired attempts cannot add observations under a successor. Replays after ownership loss are rejected too; accepted historical rows remain readable with their original attribution. A matching final batch can arrive or retry after terminal persistence clears the token. Log failure never changes the research result or permits an unfenced fallback.

## Replay and acknowledgements

Database uniqueness covers both `(mission_id, attempt_count, event_id)` and `(mission_id, attempt_count, sequence)`. Legacy rows have all three added identity fields null. For existing identity, every canonical field must match (event ID, sequence, level, message, source and UTC timestamp). Reusing an ID with changed content, or a sequence with another ID, returns 409 with **zero partial inserts**. Validate the whole batch before adding new rows.

Success returns exactly the version marker, mission UUID, attempt count, `accepted` (new rows), `replayed` (identical existing rows), and `event_ids` in request order. HTTP 201 means at least one new row; HTTP 200 means every entry replayed. `accepted + replayed == len(logs)` and the complete ID list must match before the sender dequeues anything. An arbitrary 2xx, `accepted` alone, malformed JSON or mismatched marker/identity/counts is not an acknowledgement. Lost acknowledgements reuse the identical payload. Exact replay inserts no rows and does not change receipt timestamps.

No log endpoint mutates mission status, result identity, usage, Reports or Evidence. The lock alone is not a status update.

## Read compatibility and order

GET `/api/v1/missions/{id}/logs?limit=100` keeps the existing array and fields (`id`, `level`, `message`, `source`, `logged_at`, `created_at`), with nullable `attempt_count`, `event_id`, `sequence` added. Raw proofs and derived result keys are absent. `created_at` is server receipt time and is never replaced on replay. Legacy rows remain unmodified, explicitly unattributed through null identity fields.

Keep newest-by-`logged_at` window semantics (1–500 rows, newest last). Break equal timestamps deterministically by attempt, sequence, then persisted row UUID; these keys are reversed with the selected window. Do not interpret old emitted times in a terminal backfill as evidence of live delivery. MCP's existing pass-through must be tested against the deployed route before closing this mission.

## Receiver-first rollout and retirement

One transitional receiver release retains unversioned POST `/logs` for the currently deployed terminal-only worker. It is service-only even with RBAC off, bounded to 1–200 entries and the same text limits, accepts only a terminal mission with a durable result key, and rejects a mission that already contains v2 observations. Legacy records remain unattributed and **not idempotent**. Canonical `logs` and old `entries` aliases are preserved for this compatibility window. Extra fields are forbidden, so a v2-shaped payload cannot silently downgrade on this route.

The window ends in LOG-2's coordinated cutover after its worker has passed v2 negotiation, no-provider ownership/replay tests and explicitly authorized live acceptance. LOG-2 then retires the unversioned append route with 426; it cannot remain an indefinite bypass. A rejected v2 proof never falls back to legacy, even during this window. Rollback stops v2 emission and preserves research results/accepted history; it does not turn on unfenced live appends. DeepSearch deployment and paid dispatch retain their explicit authorization gate.

## Required proof

SQLite and real PostgreSQL tests cover additive migration/rollback preserving old rows, row/sequence uniqueness, canonical replay, changed-content conflicts, whole-batch rollback, service-only writes in both RBAC modes, human scoped reads, malformed/oversized/private-proof errors, concurrent insertion, lease change/expiry after lock waits, requeue/reclaim and terminal flush races. Use the shared wire fixture through the actual HTTP client. A deployed controlled no-provider mission proves negotiation, ingest, replay, stale refusal and authorized MCP reads on exact serving commits. This does not close live worker delivery or carryover #412.

## LOG-2 sender and reader

The worker captures an immutable `LeaseAttempt`, allocates each UUID and sequence
before enqueue, and starts delivery only after confirming current ownership,
starting the heartbeat watch, and negotiating this contract. Five-second timers
and the existing threshold share one serialized background transport. Queue
capacity remains 2,000, batches at most 200, and attempts at most three with
interruptible exponential backoff. Full acknowledgement identity/count/order and
HTTP 200/201 semantics must match before dequeue. A 409 stops this attempt;
there is no unversioned fallback. Stop/discard quiesces in-flight writes before
release or requeue. Terminal retries keep the original proof and IDs.

Child and parent use one enum/numeric allowlist for structured observations.
Neither raw log formatting nor arbitrary extras become the persisted message.
Accepted history remains attributable after ownership loss.

The UI polls every five seconds while queued/running. Server `created_at` is
receipt freshness; `logged_at` labels emission. Thirty seconds without a new
receipt is a quiet gap, not proof of failure. Transient errors retain rows;
401/403/404 hide them. User+mission isolate both SWR keys and local timers. A
terminal transition revalidates immediately and for 45 seconds to catch the
post-commit final flush, with manual refresh thereafter. Known enums have readable
labels; unknown text remains visible. No percentage is inferred.

The opt-in `tests/test_live_log_cross_service.py` imports a real independent
DeepSearch checkout via `DEEPSEARCH_SOURCE_ROOT` and uses actual HTTP against a
loopback receiver. Without that explicit checkout it reports a named skip;
release readiness requires executing it with no skip. LOG-2's readiness receipt
records the exact sender/receiver source identities and production gate.

## Retirement release gate

This change is prepared on `codex/sprint-61-retire-legacy-logs` and must remain
unpublished until the authorized LOG-2 worker acceptance receipt exists.
After that cutover, service POST `/logs` returns 426 even with valid terminal
proof; capability `legacy` is `retired`. Human/anonymous denials remain 403/401,
and existing legacy history remains readable. Deploying this before worker
acceptance would disable the old worker's terminal transport.
