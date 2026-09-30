# Sprint 62 — Reliable operations and guided mission creation

Locked 2026-09-30 in planning session **PS-2026-09-30-012**, decision **#576**.
CMOS is authoritative for mission criteria, dependencies and status. This handoff
records implementation boundaries, source observations and acceptance evidence.
Guiding templates: [roadmap](../foundational-docs/roadmap_template.md) and
[technical architecture](../foundational-docs/tech_arch_template.md).
Intent: [living roadmap](../foundational-docs/roadmap-sprints-57-60-the-librarian.md).

## User mandate and current state

Derek explicitly included `hello@aquex.ai` forwarding, reported the new-user
mission-creation dead end, asked whether Librarian should guide authoring, and
prioritized high/critical and medium technical debt over a broad UX redesign.
After reviewing the proposed priorities he said:

> “I agree, lets include it. i'll take your recommendation. Lets lock s62, create the sprint and mission details that will be needed by a fresh build session to run with these.”

The existing S62 shell is now locked, **Planned**, with nine **Queued** missions.
No build mission has started and no start/end dates are invented. Opening a
planning session does not activate the sprint. Decision #576 supersedes the
discussion-only #575. Review decisions #573–574 and learnings #280–283 provide
process and intake context; the user's approval is the warrant for this work.

This planning session creates CMOS records, this handoff, the roadmap entry and
two sourced Evidence Ledger findings. It does not implement, deploy, apply Railway
configuration, send email/cross-project messages, change accounts or dispatch research.
The build session should act under its actual user authorization; do not manufacture
new owner prerequisites or repeatedly ask about product choices settled here.
Prepare any genuinely permission-dependent live action completely before asking.

## Start here in a fresh build session

1. Load root `agents.md` and `cmos/agents.md`. Use CMOS MCP; the v1 CLI references
   in older documentation are superseded by the v2 workspace guidance.
2. Use **`projectRoot=/Users/systemsystems/portfolio/TraceLab`** for every CMOS
   operation. An isolated source worktree is not a separate CMOS project/database.
3. Run `cmos_review`, `cmos_db(action="health")`,
   `cmos_sprint(action="show", sprintId="sprint-62")`, then read the full selected
   mission via `cmos_mission(action="show", missionId="S62-ISO")`.
4. Begin from the planning branch **`codex/sprint-62-plan`**, initially based on
   S61 closeout `09ae685` (runtime ancestor `4495119`). It contains final S61
   receipts required by S62-SCOPE and this plan. The original checkout remains
   `codex/sprint-61-admin-acceptance` at `d0ffd02`; do not build from that stale
   snapshot or switch it under another task. Preserve its two untracked user notes.
   Read current git state and reconcile later accepted main changes normally.
5. Start **S62-ISO** through the mission transition tool. The first mission start
   activates the Planned sprint; perform the
   [Sprint-Boundary Identity Sync](../docs/operations-guide.md#sprint-boundary-identity-sync-runbook).
   Planning leaves project identity at the last completed S61.
6. Enforce the dependency graph yourself: CMOS records ordering but does not
   reject a premature start. Its queue view can suggest S62-CI alphabetically;
   that is not dependency order. Start S62-ISO explicitly.
   Use scoped fresh build sessions as needed, recording
   precise handoffs. Commit at coherent boundaries; do not impose one commit per
   mission unless a real bisection need exists.

## Locked sequence and dependency graph

The order below is the delivery priority. Technical dependencies are deliberately
narrow; a blocked live inbox check need not stop independent locally authorized work.

| Order | Mission | Outcome | Requires | Carried item |
| --- | --- | --- | --- | --- |
| 1 | S62-ISO | Safe test defaults and explicit disposable integration access | — | #445 |
| 2 | S62-CI | Controlled timeout, accurate smoke and current CI guidance | S62-ISO | #397, #446, #464 |
| 3 | S62-MAIL | Real delivery for hello alongside Stage1 | S62-CI | #478 / Aquex request |
| 4 | S62-SCOPE | Evidence-backed scope divergence diagnosis and correction handoff | S62-ISO | #476 |
| 5 | S62-ENTRY | Focused Librarian planning as primary mission entry | S62-CI | New user request |
| 6 | S62-OBS | Useful cache and legacy metrics diagnostics | S62-CI | #444 |
| 7 | S62-UX | Disabled-session exit and keyboard-accessible code | S62-CI | #426, #447 |
| 8 | S62-DEPLOY | Supported Railway config with verified behavior parity | S62-CI | #451 |
| 9 | S62-WALK | Integrated deployed acceptance and honest closeout | All eight above | Final audit |

Do not broaden S62 into full Librarian redesign, sharing/RBAC redesign, a new cache
platform, blanket quarantine cleanup, historical report regeneration, pricing or
model changes, an Aquex connector repair, or an unplanned DeepSearch implementation.

## Source observations that shape the work

Inspection used the final S61 closeout tree `09ae685`, rather than the older
main workspace. These are source/receipt observations, not newly repeated live tests.

| Surface | Observed state | Consequence |
| --- | --- | --- |
| Shared tests | `tests/conftest.py` forces SQL/test environment and a dummy OpenAI key, but Qdrant configuration can come from `.env` | Isolate before invoking application/test imports; patching one RAG caller is insufficient |
| Cache client | `get_qdrant_client` uses global settings; enabled semantic cache initializes and can recreate its configured collection | Demonstrate transport isolation with enabled cache behavior, not only disabled cache |
| CI | Stack dumps already use `faulthandler_timeout=120`; runner ceiling is 45 minutes | Add an earlier controlled stop, preserve existing diagnostics |
| Browser smoke | Suppresses exact PUT `/activity/viewed`, omits `/activity/viewed/evidence` | Add only the expected local fulfillment; retain the no-write fence |
| Mission entry | Home, Missions and command palette link to `/missions/new`; MissionForm requires a project without creating one | Point fresh-create entry at guided planning and preserve advanced forms |
| Librarian | Planning-only conversation and inline project creation already work; four project tool panels precede conversation | Reuse the existing service and hide unrelated panels only in focused entry |
| Session handling | Backend disabled-user response is 403; shared frontend logout handles 401 | Match the specific disabled-account response, never every 403 |
| Markdown | Table wrapper already has `tabIndex=0` and region labeling; code `pre` lacks focusability | Preserve tables and fix/verify the remaining code-block gap |
| Metrics | Old `/admin/dashboard/data` uses MetricsAggregator; current Observability uses a separate stats service | Reproduce the old endpoint fault without labeling the new page broken |
| Deployment | Root/frontend `railway.json` carry build/start/health behavior; root startup runs Alembic before uvicorn | Migrate effective settings without losing migrations or unrelated infrastructure |

## S62-ISO — test isolation

Scope the fix to test infrastructure and its immediate configuration consumers.
Force safe values before importing application settings and cached client factories;
a post-import monkeypatch can be too late. Inventory nested conftest files, startup
hooks, direct Qdrant construction and semantic-cache factories. Preserve ordinary
offline/unit paths and the existing isolated PostgreSQL integration setup.

Use fakes or disposable local resources by default. A deliberate integration opt-in
must name an isolated local/testcontainer resource and collection lifecycle; an
arbitrary endpoint plus a flag must not bypass the protection. Retain current
mail/model fakes. Do not fix this by disabling all cache tests or weakening their
assertions.

The decisive regression loads production-like sentinel environment values in an
isolated process and exercises real settings/client construction with transport
intercepted. No real production access is needed. Include the enabled cache
constructor/write path and singleton/import ordering. Record representative backend,
RAG/cache, SQLite and integration setup results before broad CI.

Read: `tests/conftest.py`, `app/core/config.py`,
`app/core/qdrant_client.py`, `app/services/semantic_cache.py`,
`tests/test_rag_service.py`, `tests/test_caching.py`,
`tests/test_qdrant_prewarm.py`.

## S62-CI — useful, trustworthy validation

Retain the existing 120-second stack dump and add a controlled failure deadline
with time left before the 45-minute runner kill to collect evidence and clean up.
Choose the smallest mechanism supported by the project. A subprocess fixture that
intentionally hangs must show the stuck test/stacks and return nonzero. Verify the
success and normal-failure paths and pipeline exit handling, not only YAML presence.

In `frontend/scripts/ui-shell-smoke.mjs`, fulfill the exact Evidence viewed request
locally in both execution branches, as with the existing activity request. Keep
unrelated mutations rejected. Do not grant a broad PUT exemption or send this
expected write to production merely to make the smoke green.

Read current branch protection before updating `.github/ci/README.md` and
`cmos/agents.md`. S61 recorded nine required checks; never turn that historical
count into a substitute for a fresh read. Preserve the 12-node quarantine unless
a directly repaired test has verified intent and an explicit ratchet update.
The ten historical telemetry evaluators are not a blanket cleanup assignment.

## S62-MAIL — two supported inbound addresses

Request: CMOS message **678bc33a-cf00-42fa-847f-f43bb318297a**, from aquex.ai,
dependency for its S12-M04 contact-link change. Read its complete body at build
intake. The user has included this feature; the foreign message remains evidence
about requested behavior, not independent authorization to send replies.

Use the existing route and service:
`app/api/v1/webhooks.py`, `app/services/support_inbox.py`.
Keep `SUPPORT_FORWARD_TO`, `RESEND_FROM_ADDRESS`, inbound credentials and MX/DNS.
The allowlist is exactly `stage1@aquex.ai` and `hello@aquex.ai`.

Parse actual mailbox addresses across to/cc/bcc. Do not retain substring matching
that accepts a display-name mention or a lookalike mailbox. Derive the unique matched
set from the signed webhook, pass it into forwarding, and use a stable configured
order in the subject/intro. This preserves labels for bcc even if the fetched message
does not include that field. Dual-address mail produces one send.

Keep the existing **`stage1-support-<email_id>`** idempotency namespace; changing its
name would let a retry spanning the release use a different key. Preserve signed-URL
attachments and existing reply destination handling, with the sender fallback
tested. Svix rejection, missing-config 503, failed-forward 502, body/address-free
logs and Stage1 behavior remain part of acceptance.

Extend `tests/test_support_inbox.py`: it currently explicitly asserts hello is
ignored. Cover hello/Stage1/both, cc/bcc, display-name and unrelated-address negatives,
redelivery, provider failure, attachments and secrecy through the actual webhook.

A real deployed hello email must arrive at the forward destination with the correct
Reply-To. Prepare the controlled sender/message/inbox check and distinguish that
receipt from Resend acceptance. Reuse it at S62-WALK. Prepare the Aquex completion
summary, but do not send cross-project messages without explicit user instruction.
Aquex owns switching its contact link.

## S62-SCOPE — bounded saved-run diagnosis

This is a diagnostic mission, not an open-ended execution or billing redesign.
Reuse mission **3f5c2641-7a47-45ed-a092-feebe9143ed1** /
**S61-LOG2-ACCEPT-01**, and `cmos/reports/sprint-61/LOG-2/`:
`proposed-mission.json`, `contract-preview.json`,
`worker-structural-contract.json`, `deployed-acceptance.json` and `README.md`.

Map authored intent through persisted fields, TraceLab's vendored compiler,
saved structural/worker contracts, observations and output. Separate a preferred
reference set from an enforced source allowlist. Compare 300–500 requested words
with 2,285 whitespace-counted output words (worker count 2,240), 22 collected sources
with two final references, and the actual quality warnings. The recorded 519,007
tokens are usage, not an observed dollar bill; the former $5 allowance was not a
hard limiter.

Deliver the first demonstrable divergent boundary and a no-provider reproduction
where possible. If evidence is insufficient, name the exact missing observation,
show competing hypotheses and assign the next evidence collection task. “Probably
the model” does not satisfy diagnosis. Preserve contradictory output claims.

Use existing TraceLab/vendor source and retained/read-only accessible artifacts.
Do not modify or inspect another repository under an assumption of permission.
If the correction belongs to DeepSearch, create a precise local handoff with owner,
regression and acceptance criteria. Do not send it, deploy a worker, change model
configuration or rerun paid research. Any eventual authoring-field fix must follow
`cmos/contracts/mission-authoring-contract.md` and the compiler vendor contract;
it is not implicitly part of this diagnostic mission.

## S62-ENTRY — focused mission planning

The settled product direction is **Plan a mission** as the primary Home, Missions
and command-palette action, targeting **`/librarian?intent=mission`**.
Use the existing Librarian page/service with a focused presentation, not another
chat backend or a full-page redesign.

Keep the user journey visible:

**Describe the question → choose/create project → review/refine draft → create
draft → explicitly submit from the mission page.**

Conversation may begin without a project. Use existing inline project creation
before requesting the draft; preserve personal-Space defaults and the explicit
shared-Space picker. Do not create a default project merely by visiting the page.
The focused view presents the conversation, destination and draft; descriptions,
duplicate reviews, collection suggestions, report assembly and alternate reply
modes stay on the general Librarian surface.

Retain per-user conversation persistence and navigation recovery. Opening planning
must not silently erase a saved conversation. Project change/revocation must not
leave a draft that saves under the wrong destination. Recheck permissions on the
server; do not rely on a previously populated selector. Preserve corpus provenance,
draft validation, idempotent creation and the separate paid-submit boundary.

Show objective, success criteria, scope and deliverables for review. Conversational
refinement/regeneration remains sufficient; a new structured draft editor is not
required. Retain a secondary **Create manually** link to `/missions/new`. That
direct path needs a useful guided-planning escape for zero-project users.
Preserve `?from=`, `?collection=`, edit/preview and source context. Do not globally
redirect `/missions/new` or silently clear populated inputs.

Normal `/librarian`, `?project=`, `?q=` and `?saved=` links retain their behavior.
Resolve conflicting query intent explicitly and test it; a saved search must still
open as search. Use existing UI primitives and user-facing language, not internal
contract JSON as the onboarding explanation.

Read the mission's full reference list, especially `librarian.tsx`, storage,
MissionForm, CommandPalette, SpacePicker and server Librarian tests.
Built-browser acceptance must start with a genuine zero-project non-owner fixture.
Cover both entry pages, inline creation, focus, failure/retry, reload/user isolation,
draft review and no run on create; also exercise preserved seeded/manual paths.

## S62-OBS — cache and metrics diagnosis

Treat #444 as two claims: an old metrics endpoint returned 500, and the semantic
cache was unexpectedly empty at a particular historical observation. Neither
proves that the current Observability page fails or that the same cause persists.

Reproduce the relevant endpoint using `app/services/metrics_aggregator.py` and
`tests/test_admin_dashboard.py`. Use real cache serialization with an isolated
transport; do not let permissive mocks conceal payload incompatibilities.
Fix the smallest evidenced defect and expose safe error categories for cache
lookup/write/maintenance. Preserve fresh-answer fallback and scope/citation checks.

Failures must be visible without logging prompts, message bodies, embeddings,
secrets or private URLs. Process-local counters must say so. A dependency outage
should leave available metrics useful and identify the unavailable part, rather
than converting uncertainty into zero or “healthy.” Keep rolling-window tests
time-controlled where applicable. Do not empty production cache to reproduce an
old observation. Record an honest current fix versus historical evidence gap.

## S62-UX — two narrow defects

For #426, reuse `apiRequest`'s existing logout event and stored-auth clearing only
when the response identifies **Account is disabled**. A project permission 403 must
not sign the user out. Parse response content once and preserve normal error
reporting for malformed/unrelated responses. Test in-memory AuthContext as well as
local storage and visible user-scoped content.

For #447, `MarkdownRenderer` already gives tables a focusable labeled region.
Verify that behavior and address code blocks that actually overflow. Provide keyboard
scrolling, visible focus and appropriate labeling without modifying document prose
or copy behavior. Both changes require unit and production-build browser evidence.
Use disposable accounts for live disabled-session checks; leave existing users,
owner and service credentials alone.

## S62-DEPLOY — supported configuration, same behavior

The cutoff was reconfirmed on 2026-09-30 in
[Railway's Config as Code documentation](https://docs.railway.com/config-as-code):
legacy files stop being read on **2026-12-01**. Evidence Ledger finding
**568aca7f-b47b-41a8-846f-3a20fec75530** belongs to TraceLab Engineering project
**5229e75e-8ad3-4ac5-94de-093a177562c6**.

[Railway's IaC migration guide](https://docs.railway.com/infrastructure-as-code)
supports scoped ownership and reviewed migration plans; whole-project ownership
can delete omitted resources. Finding **98bcde7f-97a9-4ad3-a55b-6a7f1edb428c**
records that constraint. Recheck current CLI semantics before implementation.

Inventory the exact two services and their effective behavior, rather than merely
translating tracked JSON. Preserve backend migration-before-start, frontend build
and start commands, root/config paths, health checks, restart policy, replicas and
existing resource references. Never commit secret values.

Prepare explicit ownership and a saved before/after plan. Unrelated databases,
volumes, variables, domains and services must not be deleted/recreated. Resolve
legacy ownership in a controlled migration sequence, with rollback ready before
applying. Generated output is an input to review, not proof of equivalence.
Do not bundle a builder migration into this work without demonstrating necessity.

Acceptance requires actual deployment, effective-config readback, serving revision,
backend Alembic startup evidence, frontend health/build and authenticated smoke.
A repository file or successful plan alone is incomplete. New tooling belongs at
the repository root in the established package layout; update relevant lockfiles.
Apply DoD-2 to any new server variable. Preserve the deadline if rollout remains open.

## Validation and closure

Each mission stores receipts in `cmos/reports/sprint-62/<mission-id>/`, recording
tested source, actual serving version where relevant, failures and corrected runs,
pass/skip/quarantine counts, and remaining uncertainty. Use S62-ISO protections
before application tests. Never load production credentials into a test merely to
make a suite pass.

For runtime changes, run relevant pytest and frontend tests; include real PostgreSQL
when persistence/locking behavior changes. Use production-build browser tests for
UI, Light/Dark at 390/820/1440, keyboard/focus/axe, empty/loading/error/revoked states.
Run `node scripts/mcp_parity_audit.mjs` and
`python3 cmos/scripts/validate_foundational_refs.py`.
Read current required CI checks. Do not run `ruff format`.

No MCP surface expansion is planned. If implementation changes a client verb,
schema/serializer or installable package, the actual deployed-client contract
regression and clean packed/published-artifact smoke gates still apply. Preserve
REST-only classification for existing conversational authoring.

S62-WALK reuses the real email receipt and performs the final first-use journey,
diagnostic/config checks and source audit. Proving a saved draft does not require
dispatching a DeepSearch run. Stage operator interactions as one clear request with
the exact fixture and action (learning #280). Do not repeat S61 credential resets.

At close, require all mandatory acceptance gates; distinguish S62-SCOPE's completed
diagnosis from an unresolved correction. Update roadmap outcomes, read back CMOS
statuses, audit explicit decision ownership, synchronize identity only on actual
activation/closure, reconcile dashboard parity, complete the session and snapshot.
The S61 closed sprint and its accepted receipts stay intact.

## Carryover disposition

Ten existing next-steps are carried explicitly to S62 and remain unresolved until
their mission proves the relevant outcome:

| Next-step | Owner |
| --- | --- |
| #445 | S62-ISO |
| #397, #446, #464 | S62-CI |
| #478 | S62-MAIL |
| #476 | S62-SCOPE (diagnosis only; correction may need a successor) |
| #444 | S62-OBS (preserve any historical evidence gap) |
| #426, #447 | S62-UX |
| #451 | S62-DEPLOY |

The other **13** recorded carryovers are outside this sprint:
#400/#403/#407 sharing; #406 raw ledger claim presentation; #415 pricing;
#422 source language preference; #431 child Space-column drift; #448 dev-only
theme tests; #449 unrelated architecture-doc drift; #450 dead props; #452 context
size; #454 historical hub pin; #477 older Aquex connector routing.
Do not close those on the strength of this plan or treat historical observations as
fresh production facts. Escalate a newly demonstrated critical issue with evidence
and a scoped backlog change, rather than quietly adding a redesign.
