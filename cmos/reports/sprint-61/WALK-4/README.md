# WALK-4 acceptance

The recovery matrix and the single paid live-log run are verified. Final legacy
retirement CI/deployment remains required before mission or sprint closure.
The [recovery receipt](recovery-acceptance.json) separates production observations,
user actions and controlled regression tests. It follows the
[Sprint 61 handoff](../../../planning/sprint-61-HANDOFF.md) and the
[operations closeout runbook](../../../docs/operations-guide.md).

The user-created candidate received the third reset email and the user opened its
form without submitting: the JWT, ordinary key and collected device key all
continued returning HTTP200. After the user reset, each returned401, refresh and
query-token reconnect returned401, and the existing stream closed normally after
two heartbeats. The approved uncollected grant could no longer yield its key.
The candidate advanced from credential revision2 to3 with zero remaining keys or
grants. The user confirmed being signed in under that account afterward. All seven
other accounts, including owner and DeepSearch service, retained their credentials.

Both actual MCP paths (direct TraceLab and Aquex hub) returned all 65 projects after
the reset; the published MCP 2.1.0 read returned the same 12 log rows. A separate Aquex
connector failed its SSE probe with an aquex.ai 404. No connector configuration or
saved MCP credential was replaced, and that routing failure is recorded separately.

The earlier AUTH-1/AUTH-2 receipts establish delivered public/admin recovery,
new-password login, old-password rejection and automatic logout. Expiry/replay,
legacy revision0 lifecycle, denied target types and Settings behavior have isolated
backend/PostgreSQL regressions; this receipt does not label those fixtures as live
production tests. Local production-build browser matrices cover Light/Dark at
390/820/1440, keyboard/focus, scroll and axe; they are not a personal user walkthrough.

[LOG-2](../LOG-2/README.md) records two preterminal batches, a 10.627-second browser
visibility upper bound, 12 retained final lines, exact runtime hash, the retained
research/document/report/Ledger artifacts, warnings and unverified billed dollars.
Exactly one paid run was submitted. No repeat was needed for these checks.

The interaction asked the operator for too many fragmented steps and caused
confusion about the account. Learning 280 records the corrected practice. Interactive
testing is finished. The candidate stays enabled as the user left it; all temporary
test keys and grants were revoked by the reset. No further account changes are planned.
