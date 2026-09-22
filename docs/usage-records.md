# Usage records (METER-0)

TraceLab records what each mission run and each Librarian call consumed, per
user, so that metering is possible later. It records only. Nothing reads these
rows to limit, block or bill; when a usage policy is wanted, the history will
already exist. Decision #522, Sprint 57.

## What is recorded

One row in `usage_records` (Alembic `051_usage_records`) per:

| kind | when | attribution |
| --- | --- | --- |
| `deepsearch_run` | at submit (queued row), filled in when the run reaches a terminal status | `submitter`: the user who pressed submit; `project_owner` when the submitter is unknown (history, or a run that never went through the submit route) |
| `librarian_turn` | each conversational turn | `caller` |
| `librarian_draft` | each mission draft | `caller` |

Columns: `user_id`, `project_id`, `mission_id`, `kind`, `status`, `attribution`,
`provider`, `model`, `input_tokens`, `output_tokens`, `total_tokens`,
`requests`, `steps`, `tool_calls`, `duration_seconds`, `usage_complete`,
`cost_usd`, `details`, `started_at`, `completed_at`, `recorded_at`.

`cost_usd` is null for DeepSearch runs: the worker reports tokens, requests and
duration but no price, and no price is hard-coded here. Apply a price at query
time when one is decided.

The DeepSearch numbers come from the accounting the worker writes into
`missions.execution_metadata` on every terminal run (`total_tokens`,
`duration_seconds`, `synthesis_telemetry.recovery.attempt_accounting`,
`quality_record.terminating_step`, `tool_call_summary`, `runtime_identity`).
`reports.tokens_used` and `synthesis_cache.tokens_used` are unchanged and not
duplicated.

## Where it is written

- `POST /missions/{id}/submit` and `POST /missions/create-and-submit` pass the
  caller into `_submit_existing_mission`, which writes the queued row.
- `MissionResultMaterializationService._materialize_locked` fills the row under
  the per-mission lock. Both ways a terminal result arrives (the signed webhook
  receipt and the reconciler) converge there.
- The reconciler tick (`run_reconciliation_once`) also sweeps terminal missions
  that have no row and records them against the project owner. That sweep is
  the backfill for history and the safety net if a hook is ever missed. The same
  sweep is available by hand:

```bash
python -m app.cli.record_mission_usage --limit 1000
python -m app.cli.record_mission_usage --mission-id <uuid>
```

Every write is idempotent on `(mission_id, kind)`; a replay that carries the
same numbers changes nothing.

## Reading it

`GET /api/v1/admin/usage?since=&until=&user_id=` (admin only) returns per-user,
per-kind, per-model totals over the window, defaulting to the last 30 days. It
is the answer to "what did this user consume last month" without reading logs.
There is no user-visible surface.

Regression coverage: `tests/unit/test_usage_extraction.py`,
`tests/test_usage_records.py`.
