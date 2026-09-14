# Frontend hygiene (UX-5)

Implements the shared-surface requirements in the [UX roadmap](../foundational-docs/roadmap-sprints-50-53-ux-overhaul.md); that document owns product intent. CMOS owns mission status.

## Shared controls

- `PaginationBar` owns page navigation for documents, projects, reports, missions, collections, evidence and session notes. Server-paginated endpoints retain their total/page metadata. Standalone Collections, its shared Dialog picker and UX-7 project collection tabs now request server pagination; legacy MCP callers can still omit pagination for a complete response. Collection documents and report citations count authorized rows before paging. Changing a filter resets the page in the same event, avoiding a request for an old page with new filters.
- `TabList` supplies wrapping, keyboard-accessible project and document sections. Arrow keys, Home and End select and focus tabs; their panel has the matching labelled relationship.
- `StatusBadge` owns the status-to-semantic-token map for mission, document, report, user and correction states. Labels supplement color, including document processing booleans.
- `Dialog` supplies native modal semantics and the existing keyboard focus loop. Modal elements remain mounted while closed so their autofocus controls do not steal focus before `showModal` records the opener. Cancel/Escape restore focus. Busy destructive actions disable dismissal.
- `useFeedback` presents confirmation through `Dialog` and failures through `Toast`. Cancellation, Escape and component unmount resolve confirmation as false. Callers await an explicit acceptance before mutation; a failed API action stays visible and dismissible.
- `PageState` handles loading, empty and retryable failures. AuthGate uses it across authenticated routes; list pages distinguish request errors from empty results. `HttpError.status` preserves the existing API error message and auth-expiry behavior while allowing document, collection, project and report details to distinguish HTTP 404 from other failures.
- `CommandPalette` extends the shell's native dialog and global opening event. Cmd-K/Ctrl-K opens it, Up/Down focus objects and actions, Home/End select the first/last result while a result is focused, and Enter opens the focused object. Enter in the query runs research search. Tab reaches all controls; Escape restores the opener. In-dialog Keyboard help documents these controls. Object names come from the bounded `/navigation/search` projection with per-type scoped totals and `PaginationBar`; source contents are never loaded for name matching.

All controls use the existing OODS semantic aliases. Page-specific editors remain page-owned sections; this mission does not replace their business workflows.

## Retained behavior and cleanup

Device-code query prefill requests only a preview; approval still requires the user to click. Report row navigation uses the Next router. `/invites` is a permanent redirect to `/settings#invites`. Mission logs and graph health retain the shared HTTP client introduced during UX-3/UX-4.

`/search/results` permanently redirects to `/search`, retaining the query string. Search forwards nonempty project/source/date filters and preserves API result order and membership; the document-name metadata cache never filters results. Saved/recent commands execute through their existing endpoints on `/search?saved=...` and `/search?history=...`. User-scoped state and request versions prevent stale results or synthesis from crossing commands or accounts. Source options use the existing scoped facets endpoint.

Deleted components have no remaining imports: EvidenceCard, QualityGatePanel, ProgressIndicator, MissionProtocolForm, MissionActivityFeed, RelationshipTree and WorkerHealthCard. The restored mission-events API remains available; a future Sprint 51 run view can use it without keeping an unused console feed.

Frontend ESLint is a failing CI job, with no `continue-on-error`. Generated JSONL telemetry, CMOS telemetry and the ingestion SQLite journal are ignored. Existing tracked user reports are unaffected.

## Verification

`src/__tests__/hygiene.test.tsx` tests cancellation versus acceptance, failed mutations, unmount, retryable list failures, loading versus 404, collection paging and preview-only device prefill. Browser tests in `tests/e2e/hygiene.spec.ts` exercise focus containment/restoration, cancellation without API writes, form labels, axe and phone layout in both themes. The existing shell, evidence and redirect browser suites remain part of acceptance.

`tests/e2e/search-command.spec.ts` checks all six entity destinations from native keyboard input, focus containment/restoration, collection paging, exact API result order despite incomplete document metadata, saved/recent execution, the permanent redirect and distinct search states. Both themes run at 390/820/1440 against the production artifact.

Long citation snippets must leave the focus action readable at phone width. Saved and recent search times use the shared UTC API timestamp parser; a browser regression pins time outside UTC so offset-free server timestamps cannot appear hours in the future.

`scripts/ui-shell-smoke.mjs` records the authenticated route baseline against a production build and the deployed site. It permits API reads only: GET plus the explicitly reviewed read-only POST `/api/v1/facets`; other POST requests remain rejected. It keeps credentials out of browser storage and artifacts, and retains strictly identified browser navigation cancellations separately from actual transport failures. Local checks proxy the real API for the local origin. Production checks continue browser requests directly to the deployed API, reject localhost API requests, and preserve real CORS and HTTP failures. Production acceptance and exact test outcomes live in `cmos/reports/sprint-50/ux-5-validation.json` and the corresponding Sprint 51 mission receipts.
