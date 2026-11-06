# METER-0 production check: usage is recorded, durably, per user

Observed 2026-09-22 UTC. PR #353 (merge `329de9b`, Railway TraceLab `6b335b9d`,
frontend `d238440e`) shipped the table and the hooks; PR #354 (merge `10c93e2`,
TraceLab `b538375e`, frontend `e0bfc58d`) corrected two mistakes the first
backfill exposed. Migration `051_usage_records` applied on deploy through the
service's `alembic upgrade head` start command.

## What happened on deploy

The reconciler's first tick after #353 recorded every terminal mission before
any manual step: `/api/v1/health` reported `usage_recorded: 440` at 04:24:00
UTC, and the manual sweep that followed found nothing left to record. 440
terminal missions in production, 440 rows: 432 `completed`, 8
`validation_failed`.

## Sanity check against a real run (criterion 5)

Mission `TRACE-SHARE-58` (dca03dd0), the Librarian-authored run from earlier the
same day, read back from `usage_records` against the worker's own
`execution_metadata`:

| Field | usage_records | worker |
| --- | --- | --- |
| total_tokens | 2,219,061 | 2,219,061 |
| input / output | 2,182,916 / 36,145 | 2,182,916 / 36,145 |
| requests | 27 | 27 |
| steps | 25 | 25 |
| duration_seconds | 302.47 | 302.47 |
| model / provider | deepseek-flash / deepseek | deepseek-flash |
| attribution | project_owner (backfilled; the run predates the submit hook) | |

## What the backfill exposed, and the fix (#354)

1. 21 of 440 rows had input tokens above their total. Older worker versions
   store `total_tokens: 0` at the top level beside a real triple in
   `synthesis_telemetry`, and the extractor mixed the two sources. The triple
   now comes from one source. After `--recompute`: 0 inconsistent rows of 440.
2. The admin summary windowed on `recorded_at`, so the backfill made every
   historical run look like last month's usage (`admin-usage-before-354.json`:
   440 records in the window). The window is now the run's own time
   (`admin-usage-after-354.json`: 22 records in the last 30 days).

## The answer to "what did this user consume last month" (criterion 3)

`GET /api/v1/admin/usage` for 2026-08-23 to 2026-09-22, one request:

| user | model | runs | total tokens | duration |
| --- | --- | --- | --- | --- |
| derek@deniedart.com | deepseek-flash | 1 | 2,219,061 | 302 s |
| derek@deniedart.com | deepseek-v4-pro | 21 | 24,649,150 | 5.5 h |

`cost_usd` is null throughout: the worker sends no price and none is asserted.

## Not done

- No price table. Tokens and model are the durable facts; a price can be applied
  at query time when one is decided.
- 369 historical rows carry `model: null` because their worker version wrote no
  `runtime_identity`; tokens and duration are recorded where the worker
  reported them.
- Nothing user-visible, no limits, no quotas, no billing (criterion 4).
