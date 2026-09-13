# UX-1 session handoff — 2026-09-12 local / 2026-09-13 UTC

Session: `PS-2026-09-12-005`. Sprint 50 remains Active. UX-1 remains In Progress and unfinished. This document supplements CMOS's authoritative status and the [overhaul roadmap](../../foundational-docs/roadmap-sprints-50-53-ux-overhaul.md), which follows the canonical roadmap template; it does not replace either.

## User correction and ownership

The user explicitly stopped work in Forge: do not work across repositories without explicit permission; let Forge do its work. The agent wrongly interpreted UX-1's cross-repo deliverables as authorization and implemented in Forge after sending a backlog request. Decision **391** supersedes that authorization claim in decision **387**. Evergreen learning **155** records the ownership boundary. Older next steps **219** and **227**, which suggested authoring Forge changes from TraceLab, were dropped.

This handoff does not authorize further Forge inspection, edits, messages, PR/CI operations, merges, package builds, checkout changes or worker refreshes. Forge owns those actions unless the user explicitly delegates them. TraceLab owns its mapping contract, tests, evidence and CMOS bookkeeping. A future instruction to finish UX-1 must respect this boundary. No rollback, cleanup, branch deletion or CI cancellation was requested.

This build session sent exactly one new message to Forge: backlog request `f091c849-fe1a-49d5-93ee-b8029219685a` to `cmos://derek/forge`. No follow-up or landed-ref message was sent. An earlier planning session referenced request `ffbca05f`; that is separate history. Do not send another message without explicit authorization.

## Sprint and TraceLab checkout

| Mission | Handoff state |
| --- | --- |
| RECOVER-1 | Completed; PR254 merged at `429ac59` |
| RECOVER-2 | Completed; PR255 merged at `6155d88` |
| UX-0 | Completed; PR256 merged/deployed at `703a91a30c2751767547252e722cbc42f34ad8c2` |
| UX-1 | In Progress; mapping, tests and previews prepared, merge and dependency acceptance outstanding |
| UX-2 through UX-5 | Queued; no implementation started |

TraceLab working directory: `/Users/systemsystems/portfolio/TraceLab`, branch `codex/ux-1`. At handoff preparation, both local HEAD and the local remote-tracking branch were `c9e924c51fd773a705bc7a1120a9d68684fdde8a`. [TraceLab PR257](https://github.com/kneelinghorse/TraceLab/pull/257) was draft and unmerged at the last observation. The handoff/evidence checkpoint is a subsequent local commit; it is not pushed during this closeout.

The following two pre-existing user changes are outside this mission and remain byte-identical to the saved copies under `/tmp/recover1-preserved/`:

- `cmos/reports/sprint-37/graph-search-e2e-validation.json`
- `cmos/reports/sprint-38/semantic-edge-e2e-validation.json`

Only handoff documents, the UX-1 validation summary and already-downloaded final CI metadata belong in the local closeout commit. Do not stage the whole working tree. CMOS's SQLite database is not committed.

## TraceLab deliverables and verified evidence

- [Object contract](../../contracts/oods-object-model.md): seven research objects, 522 model-field mappings plus 10 nested mappings. Space maps to Organization; User is reused. Missing API ownership/history/count fields remain unavailable rather than inferred.
- `tests/unit/test_oods_object_contract.py`: **18 passed, no skips**, five dependency deprecation warnings. Includes native composed-schema parity for every mapped field constraint. Foundational-reference validation passed before the pause.
- [Validation summary](ux-1-validation.json): proof, earlier failures, fixes, provenance, limits and outstanding criteria.
- [Schema persistence](oods-previews/canonical-schemas/persistence.json): 20 saved compositions at schema version 2, source `335664b5875981f1a3ec0a9635263d17e40bfe42`. Six page objects have list/detail/timeline, Chunk is inline only, and Mission adds workflow. The provided schema tool showed 36 total records; the original 16 records' metadata was preserved.
- [Full preview index](oods-previews/preview-summary.json): 40 React receipt sets, **120 viewport observations** across 20 compositions × two themes × widths 390/820/1440; zero browser errors or overflow, 58 recorded text-wrap observations. The originally requested Mission/Evidence subset comprises 30 observations, with 14 wraps.
- Preview sources are `335664b5875981f1a3ec0a9635263d17e40bfe42` and `ce2239c062d93dbd0f7fdc70e648e24bb99e39fb`; the latter differs only in generated tool-reference documentation. Do not relabel receipts to later heads.
- UX-2/UX-3 reference the schemas and previews in CMOS. Planned UX-6/7/8 in the Sprint 51 roadmap also reference them; those missions have not been instantiated.

The previews contain synthetic fixtures, generic controls/labels and default serif typography. They are structural specifications, not completed TraceLab production screens. Phone review covered Evidence list/light, Mission detail/dark, Mission workflow/dark and Chunk inline/light: sidebars stack; pagination and long identifiers wrap; native select values truncate. Binding actual data and TraceLab typography belongs to later build missions.

UX-0's shipped proof remains separate: 88 frontend unit tests and eight interaction tests passed; both local and live matrices had 112 route/theme/width checks with zero horizontal overflow, serious/critical axe findings, JS errors or transport failures. Its backend suite had 2,391 passed, three skipped and 12 deselected; integration had 125 passed and four skipped. Do not describe suites with skips as universally passing every test.

## Last observed TraceLab CI

At `c9e924c`, required checks were green before work stopped:

- Backend: run `34728938305`, job `103648046321`.
- Frontend production build: run `34728938338`, job `103648046267`.
- Frontend type/unit checks: run `34728938311`.
- Changed-file Ruff: run `34728938306`; secret scans also passed.

The integration run `34728938307` was not finally rechecked at the stop. At the preceding `e3952e471d457966528286e9bc6f92e740c69b7b` head, backend was **2,409 passed / 3 skipped / 12 deselected**, integration **125 passed / 4 skipped**, and all eight browser tests passed. Full Ruff, mypy and frontend lint had advisory baseline failures. These are historical observations, not checks of the new local handoff commit.

## Existing Forge work — inventory only, not permission to act

At the last observation before the user's stop:

- [Forge PR105](https://github.com/kneelinghorse/OODS-Forge/pull/105) was open and unmerged, base `OODS-pro`, branch `codex/tracelab-ux-1`, pushed head `af277eaa87e3d44a1388ae5da2ae88af26bb44be`.
- Temporary worktree: `/tmp/tracelab-ux1-forge`; tracked files were clean, with temporary untracked dependency symlinks. Package output symlinks had been replaced by real build output for archive assembly.
- Canonical checkout `/Users/systemsystems/portfolio/Design-Tools/OODS-Forge` remained detached at `114a268ea10b9141bc96925c69132179c7c4b334`. Its unrelated four files under `artifacts/product-reality/sprint-190/delivery/` were preserved; hashes are in `/tmp/ux1-preserved-forge-delivery.json`.
- Canonical checkout and native worker were **not activated**. Public object listing remained the old 11 objects / historical 154-cell runtime; saved schemas alone do not prove registry activation. The intended new census is 18 unique objects, 19 definitions and 240 cells.
- Prior native worker PID 20145 belonged to adapter 19527; another bridge/worker belonged to unrelated user work. PIDs are historical only and must never be reused as action targets without fresh verification and authorization.

The implementation includes seven alpha research YAML objects; Chunk inline-only enforcement; immediate cancellation only when the declared lifecycle supports it; canonical `id` consistency across collection rows/workflow stores; enum filters using the declared field; phone sidebar stacking; current census updates while preserving historical receipts; tool-reference refresh; yielding between synchronous test compilers; and a portable census independent of authoring YAML.

These changes are not asserted to be accepted by Forge. Local source/tests, an open PR and a sent request are not landed ownership acceptance.

## Forge proof chronology and last observations

**First full catalog, run `34722431783`: rejected.** 228/240 cells passed and 12 workflows failed because collection row keys disagreed with canonical workflow-store identity. Six intent regressions reproduced the mismatch. Original rejected evidence remains under Forge's `artifacts/product-reality/tracelab-ux-1/diagnostics/runtime-ci-34722431783/`; it was not promoted as passing proof.

**Run `34725928271`: full catalog passed, other checks initially failed.** At actual CI merge `a7ef99a21c303e3ef66f57845e9f2b52475f79a3`, the pinned Linux sweep passed **240/240 cells**, four dashboard cells and 48 chart/theme checks in 58m59s; emitter mutation failed as intended and byte-identical restoration passed. The same revision passed 42/42 release cells. Canonical proof retained the original receipt bytes and source heads; only the canonical receipt-root location changed. The runtime job budget became 75 minutes, with assertions, population and per-cell limits unchanged (decision 390).

That run's coverage had 7,163 passed / 5 failed / 16 skipped; its MCP suite had 6,834 passed / 6 failed / 16 skipped plus one worker RPC timeout; the main consumer suite had 304 passed / 1 failed. Docs/current-proof fixes addressed several failures. The dist-only B-12 health failure also required removing an authoring-YAML runtime dependency: the earlier stale-proof-only explanation was incomplete. All **61 focused regressions subsequently passed with no skips or errors**. See learnings 153 and 154.

The local extracted archive then passed 19 actual tool paths, bridge parity, lifecycle and unchanged extraction checks on Node v24.6.0, but its manifest was dirty because of temporary untracked dependency links. It is development smoke, not clean final certification. Retained Forge evidence is under `local-portable/`.

**Run `34728733886`: GitHub refused jobs before execution**, reporting account payments/spending-limit capacity. No billing settings were changed. UX-1 was briefly blocked, then explicitly unblocked when the next run executed real steps. Do not treat this historical refusal as a currently verified billing blocker.

**Last run observed: `34728936186`**, branch `af277eaa`, actual CI merge **`58d88da97dbd3d120aefb70fb3a913ec90fdc46b`**. Last observation was approximately **2026-09-13 01:05:56 UTC**, before the user's stop. No Forge status was fetched during this handoff.

- Both clean portable jobs passed: Node **v24.20.0** (job `103648041257`) and **v20.11.1** (`103648041213`), 19 tool paths, bridge parity, lifecycle and unchanged extraction trees, both `dirty=false`. Identical payload SHA-256: `901a43a9be26532f4d358794be6860fbc7a0bb8f9ac1d2a8e8c88b167b6d3aa3`.
- Release job **`103648041114` passed 42/42**. Bundle head is the exact `58d88da...` CI merge; archive SHA-256 is `3b50f551c455588f0e92b1171e75b9ce4b71de9be6a8fc85e785227e462cdbe8`. Rows matched original passing receipts and host artifacts; validation issues were empty.
- Consumer job **`103648041105` passed**: stages of 13, two, and 305 tests, with no skips. Existing local log: `/tmp/ux1-final-consumers-ci.log`.
- Build, lint, types, component packages, a11y contract, tenancy, tokens, scale, diagnostics, guardrails and token governance had passed.
- **Unknown final outcomes at handoff:** coverage `103648041094`, full MCP/viz-determinism `103648041126`, and full runtime catalog `103648041176` were still running at the last observation. Remote CI may continue independently. Do not call the whole run green or recertify its current status from this snapshot.

Newly retained small artifacts are in [forge-final-ci/acquisition.json](forge-final-ci/acquisition.json), its `node-24/` and `node-20.11.1/` trees, and [release/acquisition.json](forge-final-ci/release/acquisition.json). Original artifact files are unchanged. Only report/validation metadata is stored under CMOS, not generated executable packages. The full final release download is `/tmp/ux1-final-ci-release`; full current runtime artifacts had not been downloaded.

Other useful existing scratch paths, all potentially ephemeral: `/tmp/ux1-final-portable-v2-out/forge-runtime.tar.gz`, `/tmp/ux1-final-portable-v2-extracted/`, `/tmp/ux1-current-proof-regressions-fixed.log`, `/tmp/ux1-local-workflows-final.log`, `/tmp/ux1-tracelab-contract-final.log`. Prefer the committed reports and source receipts; do not rerun scratch mutation tools without authorization.

## Next session: finish UX-1 within the ownership boundary

1. Open with `cmos_review()`, read root `agents.md`, `cmos/agents.md`, the roadmap and this handoff, then `cmos_mission(action="show", missionId="UX-1")`. Use the actual TraceLab root; older CMOS documentation contains stale paths/tool names. Start a new session, not a duplicate mission.
2. Inspect TraceLab's branch, local handoff commit and PR257 state. Preserve the two unrelated reports. Reuse the 18-test mapping suite, saved schemas, preview index and exact-source receipts; refresh tests/checks when new changes justify it.
3. Resolve the Forge dependency through Forge-owned completion evidence or explicit user delegation. Required acceptance remains seven research objects visible through the intended provided registry; Mission workflow composition with zero validation errors; and an actual landed commit plus relevant final CI/activation proof. Do not infer permission from this checklist or older mission text. Do not send a new message without authorization.
4. Once that evidence is available, reconcile TraceLab's validation summary and PR257 with the actual landed revision, complete the remaining TraceLab review/check/merge work in the resumed authorized build session, and record ownership acceptance. A passing historical 240-cell run, saved schemas, or a local clean archive alone cannot close UX-1.
5. Complete UX-1 only when all its success criteria are actually met, then verify CMOS status. Sprint 50 stays open with UX-2–5 queued. Do not start those missions during this handoff.

## Other unresolved context

During UX-0 a Playwright timeout included the local MCP key in private task output and two temporary logs. Logs were redacted and the harness was hardened; no secret was committed. The user was asked whether to replace/revoke the key and has not answered. No rotation or revocation is authorized by this handoff. Do not print credentials or raw authenticated errors. This incident is already learning 150; it is not a reason to block unrelated documentation work.

Read-only UX-2 investigation is preserved in [ux-2-preparation-notes.md](ux-2-preparation-notes.md). It is an unaccepted implementation sketch requiring source revalidation at UX-2 start. It does not authorize touching Forge or starting UX-2. Home needs truthful scoped aggregates, real execution progress, per-user review semantics, authorized report/evidence links and actual frontend package integration; no UX-2 source files were changed.

The closeout performs TraceLab documentation and CMOS operations only. Existing Forge PR, worktree, CI and workers are left as they were when the user stopped work.
