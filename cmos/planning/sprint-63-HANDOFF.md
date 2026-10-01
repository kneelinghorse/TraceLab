# Sprint 63 — Clear onboarding and focused maintenance

Locked 2026-10-01 in planning session **PS-2026-10-01-007**, decision **#589**.
CMOS is authoritative for mission criteria, dependencies and status. This handoff
records implementation guidance and the evidence needed by a fresh build session.
Guiding templates: [roadmap](../foundational-docs/roadmap_template.md) and
[technical architecture](../foundational-docs/tech_arch_template.md).
Intent: [living roadmap](../foundational-docs/roadmap-sprints-57-60-the-librarian.md).

## Mandate and starting state

Derek approved the recommended maintenance sprint and asked to lock its missions
and prepare the details for a fresh build session. Scope is package documentation
and onboarding, factual repository metadata, the confirmed frontend cleanup, and
release acceptance. **Three Queued missions in a Planned sprint; no build started.**
Start/end dates remain unset until actual execution. Planning does not release,
deploy, change public metadata, send messages or run paid research.

Use **`projectRoot=/Users/systemsystems/portfolio/TraceLab`** for every CMOS call.
The source worktree is not another CMOS instance. The planning branch is
**`codex/sprint-63-plan`**, in
`/Users/systemsystems/.codex/worktrees/sprint-63-plan/TraceLab`, based on final S62
receipt commit **`9caa93b8f6adbf11e4431c5616b380d478f67a37`**. Its runtime ancestor
is **`d7b8682`**, also the fetched `origin/main` at planning. The base carries twelve
S62 roadmap/receipt files beyond main, with no additional runtime changes; preserve
those accepted receipts and reconcile any later main changes before building.
The original checkout is older (`d0ffd02`) and has two untracked user notes. Leave
that checkout and the notes intact.

## Fresh build entry

1. Read root `agents.md`, `cmos/agents.md`, this handoff and the selected mission.
   Use CMOS MCP; the local v2 guidance supersedes the old Python CLI instructions.
2. Run `cmos_review`, `cmos_db(action="health")`,
   `cmos_sprint(action="show", sprintId="sprint-63")` and
   `cmos_decisions(action="list", sprintId="sprint-63")` against the canonical root.
3. Create an isolated build checkout from the **planning branch tip**, or use its
   committed handoff deliberately. Inspect later main/package changes before edits.
4. Open a build/custom session and explicitly start **S63-PUBLIC**. First mission
   start activates the sprint. Follow the
   [identity-sync runbook](../docs/operations-guide.md#sprint-boundary-identity-sync-runbook)
   then, including `sprint_tracking.current_sprint` if the mission start leaves it
   unset. Planning deliberately leaves project identity at S62 completed.
5. Enforce dependencies yourself; CMOS records but does not enforce them. Alphabetic
   queue order is not delivery order. Commit at coherent boundaries, with mission IDs.

## Locked missions

| Order | Mission | Outcome | Requires | Existing follow-up |
| --- | --- | --- | --- | --- |
| 1 | **S63-PUBLIC** | Accurate package setup, first run, license link and factual metadata; patch ready | — | #481 |
| 2 | **S63-CLEAN** | Remove abandoned preset input and correct affected frontend docs | — | #449, #450 |
| 3 | **S63-RELEASE** | Published-artifact, public metadata and frontend delivery acceptance; closeout | Both above | Close only accepted rows |

PUBLIC and CLEAN are independent; a release credential delay must not block local
cleanup. Read full CMOS criteria rather than treating this table as their substitute.

## S63-PUBLIC implementation guidance

Source request: Aquex CMOS message **397036b0-0e5f-43c5-aa86-0350de5c306c**.
Planning verified the GitHub root `LICENSE` endpoint returns 404; the package's
[MIT license](../../packages/tracelab-mcp/LICENSE) exists and is publicly readable.
Use that package license, not an invented service-wide license. GitHub reporting
`licenseInfo: null` for the repository is not a requirement to license the service.

The [package README](../../packages/tracelab-mcp/README.md) has the correct current
table (nine clusters, fifty actions), but still recommends pinning 1.2.0. Its
migration history stops at the eighth cluster. Preserve historical facts while
removing obsolete installation advice and completing the history. Do not invent
new tools, change the API or rewrite unrelated reference material.

Add a numbered path using the actual tool interface:

1. Obtain an invited TraceLab account and sign in to the browser app. Configure a
   supported stdio client with the API origin, then launch the adapter.
2. Complete the device-code approval shown by that launch. The MCP process must not
   be presented as a one-shot shell command for individual tool calls.
3. Call `tracelab_project` with `action="list"` and select a returned project ID.
4. Call `tracelab_search` with `action="ask"`, that `project_id`, and a `question`;
   explain how to open its supporting citation.

Provide the empty-state branch before step 4: no bundled corpus comes with signup.
Registration creates a personal Space, not projects or indexed documents; shared
access may make projects visible. Create a project and upload/process documents
before corpus Q&A. Explain `no_evidence` when the accessible indexed documents do
not support an answer. General Librarian chat/planning is different from this
corpus-only MCP action, and asking does not submit a DeepSearch mission.
Evidence: [registration](../../app/api/v1/auth.py),
[ownership](../../app/services/ownership.py), and
[personal-Space tests](../../tests/test_personal_spaces.py).

Prepare this exact factual replacement for the GitHub repository description:

> A personal-scale research repository with RAG-powered semantic search, Mission Protocol integration, and document processing with PII redaction. The architecture prioritizes rigor, traceability, local control, and cost-effectiveness.

S63-RELEASE applies and reads it back; retain other repository settings. The
approval covers this scoped factual correction, not a new certification claim.

Planning read `npm view @aquex/tracelab-mcp version dist-tags --json`: latest is
**2.1.0**. `git diff tracelab-mcp-v2.1.0..9caa93b -- packages/tracelab-mcp` is empty.
Prepare **2.1.1** as the documentation patch; recheck both facts before choosing
the release version. Update package version/lock/changelog coherently. Keep Node
>=18, dependencies, tool descriptors and runtime code unchanged. Do not add a
new regression merely to assert prose; validate examples and existing contracts.

## S63-CLEAN implementation guidance

[ChunkList](../../frontend/src/components/librarian/ChunkList.tsx) is the sole
current [SaveSearchButton](../../frontend/src/components/SaveSearchButton.tsx)
caller. It does not pass `preset` or `onPresetConsumed`. Remove that abandoned
input path and its effect, then only branches that become exclusively dead.
`SaveSearchPreset` still types the internal draft: do not mechanically delete it
or make saving read changing parent props after the form opens. Preserve query,
filters, topK, name/description, limits, cancel/reopen, API errors and `onSaved`.
No new abstraction or adjacent saved-search redesign is warranted.

Correct the affected claims in
[frontend architecture](../../docs/frontend_architecture.md): active mission
routes/filters and palette contents. Keep historical material clearly historical;
do not claim the entire architecture page was freshly audited. Saved searches
remain a real feature. Saved mission views do not.

**Preserve `frontend/src/pages/missions/queue.tsx`.** It is a deliberate 404
tombstone. Deleting it lets `[id].tsx` treat `queue` as a mission and return 200.
The [route map](../../frontend/src/lib/route-migrations.json) and browser tests
already encode that retirement. Correct the documentation, not that mechanism.

Reuse intent-bearing coverage in
[Librarian unit tests](../../frontend/src/__tests__/librarian.test.tsx) and
[search-command browser tests](../../frontend/tests/e2e/search-command.spec.ts):
current query/project/topK are saved, the saved link works, and an intended saved
run executes once. Add only a missing test for behavior the removal could change.
Keep provider calls isolated; production writes are unnecessary for this cleanup.

## Validation and release gates

The following are execution gates, **not tests run during planning**:

- PUBLIC: package `npm run build`, `npm run test:run`, `npm run test:contract`,
  `npm run test:package`; both root MCP parity scripts. Check links and examples
  against the actual descriptors and existing device-code/credential tests.
- CLEAN: `npm run test:unit -- --run src/__tests__/librarian.test.tsx`, frontend
  type-check/lint/build, and `search-command.spec.ts` plus `route-migration.spec.ts`
  against `next start`. Exercise the save form and keyboard/focus in Light/Dark
  at the existing 390/820/1440 coverage. Use the current fixture/config setup.
  Run `pytest tests/test_saved_searches.py` through S62's isolated test environment
  and `python3 cmos/scripts/validate_foundational_refs.py` from the build tree.
- RELEASE: current required CI on the exact final source; fresh serving identity
  after frontend delivery; the existing read-only browser baseline. Do not change
  the twelve-test quarantine, branch protection or known baseline failures.

DoD-1 applies even to a documentation patch. First pack and install the tarball in
a clean temporary directory and run its actual ESM entrypoint through the MCP
client. [check-package.sh](../../packages/tracelab-mcp/scripts/check-package.sh)
already does this with an isolated HTTP fixture. Inspect packed README, LICENSE,
changelog, version and handshake. The CJS scan must distinguish a valid locally
derived `__dirname` from an unbound CJS global in ESM.

After publication, independently install the **registry artifact** in a fresh
directory, verify registry version/dist-tag/integrity and packaged contents, then
pass its installed `dist/index.js` to
[check-canonical-links.mjs](../../packages/tracelab-mcp/scripts/check-canonical-links.mjs).
That real stdio harness covers project list and ask/HTTP verbs without paid
provider calls. Do not reuse the historical S59 production ask script blindly;
it can record paid usage. Rebuild before testing any changed package source and
never commit `dist/`. Use existing release authentication; if npm needs the user's
login/OTP, prepare the exact tested artifact first and keep RELEASE open until
published acceptance succeeds.

Record receipts under `cmos/reports/sprint-63/` with tested/serving commit and
package identity, commands, counts, skips, failure dispositions and source hashes.
Use the source-citation audit in the operations guide at close. Local package
tests cannot substitute for a registry install; old S62 receipts prove only
unchanged paths unless explicit replacement validation is recorded.

## Carry-forwards and neighboring work

The three selected rows **#449/#450/#481** are carried to S63 and remain open until
accepted. **Twelve other rows remain open and outside this build**:
`400, 403, 406, 407, 415, 422, 431, 448, 452, 454, 477, 479`.
Sharing remains deferred. Context size was 61.31 KB/100 KB at intake; no pruning
mission is justified. No connector migration, pricing policy, Space migration,
theme-dev repair or generalized cleanup is implied by this sprint.

P1 **#479** is still the highest-priority external correction. DeepSearch owns
source/word-scope enforcement. The retained
[diagnosis](../reports/sprint-62/S62-SCOPE/diagnosis.json) and next-step row specify
the missing executed contract/input/prompt hashes, allowlist/300–500-word negative
fixtures and same-stage counters. TraceLab vendor parity follows a versioned worker
fixture and the authoring-contract map. Do not reopen the diagnosis, call the
worker fixed, add speculative vendor changes or rerun paid research. If a correction
arrives, assess it separately instead of silently expanding these three missions.

Aquex hello request **678bc33a-cf00-42fa-847f-f43bb318297a** is already satisfied by
S62-MAIL. Its [validation receipt](../reports/sprint-62/S62-MAIL/validation.json)
contains the ready completion reply and actual inbox/Reply-To proof. No new email,
DNS change or implementation is needed. Aquex owns its site-contact update. The
two inbox messages and the DeepSearch handoff remain unsent; the user's current
instruction is planning, not an instruction to send cross-project messages.

At actual sprint close: reconcile all fifteen rows, close only verified selected
work, update the roadmap as outcome, verify CMOS health/dashboard parity, complete
the session, synchronize sprint identity and snapshot `master_context`. Do not
mark S63 complete while package publication or frontend acceptance is outstanding.

## Ready-to-use build prompt

> Build the locked Sprint 63 maintenance scope from `codex/sprint-63-plan` in a
> fresh isolated worktree. Read `cmos/planning/sprint-63-HANDOFF.md`, decision #589
> and all three mission definitions. Use the original TraceLab checkout as the
> canonical CMOS projectRoot. Start S63-PUBLIC, preserve the independent S63-CLEAN
> scope, and require both before S63-RELEASE. Complete the documented validation
> and published-artifact gates; retain the separately owned DeepSearch correction
> and other excluded carry-forwards. Record exact handoffs if a required external
> credential or acceptance step prevents completion.
