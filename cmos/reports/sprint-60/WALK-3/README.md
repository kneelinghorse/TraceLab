# WALK-3 — deployed Librarian arc acceptance

The complete Librarian journey passed on deployed `295028c8f8b7e7fa0b160be49321f53099b1951a` as a dedicated temporary **member**. This is agent acceptance, not Derek's personal walkthrough. The account was selected under the standing controlled-fixture scope; no reply to the optional preference question was assumed. Its API key is revoked and the account disabled. Existing guest credentials and unrelated research were untouched.

This receipt follows the [Sprint 60 handoff](../../../planning/sprint-60-HANDOFF.md), [living roadmap](../../../foundational-docs/roadmap-sprints-57-60-the-librarian.md), and receipt/identity runbooks in the [operations guide](../../../docs/operations-guide.md). Decisions #559–560 and learning #270 record the acceptance and carry boundaries. [PR #399](https://github.com/kneelinghorse/TraceLab/pull/399) merged as `58269adb6c4409c73e3a84a58aefbbe7d4466ff5` after all nine live-required checks passed. Its runtime trees are identical to the accepted build; final serving and CMOS closure evidence is recorded below at closeout.

## Real production journey

[progress.json](progress.json) records exact caller/project/source identities, requests, preview text, hashes, assertions and cleanup. [The harness](deployed_acceptance.mjs) asserts both serving commits before every mode, uses actual API responses through the real deployed browser, and stores credentials and signed proposals privately outside the repository. It never replaces model/API responses with fixtures. Only the controlled uploaded source documents are synthetic.

- Empty project: general planning conversation, a compiled mission preview, and explicit creation of one draft mission. The separate **Submit to DeepSearch** control remains enabled; no submission or paid research run was sent. Replay returns the same mission.
- Empty and populated descriptions: inspected planning/corpus drafts, explicit acceptance, recorded member provenance, then guarded restore to the original descriptions. Generation changes no artifacts.
- Duplicate review: the exact A/copy pair was compared, keyboard focus returned correctly, and dismissal survived reload. Full artifact snapshots stayed unchanged.
- Organisation: inspected two suggested groups, renamed one, excluded the duplicate, dismissed the other and accepted exactly two ordered chunks. Replay returns the same collection; save makes no model call. Existing collection destination behavior remains Default Workspace and is displayed, per decision #555.
- Report: explicitly reviewed both complete excerpts (5,133 characters), generated and inspected the cited synthetic report, exercised the changed-input save guard, saved once, reloaded, opened each exact citation by keyboard and exported Markdown/JSON/text. The content is byte-identical to the preview and citation objects match field-for-field in order. Repeated acceptance returns the same Report and preserves later manual title edits.
- Q&A: the answer identifies project/destination labels beside uploads and cites the actual A/C chunks. An unrelated Kubernetes question is refused with no evidence or provider usage. Ranked chunk search saves all three results as a collection only after the explicit save action.

Retained artifacts: [reviewed collection](https://tracelab.aquex.ai/collections/812075e7-a8bc-4654-86fc-d27e13d164a0), [reviewed Report](https://tracelab.aquex.ai/reports/18545204-bdc7-43ec-8799-c3b6726c9d35), and [unsubmitted mission](https://tracelab.aquex.ai/missions/9bd0493f-cdd2-443e-b8c3-4ee9161642a1). Access still follows existing authorization. The Report's Evidence panel is a separate relationship view; its empty state does not invalidate the numbered source citations.

## Scope, persistence and accessibility

All **30 deployed page checks** passed: Librarian, ranked chunks, collection, Report and mission across Light/Dark at 390/820/1440. Each checked serious/critical axe violations and overflow; none occurred. Twelve additional keyboard Report-source visits opened the exact expanded chunks. Project switching, account switching, source navigation, reload and focus preserve only the appropriate user's/project's state. Usage totals remain unchanged. Expected activity-viewed writes name only the controlled Report/mission; the harness validates rather than suppresses them.

All 30 screenshots are retained alongside the receipt. Visually inspected examples include [Light mobile Report](deployed-report-light-390.png), [Dark desktop Report](deployed-report-dark-1440.png), [Dark mobile collection](deployed-collection-dark-390.png) and [Light mobile Librarian](deployed-librarian-light-390.png).

Live negative probes denied foreign projects, forged source IDs, wrong caller/project and invalid tokens. A soft-deleted duplicate source refused drafting before model work and was restored unchanged. Revoking the dedicated member's grant to the isolated owner-owned source Space denied both source read and drafting. A stale description proposal preserved a newer manual edit. Report retry preserved a manual title and created no duplicate. Temporary edits were restored; no real research was deleted or altered. All negative probes added zero model usage.

## Published MCP and prior receipts

The registry's current **@aquex/tracelab-mcp 2.1.0** started with `npx` in an empty working directory and exposed 9 tools / 50 actions. Actual member calls passed cited ask, refusal, foreign-project denial, ranked knowledge search, collection retrieval and exact Report retrieval. Ask reused the UI question and service; this is not a claim of an additional provider generation. No MCP source or package release changed in Sprint 60.

All five earlier production receipts were rechecked read-only on the accepted commit: [REPORT-1](reverify-report1.json), [LIB-3](reverify-lib3.json), [DUP-1](reverify-dup1.json), [ORG-1](reverify-org1.json), [LIB-4](reverify-lib4.json). Source/collection/description/citation/export assertions still hold. The [reference audit](receipt-reference-audit.json) resolves 55 cited paths and 14 test/module references and records the live mechanisms behind decisions #551–560. Historical test counts remain historical; current totals are measured below. No mechanism required supersession.

## Verification and preserved failures

- [Current accepted-build CI](ci-accepted-build.json): every run passed. [Fresh log counts](ci-accepted-results.json): **2,988 backend passed / 3 existing skips / 12 quarantine deselections**, **150 PostgreSQL passed / 2 existing skips**, **82 production browser cases**.
- Local [frontend units](frontend-unit.log): **291 passed**; [types](frontend-types.log), [lint](frontend-lint.log), [production build](production-build.log) passed. [Built-browser suite](built-browser.log): **88 passed**, including the six durable-citation cases beyond CI's 82.
- [MCP parity](mcp-parity.json) and [foundational references](foundational.log) pass. No migration, dependency, environment variable or runtime source change is part of WALK-3.
- The full local backend first run had 2,987 passes and one configuration failure: the loopback Qdrant URL inherited a local API key, correctly triggering the HTTPS guard. [Original log](backend-first-run.log). Clearing the key fixed that case. The second run passed all 2,988 normal tests but the harness incorrectly retained inline quarantine comments, so all 12 known quarantined cases ran and failed. [Preserved log](backend-quarantine-parser-failure.log), with generated test JWTs redacted. The corrected exact-CI invocation [passed 2,988 tests, 3 existing skips and exactly 12 deselections](backend-final.log) in 704.91 seconds. Captured SQL/application noise is omitted from the quarantine-parser failure log; all twelve assertion traces and the final result remain.
- The first mission-route assertion omitted the existing `?from=librarian` suffix; [original failure](first-mission-route-check.log). It resumed from the existing mission after fixing pathname comparison.
- The first saved-citation assertion hashed JSON property order; [original failure](first-citation-order-check.log). Every field and value already matched. Deep equality now preserves citation array order without treating object-key order as content. It resumed from the existing Report without regeneration.

The three backend skips require external embedding/OpenAI/Qdrant services; the two integration skips require an opt-in live RBAC endpoint and authenticated ingestion CLI server. The 12 quarantine exclusions are unchanged and disclosed in `.github/ci/backend-quarantine.txt`. No failure was hidden by adding exclusions.

## Remaining boundaries

Next-step #405 is closed only for retaining Report plus original result Documents and shipping durable, honestly scoped citation support. Historical reports were not regenerated and missing legacy mappings remain unavailable. Citation identity/coverage checks do not prove semantic entailment.

Twenty-one existing maintenance entries were carried to Sprint 61's backlog without becoming its AUTH-1/AUTH-2 mission scope. A separate documentation follow-up records that [live branch protection](required-checks.json) now requires nine checks, including mcp-package; older policy docs still say eight/advisory. The live nine governed this merge. They include DeepSearch live-log/runtime-identity follow-ups (#412/#416, message `1621f451`, not revalidated by a new paid run), global test isolation (#445), the older Evidence smoke/long-code-block accessibility findings (#446/#447), and Railway's recorded **2026-12-01** configuration deadline (#451). Sharing and password-recovery implementation remain outside this acceptance. No external messages were sent.

## Final merged-build verification

Both services served receipt merge `58269adb6c4409c73e3a84a58aefbbe7d4466ff5` after 137.1 seconds ([version wait](receipt-deploy-wait.json), [deployments](receipt-deployments.json)). All [main workflows](ci-receipt-main.json), including the nine live-required checks, passed; [fresh counts](ci-receipt-main-results.json) and [post-deploy smoke](receipt-postdeploy.json) are retained. Runtime trees match the primary member-accepted build. [Final read-only WALK-3 verification](final-reverify-walk3.json) proves retained content/membership/citations/export and disabled-account access. The five `final-reverify-*.json` product receipts repeat their scoped assertions on the same merge. No account was re-enabled or model generation repeated for these checks.

Sprint 60 closes with all six missions complete, identity pointers synchronized and the approved master-context mirror exported verbatim from CMOS. The documentation-only closeout merge receives its own required checks and exact serving/read-only verification before this task concludes.
