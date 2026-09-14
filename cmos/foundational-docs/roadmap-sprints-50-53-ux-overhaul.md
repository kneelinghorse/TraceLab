# TraceLab — Vision and Roadmap: Recovery and the UX Overhaul (Sprints 50–53)

**Status:** living document. Authored 2026-09-12 at Sprint 50 open. Owner: Derek.
**Authority split:** this document is authoritative for *intent* (why, what, in what order). The CMOS sprint and mission records are authoritative for *status*. When they disagree, fix the one that drifted and note it here.
**Update cadence:** at every sprint open and sprint close, alongside the Sprint-Boundary Identity Sync runbook (cmos/docs/operations-guide.md). A sprint may not close until its section below says what shipped and what moved.
**Grounding:** TraceLab UX Baseline (artifact, 2026-09-12); research mission TL-UX-R001 (DeepSearch, 178 sources, report `f4d46a82`, document `e51e0fe0`, 50 ledger entries); d592c92 lost-logic audit (cmos/reports/audits/); CMOS decisions #377 (recovery approach) and #379 (redesign direction); learnings #142–#144.

---

## Vision Statement

TraceLab is a research knowledge platform run by one expert operator and a growing set of autonomous agents. Documents are ingested into projects, chunked, embedded and searched through the PEDR retrieval stack; DeepSearch missions run long, paid research jobs and return reports; the Evidence Ledger records every sourced claim those runs and agents produce, with its disposition and provenance. Collections bundle chunks into context, and reports synthesize them. Every one of those objects is reachable through the published MCP so agents work in the same system the operator sees.

The problem the next four sprints solve is that the interface does not show the product. The shipping UI is a flat list-plus-detail shell across seven peer entities, in three coexisting visual systems, with no home screen, five features reachable only by typed URL, an evidence ledger with no page at all, and an operations console whose headline numbers are wrong. Separately, a March 2026 "formatting" commit silently reverted Sprint 33–38 behavior in 51 places; 29 of those are still missing in production, including search-quality tuning and the ingestion edge-materialization stage. Both problems hide the same thing: what the system actually did and what it knows.

The people who benefit are the operator, who should see what needs attention and what changed while away within one screen of logging in; the agents, whose outputs become auditable back to evidence and whose MCP view matches the UI; and occasional collaborators in Spaces, who get a coherent product rather than a developer console.

**Core Philosophy:** Truth in data, evidence as the connective tissue, one design system. Every number on screen comes from a server-side aggregate. Every synthesized claim links to what it drew on. Every screen is composed from OODS tokens and components.

---

## Where We Are (September 2026 baseline)

**Platform.** Sprint 49 closed 2026-08-22 with 12 of 12 missions: CI enforcement restored (six required checks), PEDR and RAG surfaces Space-scoped under live RBAC, Evidence Ledger v1 with the `tracelab_evidence` MCP cluster, the DeepSearch writer channel, and retrieval integration. Production runs `main` on Railway; `api.tracelab.aquex.ai` and `tracelab.aquex.ai`.

**Losses to recover.** Commit d592c92 (2026-03-13, PR #198) was a ruff pass run on a pre-Sprint-33 checkout and committed over main. A 16-group adversarial audit on 2026-09-12 confirmed 51 logic losses: 20 re-implemented later, 2 partial, 29 still missing. High severity: ingestion Stage-6 incremental edge materialization; the mission-events and decision-links routers unmounted; PEDR layer diagnostics and the `degraded` flag. Medium: PEDR graph defaults reverted to pre-tuning values; per-layer fallbacks; semantic edge types `co_occurs` and `topic_similar`. One consequence, the project-stats cache collision, is fixed in PR #252.

**Interface.** Measured on 2026-09-12 across 27 routes at 1440 and 390 px with axe-core: three themes (glass login and search, light Tailwind pages, an accidental OS-dark variant), a duplicate authenticated header on every page, all 27 routes scrolling sideways at phone width, 215 color-contrast nodes, missing `lang` and `main` landmarks everywhere, four pagination implementations, fourteen `alert()` and nine `confirm()` sites, five orphaned components including the evidence card, and a console that reports 100 missions where production holds 433.

**Research.** TL-UX-R001 compared Dovetail, Condens, Aurelius, NotebookLM, Elicit, Perplexity, Linear, Notion and Obsidian. Its primary recommendation: a task-centric Home (active work, needs-attention, recents, global search), missions rendered as inspectable background jobs with a progress sidebar, evidence as the connective layer every report and mission links back to, a container/data/synthesis hierarchy instead of seven peers, keyboard-first command palette, and a migration path whenever the IA changes.

**Design system.** OODS Forge is healthy: 109 stable components, brand-A tokens built for light, dark and high-contrast, packages `@oods/tokens`, `@oods/tw-variants`, `@oods/components-react`. The registry has no research-domain objects yet.

---

## Target Experience

### Information architecture

Entities are grouped by role, not listed as peers. The old routes keep working through redirects until each surface is rebuilt.

```
Home                          what needs attention · active runs · recents · activity · ⌘K
├── Projects        container  a project bundles its documents, evidence, collections,
│                              missions and reports (the notebook model)
├── Data
│   ├── Documents              ingested sources and their chunks
│   └── Evidence               the ledger: sourced claims with disposition and provenance
├── Context
│   └── Collections            chunk bundles that double as mission context spaces
├── Jobs
│   └── Missions               background research runs; queue folded in; exceptions first
├── Synthesis
│   └── Reports                synthesized outputs with citations that resolve to evidence
├── Search                     PEDR search + RAG answer; also the ⌘K palette's search
└── Admin                      Users · Spaces · Observability · Corrections
```

### The surfaces, in the order they ship

1. **Shell, tokens, themes** (UX-0). One sidebar shell around every existing page. OODS tokens replace the HSL variables and the Tailwind palette in pages. System-respecting theme with an in-app toggle; light and dark are first-class, high-contrast optional. Landmarks, skip link, focus states, responsive drawer below 900 px. The command palette exists from day one, even if it only jumps between sections and runs a search.
2. **Object model in Forge** (UX-1). Project, Document, Chunk, Collection, Mission, Report and Evidence authored as OODS objects with their real states and traits; Space maps to Organization. This lets `design_compose` and `design_preview` generate trait-driven screens that the build missions implement, instead of intent-only guesses.
3. **Home** (UX-2). Attention queue ordered by focus (validation_failed, blocked, stalled, completed-unreviewed), active missions with step progress, recents and favorites, recent agent and evidence activity, search entry. Fed by one aggregate endpoint under RBAC scoping.
4. **Evidence** (UX-3). Browse, filter, search; entry detail with claim, snippet, source, sightings and provenance; inbound links from reports, missions and documents.
5. **Admin observability** (UX-4). The console becomes an admin page whose every figure is a server-side count. Duplicate console pages retire behind redirects.
6. **Missions as inspectable jobs** (Sprint 51). Authoring, a run view with named steps and live logs, results and evidence in one place, leave-and-return semantics, exceptions-first queue.
7. **Projects as bundles; Documents, Collections, Reports rebuilt** (Sprint 51). A project hub with tabs; collections as context spaces reusable by missions; reports whose citations resolve to evidence.
8. **Search and the full command palette** (Sprint 51). Search rebuilt in the new system; the palette reaches every entity and action.
9. **Route migration** (Sprint 51). Old URLs redirect; nothing a user or agent bookmarked breaks.
10. **Relationship graph, saved dashboards, inbox** (Sprint 52). The Obsidian-style evidence graph, Linear-style saved exception views, and a priority inbox with completion notifications.

### Rules that hold on every surface

- Every displayed count or status comes from a server aggregate; no page computes totals from one page of results.
- Every report claim, mission result and agent output can be followed to the evidence it drew on.
- Everything the UI can show, the MCP can read; new aggregates ship with an MCP or REST equivalent.
- Both themes, phone width, and accessibility are acceptance criteria, not polish.
- Old routes redirect; data is never restructured without a mapping path.

---

## Architecture Overview

```
┌───────────────────────────────── Operator & agents ─────────────────────────────────┐
│  Browser (Next.js pages router)                 MCP clients (@aquex/tracelab-mcp)    │
│  ┌──────────────────────────────┐               ┌──────────────────────────────┐    │
│  │ Shell · ThemeProvider · ⌘K   │               │ tracelab_* clusters          │    │
│  │ OODS tokens + tw-variants    │               │ (search, project, mission,   │    │
│  │ OODS components-react        │               │  execution, evidence, ...)   │    │
│  └──────────────┬───────────────┘               └──────────────┬───────────────┘    │
└─────────────────┼──────────────────────────────────────────────┼────────────────────┘
                  ▼                                              ▼
┌──────────────────────────────── FastAPI (app/) ─────────────────────────────────────┐
│ routers (thin) → services → ports/adapters    RBAC: authorize_or_403, accessible_filter│
│ NEW: /home and /admin/stats aggregates · evidence read routes · mission run view      │
│ RESTORED: mission_events + decision_links routers · PEDR diagnostics · edge stage 6   │
└──────┬──────────────────────┬───────────────────────┬──────────────────┬─────────────┘
       ▼                      ▼                       ▼                  ▼
   PostgreSQL             Qdrant (PEDR)         DeepSearch worker    Evidence Ledger
   (Alembic sole          semantic + graph      (paid runs, HMAC      (ledger_entries,
    schema authority)     layers                 webhook → writer)     notes, sightings)
```

Key decisions carried forward: hexagonal boundaries stay (routers → services → ports); Alembic is the sole schema authority; RBAC is router-level authentication plus per-id authorization; DeepSearch remains a worker reached through the mission lifecycle, never an HTTP dependency of the UI.

---

## Design System Strategy (OODS Forge)

- **Tokens first.** `@oods/tokens` CSS is the only source of color, spacing and type in pages. The Tailwind config loads `@oods/tw-variants` and sets `darkMode: 'class'`. A grep or lint gate rejects raw palette classes in `src/pages` for touched files.
- **Components where they fit.** `@oods/components-react` primitives (Button, Card, Table, Tabs, Badge, SearchInput, FilterPanel, PaginationBar, DetailHeader, StatusBadge, StatusTimeline, Stack, Grid, Text) replace per-page one-offs. A component that does not fit the pages router is wrapped, not forced.
- **Objects drive composition.** UX-1's accepted schemas and retained `design_compose`/`design_preview` receipts at 390/820/1440 are the starting references for implementation. Reuse those accepted artifacts when the composition is unchanged, then bind real API data and validate the built and deployed TraceLab screens. A fresh Forge setup is not a prerequisite to TraceLab implementation. New object authoring or registry changes remain Forge-owned. Receipts live under `cmos/reports/sprint-N/oods-previews/`.
- **What stays.** Next.js pages router, SWR, react-hook-form and zod stay for this program. Tailwind stays as the utility layer under the token plugin.
- **Contract.** `cmos/contracts/oods-object-model.md` (UX-1) maps every Pydantic schema field to the object field or trait it feeds so the API and the design system cannot drift apart silently.

---

## Implementation Plan

### Sprint 50 — Recovery and Redesign Foundation (completed 2026-09-13)

**Goal:** restore what was lost, then ship the foundation every later surface builds on, visible in production on every route.

| Mission | Deliverable | Depends on |
|---|---|---|
| RECOVER-1 | High and medium d592c92 restores: edge materialization at ingest, router mounts with RBAC review, PEDR diagnostics and `degraded`, graph defaults and fallbacks, semantic edge types | — |
| RECOVER-2 | Low restores (telemetry envelopes, test engine kwargs, `content_tsv` decision), completeness sweep, formatting-commit guard | RECOVER-1 |
| UX-0 | OODS tokens, theme system, new shell across all routes, landmarks, responsive nav, palette stub | — |
| UX-1 | Research-domain object model in the Forge registry, saved schemas, preview receipts, field-mapping contract | — (cross-repo) |
| UX-2 | Home with server-side aggregates, attention queue, active runs, recents/favorites, activity | UX-0, UX-1, RECOVER-1 |
| UX-3 | Evidence ledger UI and inbound links from reports, missions, documents | UX-0, UX-1 |
| UX-4 | Admin observability with truthful stats; console retired behind redirects | UX-0; enabled by RECOVER-1 |
| UX-5 | Shared primitives, state handling, dead-code sweep, ESLint zero, test side-effect hygiene | alongside UX-0 |

**Exit criteria:** every route renders inside the new shell in both themes on `tracelab.aquex.ai`; Home is the first screen; admin stats equal database counts; evidence has a page; the 29 missing behaviors are restored or explicitly declined with a reason.

**Shipped:** all eight Sprint 50 missions are implemented and production-verified. RECOVER-1/2 account for all 51 audit findings (43 restored, seven superseded with reasons, one declined against schema evidence), restore ingestion edges/PEDR diagnostics/router boundaries/telemetry, and add the formatting-loss guard. UX-0/1 establish the responsive OODS shell, themes, object contract and accepted retained previews. UX-2 delivers Home; UX-3 adds evidence browsing, detail and inbound links; UX-4 replaces the console with admin observability/corrections and server-side totals; UX-5 shares controls, fixes request/empty/not-found states, removes unused components and makes ESLint a failing CI check.

**Production evidence:** the final [31-route baseline](../reports/sprint-50/ux-5-production-smoke/summary.json) passed all 124 light/dark × phone/desktop measurements through direct browser requests to the deployed API, with no critical/serious axe findings, horizontal overflow or browser/API errors. Screenshots are adjacent to that receipt. Home/admin counts were checked against production: 433 missions (424 completed, one blocked, eight validation failures), 51 projects, 1,584 documents and 16,431 chunks. The research evidence session has 370 entries (191 supporting, 170 background, nine rejected); the original 50-entry research baseline above is historical. See the [UX-3 receipt](../reports/sprint-50/ux-3-validation.json), [UX-4 receipt](../reports/sprint-50/ux-4-validation.json) and [UX-5 receipt](../reports/sprint-50/ux-5-validation.json) for exact revisions and observations.

**Validation and limits:** the final frontend has 115 passing unit tests, 22 passing browser tests, zero ESLint errors/warnings and a passing production build. The required backend suite and PostgreSQL 15 integration pass; their explicit skips/quarantine counts and the existing advisory full-Ruff/mypy failures remain recorded in the UX-5 receipt. Production UI smokes are read-only; mutations are exercised through deterministic unit/browser/API tests.

**Moved:** no unfinished Sprint 50 mission is carried. Sprint 51 remains planned and unopened: job run views, project bundles, deeper document/collection/report workflows, search and route migration retain their original scope below. Closing the foundation does not claim the entire four-sprint redesign is finished.

### Sprint 51 — The Working Surfaces (opened 2026-09-13)

**Goal:** rebuild the pages people and agents live in, on the object model and the shell, and make the theme selector truthful.

**UX-1 implementation references:** use the [API-to-object contract](../contracts/oods-object-model.md) and [saved-schema index](../reports/sprint-50/oods-previews/schema-summary.json), with [all 20 compositions in both themes at 390/820/1440](../reports/sprint-50/oods-previews/preview-summary.json). UX-6 starts from Mission list/detail/timeline/workflow; UX-7 from Project, Document and inline Chunk; UX-8 from Collection and Report. The retained [Mission detail preview](../reports/sprint-50/oods-previews/mission-detail-light/react/receipt.json) and [Evidence detail preview](../reports/sprint-50/oods-previews/evidence-detail-light/react/receipt.json), with adjacent dark-theme receipts, establish the structural references. These use synthetic fixtures; bind real API data and regenerate phone/tablet/desktop previews before implementing each surface.

| Mission | Deliverable | Depends on |
|---|---|---|
| THEME-1 | Truthful System / Light / Dark selector, resolved System label, correct first paint, semantic prose and removal of no-op `dark:` utilities; High contrast deferred to THEME-2 | — (first; enables UX-6..UX-9) |
| UX-6 | Missions as inspectable jobs: exceptions-first list with the queue folded in, run view with named phases and truthful logs, authoring with inline contract preview, cancel and re-run | THEME-1 |
| UX-7 | Projects as bundles + Documents: hub tabs, upload with per-file progress, document detail with chunks and evidence; per-user favorites on Home (closes the decision #395 deferral) | THEME-1 |
| UX-8 | Collections as context spaces + Reports: instructions, seed a mission, citations resolve to evidence, export retained | THEME-1, UX-6 |
| UX-9 | Search + command palette: one search surface, palette reaches every entity, recent and saved searches, actions, keyboard navigation documented | THEME-1 |
| UX-10 | Route migration: every pre-overhaul URL redirects, MCP links canonical, map maintained here, deprecated aliases listed for Sprint 53 | UX-6, UX-7, UX-8, UX-9 |
| CI-2 | Honest lint lanes: fix, ratchet or drop the perpetually red advisory ruff-full and mypy jobs | — |

- **THEME-1 Truthful themes.** Ship System / Light / Dark with the resolved System label, authoritative head bootstrap and preserved hydration, semantic prose, and removal of 986 no-op `dark:` utilities across 30 files (987 literal occurrences included one TypeScript parameter). **Derek deferred High contrast on 2026-09-13, decision #408:** keep it out of the selector and resolve stored `hc` to System. Both the installed tokens and prepared replacement fail active-text contrast; preserve all 62 failed HC measurements. **THEME-2 is deferred to Sprint 54** for certified token acceptance, HC wiring and a clean three-theme baseline. Current verified `114a268` tarballs remain installed. Forge PR107 is merged, but consumer certification remains outstanding; merge alone does not establish acceptance.
- **UX-6 Missions as inspectable jobs.** New authoring flow (contract preview inline), run view with named steps from DeepSearch phases, logs that state unavailability truthfully while live streaming stays dormant, results and evidence tab, exceptions-first list with the queue folded in, cancel and re-run.
- **UX-7 Projects as bundles and Documents.** Project hub with Overview, Documents, Evidence, Collections, Missions, Reports tabs; upload with per-file progress; document detail with chunks and evidence references; per-user favorites surfaced on Home.
- **UX-8 Collections as context spaces and Reports.** Collections carry instructions and documents and can seed a mission; report detail whose citations resolve to evidence; export retained.
- **UX-9 Search and the command palette.** Search rebuilt on tokens; palette reaches every entity, recent searches, saved searches and actions; keyboard navigation documented.
- **UX-10 Route migration.** Every pre-overhaul URL redirects to its successor; MCP responses carry the new canonical links; a mapping table lives in this document; deprecated aliases listed for Sprint 53.
- **CI-2 Honest lint lanes.** No lane stays red as "advisory"; each is required and green, ratcheted with a shrinking count, or removed with the reason recorded.

**Definition of Done additions (decisions #400, #408):** re-run the 31-route direct-browser production baseline at every UI mission close in Light and Dark at 1440/390 (124 checks); High contrast acceptance moves to THEME-2. Deployed smoke is accepted only after Railway reports SUCCESS for both services, with deployment ids in the receipt under `cmos/reports/sprint-51/`.

**Exit criteria:** no page under `src/pages` uses the pre-overhaul shell or palette; the theme selector lists exactly the themes the tokens define and System reports what it resolved to; a mission can be authored, watched to completion and audited to evidence without leaving the UI; the Playwright baseline shows zero overflow and zero critical or serious axe findings on all routes.

### Sprint 52 — Relationships, Attention and Parity

**Goal:** make the system's structure visible and keep the operator's attention where it belongs.

- Evidence and relationship graph view (Obsidian pattern) over projects, documents, evidence and reports.
- Saved exception dashboards ("at risk missions", "unreviewed completions") on the aggregates.
- Priority inbox: agent failures, completions, new evidence; email or in-app notification on mission completion.
- MCP parity audit: every UI aggregate and action has an MCP or REST equivalent; gaps become missions.
- Documentation refresh: `docs/frontend_architecture.md` and `cmos/foundational-docs/technical_architecture.md` rewritten to the new system.

### Sprint 53 — Hardening and Measurement

**Goal:** prove the overhaul holds and automate the proof.

- Accessibility AA sweep including the high-contrast theme.
- Performance budgets on Home, search and mission run view.
- Stage1 drift scan against the April 2026 fingerprint baseline; results archived as the new baseline.
- Post-deploy frontend smoke wired into CI (the S48 lesson), including a phone-width overflow check.
- Retirement of every legacy component and route alias that Sprint 51 marked deprecated.

### Beyond Sprint 53 (not scheduled)

- Collaboration chrome (mentions, shared views) only if collaborators in Spaces become real users.
- Perplexity-style trainable context: collection instructions applied to every mission that uses it.
- Graph-first home as an alternative to the attention-first home, if the graph proves more useful than the queue.

---

## Definition of Done for UI Missions

A UI mission is not done until all of the following are true. Each rule exists because its absence has already cost a sprint.

1. Production build passes in CI and the deployed site is smoke-tested on `tracelab.aquex.ai` after the merge (S48: a broken frontend shipped with green unit tests).
2. Screenshots at 1440 and 390 px in both themes are archived under `cmos/reports/sprint-N/`.
3. Zero horizontal overflow at 390 px on touched routes; zero critical or serious axe findings on touched routes.
4. Every number on a touched page is checked against the API's own totals in production.
5. No `alert()` or `confirm()`; loading, empty and error states exist and are distinct from not-found.
6. No hardcoded palette classes in touched pages; tokens only.
7. Old routes touched by the mission redirect to their successors.

---

## Success Metrics

### Truth and coverage

- **Aggregate accuracy:** 0 difference between any displayed total and the database count, checked on every deploy.
- **Evidence reachability:** 100% of reports and completed missions link to at least one evidence entry or state explicitly that none exists.
- **Recovery completeness:** 51 of 51 audit findings restored, superseded with reason, or declined with reason.

### Interface quality

- **Phone width:** 0 of N routes with horizontal overflow (27 of 27 today).
- **Accessibility:** 0 critical and 0 serious axe findings on all routes (215 contrast nodes and 27 missing `lang` today).
- **Theme parity:** 100% of routes render correctly in light and dark; no page mixes systems.
- **Lint:** 0 ESLint errors enforced in CI (12 today).
- **Duplication:** one pagination, one status badge, one dialog, one toast component in use.

### Operator experience

- **Time to status:** what needs attention is visible on the first screen after login, without navigation.
- **Mission audit:** from a mission or report, the underlying evidence is one click away.
- **Agent parity:** every aggregate the UI reads is available through the MCP or REST.

---

## Key Design Principles

1. **Truth in data.** Server-side aggregates only; a wrong number is a bug with the same severity as a wrong record.
2. **Evidence is the product.** The ledger is the connective tissue; surfaces exist to show what the system knows and how it knows it.
3. **Roles before types.** Containers, data, context, jobs and synthesis are legible before entity names are.
4. **Operator plus agents.** One screen serves a human asking "what needs me" and an agent whose output must be auditable; MCP and UI see the same system.
5. **One system.** OODS tokens and components everywhere; no third theme, no per-page primitives.
6. **Restore before you rebuild.** Lost behavior is restored with a test before new surfaces depend on it.
7. **Nothing breaks silently.** Route redirects, mapping paths, deploy smoke, and a guard against formatting-commit losses.

---

## Risks and Mitigations

- **Risk:** OODS React components do not fit the Next.js pages router cleanly. **Mitigation:** tokens and the shell ship first (UX-0) and do not depend on component ports; components are wrapped where they fit and skipped where they do not; the object model still drives composition.
- **Risk:** "Full overhaul" scope expands without bound. **Mitigation:** sprint gates with exit criteria above; the shell ships around existing pages before any page is rewritten; Sprint 51 is scoped now, Sprint 52 and 53 are re-planned at Sprint 51 close.
- **Risk:** Regressions while rebuilding pages that agents rely on. **Mitigation:** the Playwright baseline runs per mission; MCP contract tests remain required; route redirects ship with each rebuild.
- **Risk:** Another silent mass loss like d592c92. **Mitigation:** RECOVER-2 adds a guard that flags formatting-labeled commits with net logic deletions; quarantined tests need a cited reason; learnings #142 and #144 are evergreen.
- **Risk:** The Forge object model is a cross-repo dependency. **Mitigation:** UX-1 is accepted: Forge PR105 is merged, all seven research objects and the Mission workflow were verified through a fresh MCP client, and the final runtime sweep passed. TraceLab reuses that [acceptance evidence](../reports/sprint-50/ux-1-forge-acceptance.json), mapping and retained previews. Forge still owns future review, fixes, CI, merge and registry activation; a new cross-project action or message requires explicit user authorization. This ownership boundary does not block ordinary TraceLab implementation (decision #396, learning #159).
- **Risk:** Research evidence is thin where vendors block crawlers (Perplexity, NotebookLM). **Mitigation:** those cells are marked as secondary in the ledger; decisions cite the primary-source patterns (Condens, Dovetail, Linear, Notion, Elicit) first.

---

## Route Migration Map (maintained from Sprint 51)

| Old route | Successor | Sprint | Behavior |
|---|---|---|---|
| `/` | `/` | 50 (UX-2) | Home returns 200, replacing the former redirect to missions |
| `/console` | `/admin/observability` | 50 (UX-4) | Permanent 308 |
| `/console/missions` | `/missions` | 50 (UX-4) | Permanent 308 |
| `/console/missions/{id}` | `/missions/{id}` | 50 (UX-4) | Permanent 308 |
| `/console/corrections` | `/admin/corrections` | 50 (UX-4) | Permanent 308 |
| `/invites` | `/settings#invites` | 50 (UX-5) | Permanent 308; query precedes fragment |
| `/search/results` | `/search` | 51 (UX-9) | Permanent 308 |
| `/missions/queue` | `/missions?view=queue` | 51 (UX-6) | Permanent 308; destination selects the queue view |

All redirects retain query parameters, including repeated values. The destination's explicit `view=queue` wins over an incoming `view`. Home is a replacement page, not an alias or a self-redirect. The executable map is `frontend/src/lib/route-migrations.json`; unit tests bind it to this maintained table, and the production smoke walks every row.

### Deprecated aliases to retire in Sprint 53

- `/console`
- `/console/missions`
- `/console/missions/{id}`
- `/console/corrections`
- `/invites`
- `/search/results`
- `/missions/queue`

Keep these redirects active through Sprint 52. Canonical Home `/` is retained. Source URLs, authored references and exported document contents are preserved as evidence; this migration applies to generated application navigation links.

---

## Terminology

- **Evidence entry:** a sourced claim in the ledger with claim, snippet, source URL, disposition (supporting, contradicting, rejected, background), tags, session key and mission provenance.
- **Attention queue:** the ordered list on Home of items needing the operator: validation failures, blocked and stalled runs, completed runs not yet reviewed.
- **Context space:** a collection that carries instructions and documents and can seed a mission.
- **Aggregate endpoint:** a server route that returns counts and summaries computed in the database, the only permitted source for displayed totals.
- **Recovery:** the restoration of behavior lost to commit d592c92, always against the reference tree at `8b049ed`.

---

## Change Log

- **2026-09-12** — Created at Sprint 50 open from the UX Baseline, TL-UX-R001, the d592c92 audit, and Derek's seven redesign decisions (decision #379). Sprint 50 missions RECOVER-1/2 and UX-0 through UX-5 recorded in CMOS.
- **2026-09-13 UTC** — Removed the stale cross-repository fallback to match the user's ownership correction (decision #391, learning #155). Forge completion evidence remains an acceptance dependency; TraceLab PR257's merge alone does not close UX-1.
- **2026-09-13 UTC, acceptance reconciled** — UX-1's subsequent acceptance and final Forge runtime success resolve the earlier handoff dependency. Accepted retained schemas/previews support TraceLab implementation without a new setup authorization. Home, Evidence and admin observability are deployed and production-verified; UX-5 closes after its own deployment checks.

- **2026-09-13 UTC, Sprint 50 close** — Recorded deployed recovery and UX-0–5 outcomes, exact validation receipts, and no unfinished carryover. Sprint 51 remains planned.
- **2026-09-13 UTC, Sprint 51 open** — Sprint 51 created in CMOS (THEME-1, UX-6..UX-10, CI-2; identity synced to `sprint-51-active`) and this section re-planned from it: THEME-1 added at open on Derek's direction, favorites carried from decision #395 into UX-7, CI-2 from learning #165. Sprint 50 close hygiene: regenerated sprint-37/38 e2e receipts discarded (timing-only reruns over recorded evidence), merged local branches pruned, `cmos/context/MASTER_CONTEXT.json` export refreshed from the CMOS database and its `.backup-*` files removed, mission-authoring contract commit pin set to `21271b5`.

_Truth in data, evidence as the connective tissue, one system._
