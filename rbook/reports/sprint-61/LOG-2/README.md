# LOG-2 live acceptance and retirement

The authorized worker/UI acceptance **passed** on 2026-09-30. Exactly one paid
mission completed on attempt 1: `S61-LOG2-ACCEPT-01`, UUID
`3f5c2641-7a47-45ed-a092-feebe9143ed1`. Two independently received batches were
observed while status reads before and after each log read were `in_progress`.
The browser displayed the first four observations within **10.627 seconds** of
their earliest emission, then correctly showed a quiet interval and all **12**
terminal lines without manual log refresh. The worker's reported source-tree hash
exactly matched the tested source. The [deployed receipt](deployed-acceptance.json),
[HTTP snapshots](receipt-snapshots.json), and [browser observations](browser-observations.json)
record the evidence and its limits. Legacy retirement is deployed and verified
on both services at `4495119`; LOG-2's acceptance gates are complete.

This package follows the [Sprint 61 handoff](../../../planning/sprint-61-HANDOFF.md)
and [mission log contract](../../../contracts/mission-log-delivery-contract.md).
The [rollout checkpoint](rollout-progress.json) preserves the earlier safe hold:
unrelated paid work began during the first worker build, so that deployment was
canceled before replacing the worker. After that work completed and the user
signed in, deployment `17053355-f5a5-43b2-90d3-bbb4a75850e0` succeeded with all
12 preflight checks passing and unchanged effective configuration.

## Exact changes

| Slice | Branch / commit | State |
| --- | --- | --- |
| Accepted receiver | TraceLab `55b5da6a7cc2334350aa40a251d0c479a3c96914` | Receiver preserved in serving `56aae006`; schema 058 |
| Worker | DeepSearch PR [179](https://github.com/kneelinghorse/DeepSearch.alpha/pull/179), merge `5a75502727b889aa4a65a6373df4b74aa36da23b` | Identical tree to tested `849389e`; deployed and accepted |
| UI and real HTTP proof | TraceLab PR [405](https://github.com/kneelinghorse/TraceLab/pull/405), merge `56aae00673dda2c500edf41ab4aef3296d24a784` | All required CI passed; serving verification in rollout receipt |
| Legacy append retirement | [PR #406](https://github.com/kneelinghorse/TraceLab/pull/406), `4495119551c67a39b393b40f0e0d176ea84128ba` | All nine required checks passed; both services serve the merge; live refusal/history checks passed |

Observed worker source-tree hash (exact match):
`fa31cba8cf6f88fe4c32980ecd1c2dee6b704b0ee8e5e3747823b7c935c04bcc`.
It was read from the paid mission's `runtime_identity`, with
`build_source=source_tree_hash`, `git_dirty=false`, and `model=deepseek-flash`.
This verifies #416 for this run; it does not repair historical telemetry.

The worker now negotiates v2 after ownership confirmation and heartbeat startup,
uses stable event identity and complete acknowledgements, and quiesces delivery
before release/requeue. Its existing lease/child/artifact fences and model budgets
remain intact. The UI displays actual receipt freshness, attempts, quiet gaps,
retained errors and late terminal observations without estimating progress.

## Evidence

[local-validation.json](local-validation.json) contains source hashes, baseline
failures, resolved test failures, explicit skips/limitations and screenshot hashes.
[receiver-readiness.json](receiver-readiness.json) records the 2026-09-30 production
read: both TraceLab services serve `55b5da6`, healthy RBAC/receipt configuration,
and service-authenticated v2 capability negotiation succeeds. No worker deploy or
research dispatch was performed by these probes.

- Worker: **161 passed, 2 known baseline failures**, zero skips/deselections. The
  same two frozen S87 readiness pins failed before changes; no historical evidence
  was rewritten. Four pre-existing N806 test naming findings also remain unchanged.
- Receiver plus real cross-service HTTP: **42 passed**, zero skips. Actual sender,
  service API key, uvicorn receiver and SQLite transactions prove sparse five-second
  delivery, two preterminal batches, 503 retry, lost acknowledgement replay, final
  flush, stale rejection and bounded successor overflow. These are no-provider
  fixtures, not production worker acceptance.
- Frontend: **313 unit tests** and **14 production-build browser tests** pass.
  Six Light/Dark 390/820/1440 cases include keyboard/scroll, no overflow, no serious
  or critical axe findings, quiet gaps, retained refresh errors and revoked access.
  [Screenshots](screenshots/) are local fixture evidence.
- Final retirement: **190 receiver/RBAC/real cross-service tests** pass, zero skips, 16 warnings (57.99 seconds). Initial full CI exposed eight stale legacy201 expectations outside the first107-test selection; these now assert426/no insertion while preserving role-boundary checks.
  The worker negotiates `legacy=retired`; legacy POST returns 426 after authorization.
- Production build, frontend lint/types, changed-file credential checks, foundational
  references and MCP parity pass. All nine required TraceLab contexts passed
  before PR405 merged: backend 3,074 passed / four skips / 12 unchanged quarantined
  deselections; PostgreSQL 169 passed / two skips; production browser 82 passed.
  The external-checkout cross-service test accounts for the additional CI skip.
  DeepSearch has no remote checks configured; its local results above are retained
  explicitly, including the two baseline failures.

The external-checkout cross-service test explicitly skips without
`DEEPSEARCH_SOURCE_ROOT`; release verification must execute it with that variable:

```sh
DEEPSEARCH_SOURCE_ROOT=/path/to/DeepSearch.alpha python -m pytest tests/test_live_log_cross_service.py
```

No MCP request/response surface changed in LOG-2. The accepted LOG-1 receipt already
covers the actual published MCP client against production; the actual published `@aquex/tracelab-mcp@2.1.0` read matched all 12 deployed rows, preserving attempt/event fields and excluding proof fields ([receipt](published-mcp-read.json)).

## One-run scope and cost

[proposed-mission.json](proposed-mission.json) is schema-validated and was created
once as draft UUID `3f5c2641-7a47-45ed-a092-feebe9143ed1`, submitted exactly once, and completed.
Both the deployed structural preview and the current worker's no-provider
structural compiler were inspected. It selects existing **TraceLab Engineering** project
`5229e75e-8ad3-4ac5-94de-093a177562c6`: a 300–500 word comparison of PostgreSQL
transaction/statement/wall-clock timestamps, using two official documentation
pages and one worked lease-lock timeline. One explicit submit only; preserve
all artifacts and billed attempts. Do not dispatch again just to repair evidence.

Keep production `LLM_BACKEND=deepseek`, `DEEPSEEK_MODEL=deepseek-flash`, and all
other provider/lease/budget settings unchanged. The existing default is 40
CodeAgent steps and 32,768 output tokens per request, with existing bounded
same-memory recovery and zero-usage transient requeue rules. `max_loops` is inert
on this path and is deliberately not presented as a spend control.

Authorized planning allowance: **$5**. An illustrative conservative usage envelope
of 10 million uncached input tokens, 1 million output tokens, and 100 standard
search requests costs **$4.80** using peak Flash rates and assuming $0.006/search.
This is arithmetic for review, not a prediction or enforced ceiling. Flash peak
rates are $0.30/M input and $1.20/M output; Linkup's public Search range is
$0.005–$0.006/request. Recheck account pricing before dispatch. Sources:
[DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/) and
[Linkup pricing](https://www.linkup.so/pricing). Findings were captured in the
project Evidence Ledger (IDs in the JSON receipt).

**The production worker has no hard dollar limiter.** Authored word/source limits
are task scope, not enforced billing limits. The user accepted this limitation in
the authorization to proceed. Public prices were rechecked before the rollout;
account-specific discounts and the eventual billed total remain unverified.
No new budget mechanism is included in this logging change.

## Observed outcome and final verification

Full research Markdown (15,440 characters) and the five-chunk processed/embedded
document remain available. The existing materializer also produced a 529-character
protocol summary report with five sources and `citation_status=legacy_unavailable`;
this is not a claim of durable report citations. The Ledger retained 24 entries
(four supporting, 20 background). The published MCP log read matches the HTTP rows.

Model accounting observes 519,007 tokens across 24 requests including contract
compilation (492,325 input / 26,682 output); the legacy synthesis/critique total is
513,840. Two web searches and 15 source-fetch calls are recorded. **Actual billed
dollars are unavailable**; the $5 allowance remains a planning allowance, not a
measured charge or hard limit.

The research output exceeded its authored scope: 2,285 whitespace-separated words
(worker count 2,240), 22 collected sources across seven domains, and warnings
`critique_assessment_partial` / `retrieval_failures_2_source_fetch`. Its final
references are the two requested official pages, but prose claiming no third
source was consulted overstates the collection telemetry. Preserve these artifacts
and investigate compiler/output scope separately. No second paid run is authorized
or needed for logging evidence.

The healthy production run demonstrates live delivery and retained artifacts.
Lost-ack replay, failures, stale ownership and multiple-attempt separation are
covered by the real cross-service tests and LOG-1 deployed synthetic proof; this
run was not deliberately disrupted. The terminal read stayed at 12 rows.

Legacy retirement is deployed on both TraceLab services at `4495119551c67a39b393b40f0e0d176ea84128ba`.
The [live refusal receipt](retirement-verification.json) confirms capability
`legacy=retired`, service426, human403, anonymous401 and unowned v2 rejection409.
The 12 accepted observations remain byte-for-byte unchanged; the published MCP
reader returns the same rows. No research was dispatched by these checks.
[Final CI](../WALK-4/final-validation.json): backend 3,074 passed / four skipped /
12 unchanged quarantined deselections; PostgreSQL 169 passed / two skipped;
82 production browser tests passed. The initial eight stale legacy201 assertions
were corrected before this required-check pass; their failed run remains recorded.
WALK-4's recovery matrix is accepted; no further user-assisted reset is needed.

## Rollback

Before retirement, revert worker code to `8465fab` and the UI slice to accepted
`55b5da6` if needed, after safely quiescing current work. Keep schema058, accepted
history, terminal artifacts and the v2 ownership fence. The old worker is
terminal-only; never enable unfenced live fallback. It may be unable to append
legacy lines to a mission already containing v2 history, which intentionally
preserves attribution; research results remain retained.

After retirement, restore the receiver's transitional compatibility commit
before reverting the worker, or keep the v2 worker and fix forward. Never roll
back schema058 or delete accepted observations to make old appends succeed.

DeepSearch [agents.md](../../../../../../sprint-61-worker-logs/DeepSearch.alpha/agents.md)
requires: “build sessions land code; deploys + dispatches require explicit user
authorization” and forbids pushing commits without explicit user OK. The user's
2026-09-30 “authorized, proceed” satisfied this gate for the prepared package.
That authorization persists and the worker/browser hold was resolved. No S93
evaluation approval or prior paid result was reused.
