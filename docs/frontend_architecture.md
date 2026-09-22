# Frontend Architecture (as built)

As of main `bf750cb70550a33f179b0ca4c2518454122ff87c` (2026-09-15, end of the Sprint 52 build). This page describes the
frontend that ships from `frontend/` today. Intent and the sprint plan live in the living
roadmap, `cmos/foundational-docs/roadmap-sprints-50-53-ux-overhaul.md`; CMOS holds mission
status. The Sprint 03 "Mission Protocol UI" notes this page replaces are in git history
(`git show 3a498c6:docs/frontend_architecture.md`).

## Stack

- **Next.js ^16 with the pages router**, React 19.2, SWR ^2.3 for data fetching and polling,
  react-hook-form ^7.66 with zod ^4 for authoring forms, date-fns, react-markdown; Tailwind CSS 3.4
  through PostCSS (`frontend/postcss.config.mjs`, directives in `frontend/src/styles/globals.css`); see
  `frontend/package.json`.
- **Design tokens.** `@oods/tokens` and `@oods/tw-variants` are vendored as immutable tarballs
  (`frontend/vendor/oods-tokens-0.1.0.tgz`, `frontend/vendor/oods-tw-variants-0.1.0.tgz`) with provenance in
  `frontend/vendor/oods-provenance.json` (OODS-Forge checkout `114a268`), and wired through
  `frontend/tailwind.config.ts`. There is no `@oods/components-react` dependency: every component is
  local to this repository.
- Node 22 or newer. `npm run build` runs the token gate first (`frontend/scripts/check-token-colors.mjs`)
  and then `next build`; Railway serves the result with `next start`.

## Routes (`frontend/src/pages`)

| Route | File | Notes |
| --- | --- | --- |
| `/` | `index.tsx` | Home: recent activity (newest first), active runs, recent reports and projects, favorites, evidence activity |
| `/projects`, `/projects/[id]` | `projects/index.tsx`, `projects/[id].tsx` | Project list and bundle |
| `/documents`, `/documents/[id]`, `/documents/upload` | `documents/*.tsx` | Document list, detail (full text first via `GET /documents/{id}/content`, Overview/Chunks/Evidence tabs, `?tab=` deep links, Open report/mission links from the server-resolved `links`), upload |
| `/collections`, `/collections/[id]` | `collections/*.tsx` | Collections and collection context |
| `/missions`, `/missions/[id]`, `/missions/new`, `/missions/queue` | `missions/*.tsx` | Mission list with views and reason filters, run detail, authoring, queue |
| `/reports`, `/reports/[id]` | `reports/*.tsx` | Reports |
| `/search` | `search/index.tsx` | Research search |
| `/librarian` | `librarian.tsx` | The Librarian (Sprint 57, LIB-1): conversation with typed provenance (prose vs cited corpus claims), mission draft with compiled contract and lint, explicit creation of a draft mission. Since LIB-2 the conversation, project and draft persist per user in localStorage (`lib/librarian/storage.ts`), a fresh draft takes focus, the three-step strip (`components/librarian/LibrarianSteps`) and the mission page's `?from=librarian` notice share one "don't show again" preference |
| `/graph` | `graph.tsx` | Relationship neighborhood (Sprint 52, UX-11) |
| `/evidence`, `/evidence/[id]` | `evidence.tsx`, `evidence/[id].tsx` | Evidence browser and entry detail (Open report for the capturing mission's result report, from the `mission_result` link flag) |
| `/saved-searches` | `saved-searches.tsx` | Saved searches |
| `/settings`, `/device` | `settings.tsx`, `device.tsx` | Account settings, device-code approval |
| `/admin/users`, `/admin/spaces`, `/admin/observability`, `/admin/corrections` | `admin/*.tsx` | Admin surfaces behind `RequireAdmin` |

`_app.tsx` mounts `AuthProvider`, `RoleProvider`, `ThemeProvider` and `AppShell`; `_document.tsx`
carries the theme bootstrap. Legacy routes redirect: `frontend/src/lib/route-migrations.json`
(eight mappings) feeds `redirects()` in `frontend/next.config.ts`, and the canonical map is the
roadmap's Route Migration Map section. Redirects are covered by `frontend/tests/e2e/route-migration.spec.ts`.

## Shell

- `frontend/src/components/AppShell.tsx`: skip link, the sidebar (`Navigation.tsx`), a sticky toolbar with
  the active section label and the ⌘K search control, exactly one
  `<main id="main-content">`, a mobile navigation drawer built on a native `<dialog>`, and
  `CommandPalette.tsx`.
- **Authentication.** `frontend/src/contexts/AuthContext.tsx` owns the session and
  `frontend/src/lib/auth/storage.ts` persists it in local storage under `tracelab.auth.v2`;
  `components/AuthGate.tsx` wraps every page; a 401 from any request clears the session
  through the `tracelab:auth-expired` window event in `lib/api/http.ts`.
- **Role channel.** `frontend/src/contexts/RoleContext.tsx` reads the role from a live
  `GET /api/v1/auth/me` only, never from the token or stored auth; `components/RequireAdmin.tsx` fails
  closed and admin navigation groups are filtered by `useRole().isAdmin`.
- **Themes.** `components/ThemeSelect.tsx` and `contexts/ThemeContext.tsx` over `lib/theme.ts` offer
  System, Light and Dark, persisted per user (`tracelab.theme.v1:<user id>`) and applied through
  `data-theme` with semantic tokens only: no fixed palette classes and no `dark:` utilities, enforced by
  `frontend/scripts/check-token-colors.mjs`. High contrast is deferred to THEME-2 in Sprint 54.
- **Command palette.** ⌘K / Ctrl-K opens `CommandPalette.tsx`: name lookup through
  `lib/api/navigation.ts` (`GET /api/v1/navigation/search`), recent and saved searches, saved mission
  views, and "Go to" entries derived from `navigationGroups`.

## Data layer (`frontend/src/lib/api`)

- `http.ts` builds every request from `NEXT_PUBLIC_API_BASE_URL` plus `NEXT_PUBLIC_API_PATH_PREFIX`
  (default `/api/v1`), attaches the bearer token, raises `HttpError` with the status, and turns a 401
  into a logout.
- One client module per noun: admin, admin-stats, auth, collections, console, deviceAuth, documents,
  activity, evidence, graph, home, missions, navigation, projects, reports, savedSearches,
  search, settings.
- `timestamps.ts` exports `parseApiTimestamp`, which treats offset-free API datetimes as UTC; pages
  must use it instead of `new Date(value)`: learning #173 recorded offset-free timestamps showing five
  hours ahead in Chicago.
- SWR keys include the user id. Home and the activity summary poll at the server's `refresh_seconds`
  (30 s); the shared summary poll (`lib/hooks/useActivitySummary.ts`) also owns `markViewed`, which records
  an opened item and revalidates the badges and Home.
- Every transport in this directory is inventoried by `scripts/mcp_parity_audit.mjs` and classified in
  `cmos/contracts/mcp-parity-manifest.json`, so the MCP surface and the UI cannot drift apart silently.

## UI primitives (`frontend/src/components/ui`)

`Dialog` (native `<dialog>` with focus retention), `PageState` (loading, empty and error with retry;
pages render not-found as a distinct state), `PaginationBar`, `StatusBadge`, `TabList`, `Toast` and
`useFeedback` (explicit confirmation and notices). No page uses `alert()` or `confirm()`.

## Sprint 52 surfaces

- **Relationships** (`/graph`, UX-11 over GRAPH-1): a root picker, a depth 1–2 neighborhood diagram and an
  accessible list equivalent over `GET /api/v1/graph/neighborhood` (`lib/api/graph.ts`).
- **Recent activity** (Sprint 53, ACT-1, decision #459): Home shows one newest-first stream over missions,
  reports and evidence groups (`GET /api/v1/activity`, `lib/api/activity.ts`). Status is a label and never
  changes the order. An item is new until the user opens it (mission and report pages call `markViewed`
  on load; activity rows mark on click) or presses "Mark viewed". Evidence is one item per group (project,
  mission, session, origin), and opening the group is what clears it: the Evidence page and a mission's
  Evidence tab call `markEvidenceSeen` (`PUT /api/v1/activity/viewed/evidence`, scoped by project, mission
  and session) so a 300-entry run never needs paging through (Sprint 58, BADGE-1, decision #528).
  `GET /api/v1/activity/summary` feeds the
  sidebar badges on Missions, Evidence and Reports, named "Missions, N new" and hidden at zero. The mission
  dashboards, saved views, priority inbox and "Mark reviewed" from Sprint 52 were removed; `/inbox`
  redirects to Home.
- Home, the evidence browser, project bundles, collection context and saved searches shipped in
  Sprints 50–51; the roadmap records each with its receipt.

## Test lanes

- `npm run test:unit` (vitest, jsdom) over `frontend/src/__tests__` and co-located `*.test.tsx`; the
  required CI context is `vitest`.
- `npm run type-check` and `npm run lint` (`eslint --max-warnings=0`); both are required contexts.
- `build-frontend-production` (required): the production build with the token gate, a check that the
  admin routes are in the pages manifest, then Playwright against `next start` for the specs listed in
  `.github/workflows/frontend-production-build.yml` (app-shell, mission-protocol, project-bundles,
  collection-context, search-command, route-migration, graph).
- After deploy: `.github/workflows/production-smoke.yml` runs `frontend/tests/e2e/production-smoke.spec.ts`
  on a schedule and on dispatch, and every UI mission reruns the read-only direct-browser baseline
  `frontend/scripts/ui-shell-smoke.mjs` (every route, Light and Dark, 1440 and 390 px, axe and overflow
  checks under an America/Chicago clock) only after both Railway services report SUCCESS. Receipts live
  under `cmos/reports/sprint-N/`.

## Configuration

- `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`) and `NEXT_PUBLIC_API_PATH_PREFIX`
  (default `/api/v1`) select the API. Production points at `https://api.tracelab.aquex.ai`.
- Deployment variables and Railway settings are in `docs/frontend_deployment_decisions.md`; local
  commands are in `frontend/README.md`.
