# Sprint 60 — Finish the Librarian

Planned 2026-09-29 in CMOS session **PS-2026-09-29-002**, decision **#551**.
CMOS is authoritative for mission criteria, dependencies and status. This handoff explains the build sequence and boundaries; it is not a second backlog.
Guiding templates: [roadmap](../foundational-docs/roadmap_template.md) and [technical architecture](../foundational-docs/tech_arch_template.md).
Intent: [The Librarian roadmap](../foundational-docs/roadmap-sprints-57-60-the-librarian.md).

## Outcome and authorization

Derek asked: “open a planning session and get sprint 60 work detailed and ready to handoff to a fresh build session so we can wrap up the librarian arc and make sure its all ready to go.”
Asked whether organisation and duplicate suggestions should span projects, he chose **“One selected project.”**

A researcher can ask the Librarian to describe a project, review possible duplicates, organise research into collections, and assemble a cited report from those materials. They review and accept each change. The saved result retains its provenance and resolving citations. Existing conversation, mission authoring, Q&A and chunk search continue working.

This session performed planning and source inspection only. The sprint is **Planned**, all six missions are **Queued**, and no delivery dates have been invented. Starting REPORT-1 is the build-session sprint open. Password recovery stays in Sprint 61 (AUTH-1, AUTH-2).

## Build order

| Order | Mission | User-visible result | Depends on |
| --- | --- | --- | --- |
| 1 | **REPORT-1** | Report citations survive save, reopen and export; legacy gaps are represented honestly | — |
| 2 | **LIB-3** | Review/edit/accept a project-description draft, see provenance, and safely restore the previous value | REPORT-1 |
| 3 | **DUP-1** | Compare exact or probable duplicate documents and review remediation options | LIB-3 |
| 4 | **ORG-1** | Review themed document/chunk groups and save only the chosen collections | DUP-1 |
| 5 | **LIB-4** | Draft a report from reviewed material and explicitly save that exact draft | ORG-1 |
| 6 | **WALK-3** | Deployed end-to-end acceptance and an evidence-backed close of the arc | LIB-4 |

The Requires chain records the agreed delivery order, not just compile-time dependencies. CMOS does not enforce those edges at mission start: follow the order explicitly. Use a fresh build session per mission, and merge, deploy and verify the slice before starting the next, as in Sprint 59. A failing production check remains unfinished work for that slice.

## Settled product boundaries

- **One selected project.** Require and visibly display it for new workflows. Administrators still get only that project's inputs. A mixed-project collection must not silently broaden a report; show the selected-project subset for review or reject the input clearly.
- **Ask, review, accept.** No scan on page load, model regeneration on focus, scheduler, cron, autonomous write, or global suggestion inbox. Per-user/project draft state follows the existing Librarian storage convention. Only explicit acceptance changes a research artifact.
- **Description.** Show old and proposed text; allow editing and dismissal. Accept checks the expected current value/version, records minimal provenance and offers guarded restore. An empty project may be described from the user's stated intent, clearly distinguished from corpus claims.
- **Duplicates.** Documents are the comparison unit. Distinguish exact normalized text from probable overlap, cite the comparison evidence and disclose coverage. Keep-both/dismiss and existing document links are enough to act on the advice. Do not implement merge, delete, reparent or source rewriting in this workflow.
- **Organisation.** Suggest themed collections with exact membership. Users may rename groups, remove members and accept groups separately. Create new collections through existing operations; do not retag, move or rewrite existing records. A collection has no project foreign key: membership supplies its research context. Display its destination Space under existing ownership rules.
- **Reports.** Keep the existing **Report** artifact and the original DeepSearch result **Documents**. Draft from reviewed chunks or collections, then save the exact preview without a second model call. Save as a draft Report; existing finalization remains available. No bulk conversion or regeneration of historical reports.
- **Provenance.** Persist generated origin, accepting user/time, prompt/model, source identities and accepted value/membership as appropriate. A client-provided citation or origin label is not proof. Acceptance must be bound to a verifiable proposal and recheck source access/liveness.
- **Conversation remains free.** Decision #513 superseded the old rule that every turn must create an artifact. Corpus claims still need sources (#512); prompt shaping/world knowledge can be ordinary prose. Nothing writes unasked (#515).
- **Small implementation.** Extend existing services, provider seam and UI patterns. No new workflow framework, global background queue, provider migration or separate vector store. Record concrete schemas, budgets and candidate thresholds before code; these are implementation choices within the settled scope.

## Why report citations come first

Source inspection at `c0886e7` found:

1. `app/api/v1/reports.py::_build_report_detail` returns `citations=[]` even after creation returned citations.
2. `app/services/report_service.py::create_report` and `app/api/v1/synthesize.py::_create_report_from_synthesis` are two persistence paths. Both need to retain the effective mapping.
3. `app/services/synthesis.py::_process_citations` returns chunk IDs without the original numeric marker, and leaves unknown markers in the content. A returned array of two citations cannot reconstruct a draft that cited `[1]` and `[3]` by array position.
4. `ReportSource` records input sources; `ReportCitations` displays report-related Evidence ledger entries. Neither is the mapping from a particular claim's marker to the chunk that supports it (learning #261).
5. `auto_report.py` formats the DeepSearch result protocol and attaches up to ten chunks per result document. Those references must not be retroactively called proof of particular claims.

REPORT-1 must keep a validated, stable marker-to-source mapping through create/read/export, recheck source visibility, and show missing legacy mappings honestly. It must not fabricate citations for old reports or replace existing result documents. Next-step #405's artifact-choice question is settled by decision #551; the implementation remains open until REPORT-1 passes.

## Existing implementation to reuse

| Concern | Entry points |
| --- | --- |
| Librarian caller/project gates, provider seam, corpus-claim validation | `app/api/v1/librarian.py`, `app/services/librarian.py`, `app/services/librarian_model.py` |
| Project description update | `app/api/v1/projects.py`, `app/models/project.py`, `app/schemas/project.py` |
| Document liveness and read access | `app/services/document_policy.py` |
| Document content / chunk identity | `app/models/document.py`, `app/models/chunk.py` |
| Research-reuse search, not a ready-made document-dedup engine | `app/services/pedr/preflight.py` |
| Collection creation, document context and chunk membership | `app/services/collection.py`, `app/services/collection_context.py`, `app/api/v1/collections.py` |
| Partial save with retry using the existing collection | `frontend/src/components/librarian/ChunkList.tsx` |
| Synthesis and Report persistence/read/export | `app/services/synthesis.py`, `app/services/report_service.py`, `app/api/v1/synthesize.py`, `app/api/v1/reports.py` |
| Current Librarian modes and per-user draft state | `frontend/src/pages/librarian.tsx`, `frontend/src/lib/librarian/storage.ts` |
| Saved report and separate Evidence relationship panel | `frontend/src/pages/reports/[id].tsx`, `frontend/src/components/evidence/ReportCitations.tsx` |

Read immediate callers, ports/adapters and relevant tests before changing these seams. Update [collection context/report contract](../contracts/collection-context-and-reports.md) when its behavior changes. Do not implement a second citation validator that drifts from the established grounding rules.

## MCP and usage

New conversational proposal/review/accept endpoints follow LIB-1's **REST-only-by-design** classification. Record new UI operations in `cmos/contracts/mcp-parity-manifest.json`; do not manufacture a new MCP cluster for the assistant.

Existing `tracelab_report` create/get and `tracelab_collection` synthesize and `tracelab_search` ask must retain parity. The TypeScript create/get handlers currently forward `result.citations`, so verify actual propagation before assuming a package edit is needed. A changed MCP response contract requires the deployed-client regression in the root playbook even when a direct REST test passes. If package source changes, build before local tests and satisfy the clean published-artifact smoke gate; a tarball dry run alone is not proof of what npm serves.

Record paid draft/repair calls against the requesting user and selected project using the existing usage infrastructure. Saving, dismissing, restoring and reading a cached result do not represent fresh provider usage. Use the configured Librarian model seam; no model comparison or migration is part of S60.

## Validation and closure

Each mission's full acceptance criteria are in CMOS. All feature slices require:

- Meaningful tests of the human-control boundary, scope before model work, bad/stale source IDs, idempotent acceptance and liveness/access changes; mutation proofs for fabricated provenance/citations.
- Isolated database, Qdrant, model and outbound-service dependencies. Next-step #445 warns that the local `.env` can point tests at production Qdrant; prove the touched test paths cannot do that before running them. PostgreSQL tests are required for migrations and transaction/concurrency behavior, alongside relevant SQLite-backed tests.
- Relevant backend/frontend suites, changed-file lint, frontend types/build and built-browser checks. No `ruff format`. Run `node scripts/mcp_parity_audit.mjs` and `python3 cmos/scripts/validate_foundational_refs.py`.
- Deployed acceptance with an agreed test account/project, exact serving commit, resolving source links and secret-free receipts under `cmos/reports/sprint-60/<mission>/`. Confirm any new environment setting in deployment and run the actual flow (DoD-2).

WALK-3 combines the slices on the final deployed build in Light/Dark at 390/820/1440 with keyboard/focus/accessibility checks. It rechecks general conversation, cold-start mission drafting, separate create/submit, corpus Q&A and refusal, chunk listing and collection save, then the complete new description → duplicate review → collection → report journey. Test exports and published MCP reads too. Fix failures blocking those journeys; record unrelated debt explicitly.

A paid DeepSearch execution is not required solely to re-prove its already-accepted authoring path. If a real submitted run or Derek's own walkthrough is needed, coordinate it and state what was actually exercised. Agent verification must not be recorded as Derek's personal acceptance.

Before closing the sprint, run receipt re-verification against final HEAD (decision #509), rewrite the roadmap as outcomes, reconcile CMOS and its dashboard mirror, and carry unresolved work explicitly. Do not call the Librarian arc complete with a must-pass criterion skipped.

## Carried next-steps: disposition for this build

The 23 carried entries are not 23 additional missions.

| Entries | Disposition |
| --- | --- |
| **#453** plan Sprint 60 | Fulfilled by this planning session and its six missions |
| **#405** choose Report vs result Document | Artifact choice resolved in #551; implementation/legacy limitations owned by REPORT-1 and checked in WALK-3 |
| **#445** tests reaching production Qdrant | Validation prerequisite for touched S60 tests; implement only the needed isolation, with proof |
| **#446** smoke harness's Evidence mark-seen write; **#447** document overflow accessibility | Repair if they block the required walkthrough; do not suppress product writes or hide accessibility failures to make the run pass |
| **#412, #416** DeepSearch live log flush/model identity | Existing outbound message `1621f451` remains pending; no new message or DeepSearch changes authorized by this planning session. Record the live-log limitation at acceptance; do not invent its resolution |
| **#400, #403, #407** project sharing | Deferred by Derek's later #538 instruction; no new sharing data model or invitation gate |
| **#397** test timeout diagnostics; **#406** raw markdown claims; **#415** price policy; **#422** language preference; **#426** disabled-account sign-out; **#431** child Space drift; **#444** cache/admin diagnostics; **#448** dev-only theme test; **#449** old frontend docs; **#450** unused save-search props | Existing backlog, not extra S60 missions. Only a demonstrated blocker of this sprint's accepted flow warrants a scoped change |
| **#451** Railway configuration deadline; **#452** context size; **#454** hub package pin | Operational follow-ups outside this product scope. #451 records a 2026-12-01 warning and must not be lost; verify its current applicability before implementation |

## Fresh-session start

Use the current checkout's absolute project root with every CMOS call (on this machine `/Users/systemsystems/portfolio/TraceLab`); do not copy the stale Linux path in `cmos/agents.md`.

1. Run `cmos_review`, read root `agents.md` and `cmos/agents.md`, check database health and working-tree state. The local v2 MCP-only instruction supersedes the root's old CLI examples.
2. Read this file, decision #551, learning #261 and `cmos_mission(action="show", missionId="REPORT-1")`. Reconfirm it is the first unfinished mission.
3. Start the build session and REPORT-1 through CMOS. Starting the first mission activates the sprint. Run the [Sprint-Boundary Identity Sync runbook](../docs/operations-guide.md#sprint-boundary-identity-sync-runbook), including `sprint_tracking.current_sprint` (learning #247). Do not mark the sprint Active during planning merely to make the digest look current.
4. Record REPORT-1's concrete additive contract before coding, then prove the transient-citation defect with focused tests. No new research mission is necessary; the relevant behavior is in the tree.
5. Build, test, merge/deploy within the user's standing authorization, run live acceptance, record the receipt and complete only that mission. Hand the next mission to a fresh session. Do not create a new Codex task unless Derek explicitly asks.

Suggested opening prompt:

> Continue TraceLab Sprint 60 from cmos/planning/sprint-60-HANDOFF.md. Run cmos_review(), load both agents files, and read decision #551 and REPORT-1. Build REPORT-1 in this fresh session, verify it locally and on the deployed build, and record its acceptance before handing off LIB-3. Keep organisation and duplicate scope within one selected project; preserve explicit human acceptance and resolving citations. Sprint 61 password recovery is separate.
