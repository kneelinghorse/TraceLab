# LOG-2 readiness and rollout checkpoint

LOG-2 is **not complete**. The user authorized publishing, deployment and the one
paid acceptance run on 2026-09-30, including the disclosed $5 planning allowance
without an enforced dollar cap. Both PRs are merged. The worker rollout was
canceled before replacing the old worker because unrelated paid research began
during its build. Resume only in an idle window and with an authenticated browser
ready to capture live evidence. WALK-4, #412 (live delivery), and #416 (observed
runtime identity) remain open. [rollout-progress.json](rollout-progress.json)
records the exact checkpoint. This package follows the [Sprint 61 handoff](../../../planning/sprint-61-HANDOFF.md)
and [mission log contract](../../../contracts/mission-log-delivery-contract.md).

## Exact changes

| Slice | Branch / commit | State |
| --- | --- | --- |
| Accepted receiver | TraceLab `55b5da6a7cc2334350aa40a251d0c479a3c96914` | Receiver preserved in serving `56aae006`; schema 058 |
| Worker | DeepSearch PR [179](https://github.com/kneelinghorse/DeepSearch.alpha/pull/179), merge `5a75502727b889aa4a65a6373df4b74aa36da23b` | Identical tree to tested `849389e`; deployment held |
| UI and real HTTP proof | TraceLab PR [405](https://github.com/kneelinghorse/TraceLab/pull/405), merge `56aae00673dda2c500edf41ab4aef3296d24a784` | All required CI passed; serving verification in rollout receipt |
| Legacy append retirement | TraceLab `codex/sprint-61-retire-legacy-logs`, `dc9787dffa5ca4389ee5c4bd7c13261d70ec94ff` | Separate local commit; hold until worker acceptance |

Expected worker source-tree hash:
`fa31cba8cf6f88fe4c32980ecd1c2dee6b704b0ee8e5e3747823b7c935c04bcc`.
This is a local fingerprint, **not a newly observed deployed runtime identity**.
The current reported production worker commit is `8465fab0564a9847ded70593e7b9f59e99a1e29e`;
its computed source hash is `6adab231174a3d7c20fce2aa3f31ea627a7a6070f980bae638e81b8ce6e603dd`.
Do not count a Railway success label as runtime hash verification.

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
- Held retirement: **106 receiver/RBAC tests + 1 real cross-service test** pass.
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
covers the actual published MCP client against production; rerun its authorized
logs read during the required live mission to verify the final observations.

## Proposed one-run scope and cost

[proposed-mission.json](proposed-mission.json) is schema-validated and was created
once as draft UUID `3f5c2641-7a47-45ed-a092-feebe9143ed1`. It is **not submitted**.
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

## Authorized rollout and live receipt

1. With explicit approval, publish the UI/worker branches, create reviewed PRs and
   pass current required CI. Do not publish the retirement branch yet. Confirm no
   unrelated active paid run will be interrupted before deploying the worker.
2. Merge/deploy UI and worker while keeping the already accepted v2 receiver and
   transitional terminal-only legacy route. Confirm TraceLab serving commits and
   worker deployment source, unchanged effective config, healthy preflight and
   fresh heartbeat. No new server environment variable is required.
3. After the paid-run allowance is approved, create exactly the proposed draft,
   inspect its compiled contract, then submit once. Record the assigned UUID and
   actual selected config. Start API receipt sampling and the real browser view
   before submission so initial batches cannot be missed.
4. Save at least two distinct receiver snapshots while status is `in_progress`,
   with event IDs, attempts, emitted `logged_at`, received `created_at`, observation
   capture time and browser evidence. Measure emitted-event-to-display delay
   against the proposed healthy-path 15-second target. Quiet intervals are not
   delivery lag. Retained terminal-only history cannot satisfy this gate.
5. On the same run, record terminal final-flush visibility, stable history on
   re-read/replay, result/report/ledger preservation, actual usage/cost, and
   `runtime_identity.build_hash` plus its source. Require the exact expected
   source-tree hash when source-tree hashing is reported; handle other identity
   mechanisms explicitly. This piggybacks #416 verification on the required run.
6. Only after that receipt passes, publish/rebase the held legacy-retirement
   commit, resolve the additive contract-doc overlap, run required CI, deploy and
   verify capability `legacy=retired`, service legacy426 and human403/anonymous401.
   Use an unowned/controlled fixture for refusal; do not rerun paid research.
7. Complete LOG-2 and perform WALK-4's remaining credential and final serving-build
   audit. Reuse this paid receipt. Do not close Sprint 61 or #412 before acceptance.

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
That authorization persists; the current hold is an occupied worker and missing
browser session. No S93 evaluation approval or prior paid result is reused.
