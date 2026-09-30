# Sprint 61 — Account recovery and live run logs

Planned 2026-09-30 in CMOS session **PS-2026-09-30-004**, decision **#563**. CMOS is authoritative for mission criteria, dependencies and status; this document explains the implementation boundaries and handoff.
Guiding templates: [roadmap](../foundational-docs/roadmap_template.md) and [technical architecture](../foundational-docs/tech_arch_template.md). Intent: [living roadmap](../foundational-docs/roadmap-sprints-57-60-the-librarian.md).

## Outcome and authorization

Derek asked: “open a planning session and look at what we need to do for s61 for the password reset workflow and I believe we still have deepsearch live log issue hanging out there. Lets get into those details and see what's possible for s61, then we can create the sprint and missions needed to do the work and we'll hand that off to a fresh session to go build.”

The existing Planned Sprint 61 and AUTH-1/AUTH-2 are refined, not duplicated. This session plans and inspects source; it does not implement recovery, reset an account, send mail/messages, deploy, or submit paid research. Sprint 61 stays Planned until a build mission starts. No dates or delivery estimates are invented.

The outcomes are (1) recover a forgotten password through a real Resend email, independently or with admin help, and (2) see genuine worker log observations while research is still running, with safe retries and honest freshness. Recovery can ship even if the worker integration needs a later deployment window.

### Working product defaults

These are agent recommendations, not claims that Derek selected the options in the planning questions:

- Admins **send a reset email to the stored mailbox**; the recipient chooses the password. No administrator-set temporary password or mailbox reassignment.
- Successful forgotten-password recovery signs out prior browser sessions and revokes **that human user's** API keys, including device-issued MCP keys. Explain reconnecting integrations before submission. The separate DeepSearch service principal and other users are unaffected. A request or link preview changes no credentials.
- Plan the worker counterpart alongside TraceLab's log work. LOG-2 tracks that integration here; the handoff below is ready for a DeepSearch build session. DeepSearch's existing Sprint 93 and blocked model evaluation are untouched. No cross-project message has been sent and no DeepSearch backlog ownership has been claimed.

If Derek answers differently, update the corresponding CMOS criteria and this section before building; do not invent a prior user approval. Routine implementation details below can be finalized and recorded by the builder without reopening settled product scope.

## Mission sequence

| Order | Mission | Deliverable | Dependency |
| --- | --- | --- | --- |
| 1 | **AUTH-1** | Signed-out email recovery, single-use tokens, credential invalidation, working public reset UI | — |
| 2 | **AUTH-2** | Admin Users action sending the same recovery email, with target confirmation and audit | AUTH-1 |
| 3 | **LOG-1** | Versioned, attempt-scoped, replay-safe TraceLab log ingestion and readable log metadata | —; land before worker enablement |
| 4 | **LOG-2** | DeepSearch delivery during an owned attempt, integrated with truthful TraceLab polling and final refresh | LOG-1; coordinated worker change |
| 5 | **WALK-4** | Deployed recovery and in-progress-log acceptance, exact-build receipts and sprint closeout | AUTH-2 and LOG-2 |

Use fresh build sessions and follow each mission's actual criteria. The two tracks are technically independent; the listed order prioritizes account recovery. CMOS dependency edges are advisory, so the builder must enforce them. A completed receiver or simulated timer test alone does not complete LOG-2/WALK-4.

## What exists, and what is missing

Inspection began at TraceLab `778f6af`; the planning branch starts at its merged `origin/main`, `e02fbcf`. DeepSearch source inspected at `2468fb9` in the sibling `DeepSearch.alpha` repository. These are source observations, not fresh deployed-state claims.

| Surface | Observed implementation | Planning consequence |
| --- | --- | --- |
| Login / Settings | `app/api/v1/auth.py`: email login and PATCH `/auth/me` requiring current password | Retain known-password Settings behavior; recovery needs separate public APIs |
| JWT | `app/core/security.py`: payload has `sub` and `exp`; decoder returns only subject | Password replacement alone leaves prior JWTs and refresh valid; add a user credential revision and preserve it through verification |
| Device authorization | `app/api/v1/auth_device.py`, `app/models/device_authorization.py`: approved grant points to API key; plaintext delivery is process-local; pending grants have no user owner | Revoke linked human keys/grants safely, respect FK order, prevent reset/approval races; do not purge other users' unowned pending codes |
| Public pages | `frontend/src/components/AppShell.tsx` and `AuthGate.tsx` gate signed-out routes except error pages | Explicitly allow only recovery routes; a new page alone would still show LoginPanel |
| Mail | `app/services/notifications.py`: reusable `Email`, `ResendClient`, address filter; mission preference gating is separate | Recovery bypasses mission-email preferences; sanitize provider errors before sending token-bearing content |
| Rate limiting | `app/core/rate_limit.py`: trusted-proxy IP extraction, process-local sliding window | Reuse IP policy; bound reset request and redemption separately and add recipient-level send protection without revealing account existence |
| Log receiver | `app/api/v1/missions.py`: service-authenticated POST blindly appends; GET authorizes human read | Add ownership/replay checks before allowing live worker retries; retain legacy history and RBAC |
| Log display | `MissionRunActivity.tsx`: GET latest 100 lines every 5 seconds while queued/running | Polling already exists; distinguish empty, failed, stale and receiving states, and fetch the final batch when status becomes terminal |
| Worker | DeepSearch `worker/main.py`: constructs `TracelabLogHandler(auto_delivery=False)`, publishes only after a fenced terminal write, discards unfinished attempts | Terminal-only delivery is deliberate lease protection; do not solve it by flipping a flag |
| Worker transport | DeepSearch `tracelab/log_handler.py`: interval/threshold delivery, bounded queue, retries and safe event projection; `worker/execution.py` already forwards child logs | Reuse these seams; add attempt proof and stable event identity, rather than another stream infrastructure |

CMOS learnings **#274–275** retain this investigation. Message `1621f451-c6af-4c8c-90ab-1839cefbdc4b` remains pending as of this planning session. Its September 22 production observation showed `created_at` clustered after completion even though `logged_at` spanned the run. Its claim that repeated append batches are “idempotent-safe” is incorrect for current source and must not guide the implementation.

## AUTH-1: recovery contract to implement

Use thin routers and a focused recovery service. Proposed public routes are POST `/auth/password-reset/request` and POST `/auth/password-reset/confirm`, with public UI `/forgot-password` and `/reset-password`. Final names, limits and migration numbers are recorded before code; classify new UI/API operations in the parity manifest as REST-only authentication flows rather than adding credential tools to MCP.

1. **Request.** Normalize email consistently with login. Return the same generic response for known, unknown, disabled, service and non-deliverable accounts. Avoid account-dependent provider latency in the public response; isolate mail dispatch from request completion with explicit observable failure handling. Rate-limit by trusted client IP and a privacy-preserving normalized recipient key; an address cooldown must not reveal that an account exists or lock out normal password login. Keep bounded memory/storage and document process/replica behavior.
2. **Token.** Use a cryptographically random opaque token, store only a digest, bind it to the user and credential revision, and set a proposed **30-minute** expiry. The newest issued link supersedes earlier links; document what a failed send means and make explicit retry possible. Requesting a link does not change the password, session revision, role, activity status, ownership or keys. Merely opening an email link never consumes it, including mail-scanner visits.
3. **Confirm.** Enforce the existing password policy and matching confirmation. Atomically validate/consume the unexpired token, replace the password, increment the user's credential revision, invalidate other recovery tokens and revoke the selected credentials. Concurrent redemption succeeds once. A manual Settings password change must invalidate outstanding recovery links so an older link cannot overwrite it; preserve the existing Settings experience unless a recorded design requires a narrowly explained adjustment.
4. **Sessions and keys.** A user credential revision is the recommended mechanism. New JWTs include it; legacy JWTs without it can represent revision zero only while the user's revision is still zero. Compare the token's revision with live user state in header, refresh and query-token paths. Resolve issuance/refresh/reset races so an old password or token cannot mint a new-revision session. Revoke the recovering human's existing API keys and approved grants under the proposed policy; serialize API-key creation/device approval against reset so an already-authorized stale request cannot leave a usable credential behind. Handle grant-to-key FKs and cached plaintext. Unowned pending device codes require a fresh, valid approval and are not globally deleted. Do not affect the service principal.
5. **Streaming.** Test new SSE connections and already-open event connections: reset must stop subsequent protected deliveries from an invalidated session. Reuse the existing stream reauthorization boundary rather than assuming connection-time verification is enough.
6. **Email and privacy.** Reuse Resend and the configured HTTPS `FRONTEND_URL`, independent of `notification_emails_enabled` and per-user mission preferences. Never accept a caller-supplied recipient or redirect URL. Keep tokens and reset URLs out of provider-error logs, API errors, analytics, referrers, localStorage, screenshots and committed receipts. Prefer a fragment-carried token or an equally demonstrated no-leak route design; strip it from the address bar after safe in-memory capture and provide a retry path if state is lost. Opening a valid link while already signed in must not reset the wrong account or be blocked by the shell. Completion returns to ordinary login, with no surprise automatic sign-in.
7. **Failure UX.** Cover invalid/expired/used/superseded links, weak/mismatched passwords, rate limiting, offline requests and unavailable recovery service. A public success means “if eligible, instructions will be sent,” not confirmed inbox delivery. Disabled/service users cannot recover into human access. Narrow public-route exceptions must not expose normal app content.

Do not add a general job framework, replace the auth system, change providers or rotate the shared signing secret. Make recovery table deletion cascade or update the existing admin purge in FK order; verify PostgreSQL behavior. Correct authentication documentation for the paths touched: its current environment-login description is stale, so do not copy it as a runtime contract.

## AUTH-2: admin help

Add **Send password reset link** to the existing Users page for eligible human accounts, including self and other admins/owners. Use the existing confirmation dialog naming the target and its stored address. The server enforces `require_admin`; ordinary members, viewers, service principals and anonymous callers are denied. This grants no ability to set another user's password directly, change its address or reactivate it.

Reuse AUTH-1's request/token/mail service and recipient budget. Record initiating admin, target, timestamp and delivery outcome without secrets. Distinguish provider acceptance from mailbox delivery. Disabled/service/non-deliverable targets get a useful admin-facing refusal. Repeated clicks, resends and provider failure must follow the same supersession policy; no password/session/key changes occur until the recipient submits a valid confirmation.

## LOG-1: receiving contract before sender enablement

Freeze a small versioned request/acknowledgement contract in `cmos/contracts/mission-log-delivery-contract.md` during the build. TraceLab owns schema/migrations; DeepSearch owns worker emission. Preserve existing log fields and legacy reads. No WebSocket/SSE replacement, generic event bus or change to research success criteria is required.

The contract must include stable per-event identity and order within an attempt, the mission UUID and monotonic attempt identity, and service-authenticated ownership proof. Keep raw lease proof private and absent from GET/MCP responses and validation-error payloads. Reuse the existing lease-v2 columns and terminal result identity; do not create an unrelated claim mechanism.

- Validate an active attempt against the live mission's owner/token/attempt/status/expiry **atomically with insertion**, serialized against lease change and terminal persistence. A sender-side heartbeat check followed by an unrestricted HTTP POST is insufficient.
- Deduplicate exact retries using a database uniqueness boundary; the same identity with changed content is a conflict, not an overwrite. A lost HTTP acknowledgement must not duplicate the log. Define accepted/replayed counts and client checks precisely.
- Specify terminal-race behavior: successful terminal persistence clears the active lease token. A final batch needs a separately validated matching terminal result/attempt path, or must finish under the active lease before terminalization. Failed/requeued/expired attempts cannot append new lines under a successor. Historical accepted observations may remain, visibly associated with their own attempt.
- Bound batch count, event size and queue handling; reject malformed or mixed-attempt batches without partial acceptance. Define ordering for equal timestamps. Current GET limit semantics and human read authorization remain.
- Use explicit contract negotiation so an old endpoint that ignores unknown fields cannot be mistaken for a fenced receiver. Deploy receiver first, then worker. Record a bounded old-worker rollout path and retirement condition; never silently fall back from rejected v2 proof to unrestricted legacy append.
- Keep machine writes service-only even when inspecting policy flags, and test human owner/admin refusal plus denied out-of-scope reads. Log endpoints must not mutate mission status, charge tokens, or materialize Reports/Evidence.

The builder chooses the minimal precise schema and records the design before implementation. Tests must demonstrate real PostgreSQL insertion/replay/ownership races as well as SQLite behavior, with the actual request contract shared by both repositories.

## LOG-2: DeepSearch counterpart and visible progress

This is a cross-repository integration mission tracked in TraceLab. The worker work package is concrete; no separate DeepSearch sprint is created over its active S93 and no message is sent by this planning session. When a fresh build session takes the worker side, it must load that repository's instructions and either associate the work with an explicitly agreed local mission or record the TraceLab integration ownership. Do not use S93 model-evaluation authorization for this work.

Required DeepSearch source seams: `deepsearch/worker/main.py`, `deepsearch/tracelab/log_handler.py`, `deepsearch/worker/execution.py` only if forwarded structured metadata needs preserving, `deepsearch/worker/lease.py`, and the existing log/worker/lease tests. The current lease contract is documented in `cmos/reports/sprint_87_m05_tracelab_lease_contract.md` there.

- Enable bounded delivery only after the receiver proves the new contract and the worker has confirmed ownership. Use the existing five-second interval and threshold mechanism where suitable. Give events stable identities before enqueueing; retain the same identity/payload across transport retries. No HTTP delivery may block the research event loop or heartbeat.
- Preserve secret-safe allowlisted events, not raw prompts, traces, URLs, credentials or exception bodies. Render useful phase messages from those enums. Carry child observations through the existing pipe without weakening child cancellation, sandboxing, artifact checks or parent-death behavior.
- On lost ownership, stop new delivery, quiesce in-flight delivery and drain/discard attempt-local pending work according to the contract before release. Receiver rejection is still mandatory for races. Never label prior-attempt observations as the successor's current work. Old tests that require no pre-terminal posts must change to assert the stronger ownership invariant, not simply be deleted.
- Preserve bounded acknowledgement/retry/overflow telemetry. Transient log transport failure does not fail research or lose a paid result; stale-proof failures are not retried as unrestricted writes. Final flush and retry after terminal commit follow LOG-1's identity contract.
- Keep the current model configuration, execution budget, leases, receipt, Ledger and retained paid artifacts unchanged. No model comparison or general logging rewrite.
- In TraceLab, retain five-second polling; distinguish waiting for first logs, recent received observations, a stale gap, refresh failure with retained lines and terminal history. Derive readable phase text only from recognized actual events; unknown/legacy messages remain readable as text. Do not infer percent complete from a timer or log count. Isolate user/mission state, show attempt boundaries as needed, and explicitly refresh once status becomes terminal so the last batch is not missed when polling stops.

Proof starts with deterministic, no-provider cross-service tests using the real client and a controlled lease lifecycle. Test slow research, acknowledgement loss, duplicate/reordered batches, queue overflow, parent cancellation, lease loss/reclaim and terminal flush. Then prepare the deployable commits/configuration and exact live acceptance plan. DeepSearch `agents.md` says **“build sessions land code; deploys + dispatches require explicit user authorization.”** This planning request does not authorize either. Do all local work first and present the concrete worker deployment/paid-run request only when it is ready. LOG-2 owns the authorized live run and its pre-terminal receipt; WALK-4 reuses that evidence and performs read-only final verification rather than requiring another paid run.

## WALK-4: acceptance and closure

Recovery must be exercised through a real delivered email for a dedicated controlled account with an accessible test mailbox: public request → mailbox → link → reset → new-password login; then admin-triggered recovery through the same route. Verify old password/JWT/refresh/query-token/key/device rejection and unchanged access for a separate user and the service principal. Confirm disabled-account denial, expired/replayed links and expected Settings behavior. Agree the concrete mailbox/account before sending or changing credentials; never reset Derek's or another existing user's password merely for a smoke. Disable/revoke the temporary fixture afterward.

For logs, observe at least two separate received batches **before terminal completion**, with server receipt timestamps and a browser observation while the mission is `in_progress`. Proposed healthy-path target: an emitted safe observation becomes visible within **15 seconds** (existing five-second flush plus five-second UI poll with margin); measure delivery lag separately from quiet periods when no new event exists. Verify final lines after terminal status, stable counts on acknowledgement replay, readable attempt attribution and scoped access. An old `logged_at` on a post-completion batch is not live proof.

Use a required, explicitly authorized bounded research run for the production proof; piggyback build-hash verification on it. Prepare the exact mission payload, selected project, model, limit and cost ceiling before requesting dispatch approval. Preserve all outputs and billed attempts; no blind rerun to rescue a receipt. Local/no-provider tests can validate transport mechanics but cannot replace an actual worker run for closing #412. Lack of deployment/dispatch authorization leaves the corresponding acceptance gate open without blocking delivery of already-accepted recovery slices.

Full validation is scoped to changed code: relevant backend/auth/device/notifications/RBAC and OODS contracts; frontend units/types/build; PostgreSQL migrations/concurrency; built-browser Light/Dark at 390/820/1440 with keyboard/focus/axe. Run `node scripts/mcp_parity_audit.mjs` and `python3 cmos/scripts/validate_foundational_refs.py`. If MCP response/handler/package changes are needed, apply the actual deployed-client contract test and clean published-artifact gate. Never silently alter the existing quarantine; report all skips. DeepSearch's known-red tests need comparison against a clean baseline, not silent deselection.

Follow review decision **#562**: isolate mail/model/Qdrant before tests, include schema and immediate consumers early, validate fixtures, preserve failures and retry saved artifacts. Read current branch protection rather than relying on the stale eight-check prose (#464). Receipts under `cmos/reports/sprint-61/<mission>/` identify the actual tested and serving commits, provider acknowledgements versus delivered emails, observed timestamps and all limitations, without secrets.

## Carryovers and handoff

- **#412** is promoted into LOG-1/LOG-2/WALK-4, but remains unresolved until real pre-terminal delivery is accepted. The pending message is historical evidence, not a commitment from DeepSearch.
- **#416** runtime model identity remains a separate carryover. Observe it on the accepted log run and record the result; fix it only if scoped explicitly or required to identify the tested build. Do not bundle a telemetry redesign into logs.
- **#445** global Qdrant test isolation and **#464** CI documentation are validation hazards to accommodate, not unrelated refactors. **#451** retains its recorded 2026-12-01 deployment-config deadline.
- Sharing, pricing, model selection, cache investigations, historical report regeneration and other maintenance remain outside S61. The existing carried entries remain in CMOS rather than being copied into new missions.

Fresh session: run `cmos_review`, read both TraceLab agents files, this handoff and the selected mission's full CMOS criteria. Confirm current source and any new answers, then start **AUTH-1**. The first mission start opens the sprint; run the identity synchronization procedure in the [operations guide](../docs/operations-guide.md). Planning alone must not set the project to `sprint-61-active`.

At close, reverify receipts against final source, record actual outcomes in the roadmap, audit cross-sprint decision ownership (review learning #273), reconcile dashboard parity, complete the session and take a context snapshot. No full-sprint completion while live-log acceptance is still pending.
