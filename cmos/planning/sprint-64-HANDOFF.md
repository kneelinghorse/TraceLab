# Sprint 64 — Authored scope preview and result alignment

Planned 2026-10-01 in session **PS-2026-10-01-012**, decision **#595**.
CMOS is authoritative for mission criteria, dependencies and status. This handoff
records implementation guidance and evidence boundaries for a fresh build session.
Guiding templates: [roadmap](../foundational-docs/roadmap_template.md) and
[technical architecture](../foundational-docs/tech_arch_template.md).
Intent: [living roadmap](../foundational-docs/roadmap-sprints-57-60-the-librarian.md).

## Mandate and starting state

Derek requested TraceLab's next sprint after DeepSearch returned the scope fix.
**Four Queued missions in a Planned sprint; no implementation started.**
Start/end dates remain unset. Planning selects existing follow-up **#479** only;
the eleven other carried items retain their owners and stay outside this sprint.

Use **`projectRoot=/Users/systemsystems/portfolio/TraceLab`** for all CMOS calls.
The planning branch is **`codex/sprint-64-plan`**, in
`/Users/systemsystems/.codex/worktrees/sprint-64-plan/TraceLab`.
It preserves S63 final receipts at **`0a04e23bee2031529e4f964bcaf8f355394f6521`**
and reconciles fetched main **`e716e34bcb1b60966ffcd8d67246f3c8e6026b40`**.
Only the older context/roadmap status conflicted: retain the later accepted S63
closeout, not main's superseded active/2.1.0 description. No runtime differences
from main are introduced by this plan. The original checkout at `d0ffd02` and
its two untracked user notes remain intact.

Read the detailed missions through CMOS; do not treat this handoff as a duplicate
backlog. Follow Requires ordering explicitly because CMOS does not enforce it.

| Order | Mission | Intended outcome | Requires |
| --- | --- | --- | --- |
| 1 | **S64-VENDOR** | Deterministic schema 1.2/revision 3 compiler and canonical fixture parity | — |
| 2 | **S64-SCOPE** | Lossless authoring, Librarian drafts, REST and MCP preview fields | VENDOR |
| 3 | **S64-RESULT** | Understandable planned limits and preserved partial/failure artifacts | SCOPE |
| 4 | **S64-ACCEPT** | Integrated parity, package/TraceLab delivery and explicit worker-gate disposition | All three |

## DeepSearch evidence and delivery boundary

The outgoing request is **096847da-aa08-4c65-aa11-1d9cd7a1be84**.
The completion update is **ad16f01d-afe6-4553-a2c9-1bb721c67c04**.
A [read-only copy](../reports/sprint-64/planning/upstream-message.json) preserves
the handoff; [intake verification](../reports/sprint-64/planning/intake.json)
records inspected sources and hashes.

DeepSearch's implementation is **`79ef84842fb84259bafe59924b21fe2f5ad05d7d`**;
closeout is **`1c5d35283f35a94ae74328d3c11d1e62ab6aa483`** on
`codex/s94-authored-scope`. Read those immutable Git objects from
`/Users/systemsystems/.codex/worktrees/s94-authored-scope/DeepSearch.alpha`
or the canonical DeepSearch repository. Required upstream references:

- `docs/authored_scope.md` — semantics and persistence surfaces.
- `cmos/reports/sprint_94_closeout.md` — verification and delivery state.
- `tests/fixtures/authored_scope_v1/` — canonical inputs, prompts, outputs and verdicts.
- `deepsearch/mission/compiler_provenance.py` — structural module list and canonical rules.
- `scripts/check_authored_scope_parity.py` and the S94 tests — upstream regression intent.

The handoff explicitly says **not pushed, merged or deployed**. Its locally
verified fix is a valid integration input; it is not evidence of production
enforcement. Recheck new evidence at build/release time without operating the DS
repository. Worker delivery remains DeepSearch-owned and separately authorized.
Do not dispatch paid research or a hash-only probe. Production byte identity
belongs on the next required, separately authorized worker run.

The historical executed contract `bae1333274533285`, saved preview
`106cb8668a3efdb8`, and new fixture `8ca1ebfaa604dc7e` are distinct.
Historical input/prompts were not recovered. The 2,285 rendered versus 2,240
reported word delta remains unexplained. Do not relabel a structural replay as
historical execution or infer 22 body downloads from 22 grounding URLs.

## Compiler and fixture guidance

Planning checked all **17 fixture files** against both the manifest and the
implementation commit, plus all **six structural modules**. No mismatches.
The [manifest copy](../reports/sprint-64/planning/upstream-fixture-manifest.json)
has SHA-256 `db256e5821393ca9750b704714b8e76803e3e8f7de86255a6f83d9d7cc0114cc`.
The canonical contract bytes hash to
`163e7af36080b8440afe55f501b023cb2e3aba84e1b8644298fc0784167b5cb6`.
Import fixtures into the root test layout during implementation, keeping their
bytes intact and recording provenance. Do not put runtime code under `cmos/`.

The structural dependency set is `contract.py`, `scope.py`,
`compiler_provenance.py`, `title_utils.py`, `deliverable_schemas.py`, and
`domain_policy.py`. The old three-file recipe is insufficient. Follow the
[vendor contract](../contracts/deepsearch-compiler-vendor.md) and replace its
stale pin/recipe in VENDOR. Keep an explicit list of local adaptations:

- Rewrite imports to the vendored package; retain source attribution.
- Always pass `enrichment_mode="none"`; upstream defaults to configured enrichment.
- Keep deterministic declared-entity behavior and the COMPILER-1 clean-runtime guard.
- Adapt provenance identity locally: upstream manifest helpers import observability
  when called; bringing in its runtime dependency tree defeats offline preview.
- Use canonical origin/time only for canonical identity/fixture comparison.
  Distinguish semantic compiler revision **3** from the pinned source commit.
- Reconcile the entire semantic state before claiming parity. In particular,
  TraceLab currently defaults `min_loops` to 0; the worker fixture uses 2.
  Preserve explicit author values and do not silently omit differing fields.
  This does not authorize changing worker budgets or restoring research-depth UI.

Use the compiler's typed restrictions, not a second local interpretation.
References alone remain seeds. Exact-page restrictions differ from domains,
and arbitrary prose is not a supported scope grammar.

## Authoring and public surfaces

The durable typed location is **`context.authored_scope`**, already supported
by the worker. A new DB column or parallel top-level persistence field is not
needed. Preserve structured references, context keys and constraints fallback.
Update the [authoring map](../contracts/mission-authoring-contract.md) in the same
implementation commit as the boundary changes.

Immediate gaps inspected during planning:

- `build_mission_context_from_mission` omits structured scope.
- Librarian `MissionDraft` lacks references/context, and
  `_as_mission_namespace` supplies `references=None` and `context={}`.
  Fix both validation and conversion/persistence: a successful pre-save preview
  must describe what is actually saved.
- The preview dataclass/shaper, Pydantic response and frontend types lack the new
  scope and canonical identity. Update API types and the hand-shaped TS MCP summary
  as well as the full result. Exercise the actual installed client/verb.
- Manual edit, collection seed and rerun must preserve author input without
  copying execution metadata into a new run.

Read immediate callers before changes. Preserve the existing explicit
save/preview/submit separation, project authorization, idempotency and
one-execution guard. Use scripted Librarian responses for deterministic tests;
the task is field preservation, not model migration or prompt-quality research.

## Scope results and user-facing acceptance

Read the outcome from
`execution_metadata.final_outcome.authored_scope_validation`; the protocol's
forensic metadata carries the same audit. The controlling count is **`persisted`**,
using **`unicode-whitespace-v1`**, not the legacy pre-render quality metric.

| Immutable case | Persisted words | Consulted pages | Expected outcome |
| --- | ---: | ---: | --- |
| compliant | 370 | 2 | Complete; independent quality warnings remain |
| partial | 389 | 1 | Complete with a visible partial/degraded warning |
| too_long | 660 | 2 | Validation failed; full result retained |
| 22_sources | 370 | 22 | Validation failed; final citation count cannot hide consultation |

The fixture also contains eight admission cases. Test the agreed semantics
without reimplementing DeepSearch's research execution in TraceLab.
`validation_failed` already exists in TraceLab's status, log, protocol and
artifact handling. Extend only demonstrated gaps.

Show planned words/pages and actual violation/unavailability reasons in the
existing preview/result views. Avoid making users interpret raw compiler JSON
to understand a limit. Preserve unknown state for old/missing audit data.
A preview describes a plan and does not prove current worker deployment.
Keep complete reports/protocols accessible; do not truncate output, erase a failed
artifact, silently retry paid work or turn partial results into uncomplicated success.

Cover the actual save/review journey, long links and warnings, keyboard focus,
overflow, and Light/Dark at 390/820/1440. No broad restyling or new scope-editor
system is part of this plan.

## Release gates and closure

Use [S63 acceptance](../reports/sprint-63/S63-RELEASE/validation.json) as historical
baseline, only where source hashes still match. The last accepted package was
2.1.1; choose a new patch only after checking the registry at build time.
Any changed MCP surface needs real-client/verb coverage and the published-artifact
smoke: pack, clean tarball install, publish, independent registry install and
actual entrypoint/CallTool checks. Learning #295 covers interactive npm browser approval.

No new server environment variable is expected. If one becomes necessary,
DoD-2 requires deployed configuration and real-flow evidence.
Retain the recorded TL baseline skips/quarantine and the two legacy CMOS failures.
The DS handoff separately reports 10 baseline failures and 10 opt-in live skips;
planning verified artifact hashes, not those runtime suites.

S64-ACCEPT must distinguish these two outcomes:

1. **TraceLab integration/release accepted:** source, canonical fixture, API/MCP/UI,
   published package as applicable, and exact TraceLab serving evidence pass.
2. **Cross-system #479 closed:** the above plus DeepSearch's reviewed/deployed
   runtime identity and separately authorized required-run acceptance.

If the second gate is unavailable, preserve **#479** open with its owner/evidence.
Do not create a duplicate successor or claim worker rollout. A truthful TL-only
closeout can record the external remainder. Prepare the DS evidence reply; sending
a new message remains a separate user instruction.

The eleven unselected records are
**#400/#403/#406/#407/#415/#422/#431/#448/#452/#454/#477**.
No sharing, cost-policy, hub/connector, language-preference or Space-resync work is
implicitly included.

## Fresh build entry

1. Read root `agents.md`, `cmos/agents.md`, this handoff and the CMOS missions.
2. Use the canonical CMOS root for review, health, sprint/decision reads.
3. Start a fresh isolated build from the committed **`codex/sprint-64-plan`** tip;
   inspect later main and upstream changes before substituting any pin.
4. Open a build session and start **S64-VENDOR** explicitly. First start activates
   the sprint; follow the identity-sync runbook then. Planning keeps S63 completed
   identity and leaves S64 dates unset.
5. Enforce Requires order, capture deviations/decisions, and commit at coherent
   boundaries. Do not use alphabetic queue order as delivery order.

