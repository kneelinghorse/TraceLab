# UX-2 preparation — unstarted, unaccepted sketch

Preserved from read-only investigation during session PS-2026-09-12-005. Revalidate sources when UX-2 starts. Any Forge dependency must be supplied by Forge or explicitly delegated by the user; the package-integration notes below do not authorize cross-repository access, builds, changes or messages. UX-2 remains Queued.

UX-2 read-only preparation during UX-1 CI (no UX-2 files edited or mission started)

Known runtime sources:
- app/api/v1/missions.py:get_mission_status validates execution_metadata.progress_percent as bounded non-bool number and current_phase as string. Reuse those semantics, do not derive percentage from elapsed time.
- frontend/src/components/missions/ExecutionTimeline.tsx and frontend/src/types/mission.ts explicitly reject legacy execution_metadata counters for completed runs. Truthful post-completion source/step/runtime metrics live in result_protocol.report_metadata.
- app/core/authorization.py:accessible_filter applies owner/admin, resource owner, effective parent Space membership before counting/paging. No grants means false(), not unfiltered.
- app/api/v1/evidence.py:_evidence_access_filter adds the project's owner path. Home evidence groups need equivalent authorized visibility and must not leak foreign project/mission labels through joins.
- There is no current review state or generic user-preferences column. Mission completion and user review are different concepts. Per-user review persistence needs a small dedicated table/route (or a later explicit scoped decision), not an invented existing flag.
- Mission UX-2 permits an explicit recents-only decision deferring favorites. Label recents as recently updated; no last-viewed tracking exists.
- Root frontend page redirects to /missions. AppShell Brand already links /. Command palette lives inside AppShell; add a small shared event or context only if necessary for Home's search button to use the same modal.
- The current Evidence client list requires project_id and ignores session/mission filters; UX-3 owns full filtering. Home result links must land on working destinations and preserve identifiers for UX-3.

Potential validation cases to implement after start:
>100 missions: scoped totals equal direct DB query + pagination totals; focus ordering validation_failed, blocked, stale queued, completed unreviewed; one refresh reflects transition; review is per-user and renewed runs reappear; no access through another child's denormalized workspace; missing/invalid progress stays unavailable; result links only reference accessible artifacts; both themes phone/desktop with axe and no overflow. No new environment variable needed.

Additional source findings during UX-1 verification:
- Current Alembic head is 043_deepsearch_evidence_batches; inspect again before choosing a migration ID.
- MissionService.update_mission only initializes queued_at/started_at/completed_at when NULL. Manual/requeued runs can retain old timestamps. A per-user review marker should qualify the actual reviewed mission revision (updated_at, optionally job ID), rather than completed_at alone. Writing the review must not itself update Mission.updated_at. Reject acknowledging an unseen changed revision (409) if the UI submits an observed revision.
- Mission list counts are scoped directly with accessible_filter(user, Mission, db); do not silently add a deleted-parent exclusion to Home counts, or they will differ from pagination totals. Resolve project names/links separately under project access and soft-delete rules.
- Evidence list access first loads/authorizes an active parent Project, then applies its entry policy. Home evidence groups need this parent constraint too; child-row ownership alone must not expose a foreign project's title/session data.
- LedgerEntry and LedgerNote have separate created_at/updated_at, project_id, mission_id and session_key. Group activity with the project key so reused session strings across projects cannot combine unrelated research. Label updated-entry counts accurately; they are not a full event history.
- UX-1 fixes shared Forge sidebar CSS. Updating the native Forge worker does not refresh TraceLab's vendored frontend tarballs. Before implementing UX-2 with the new compositions, inspect the qualified Forge release and refresh the needed vendored package artifacts, then run npm install and commit package-lock.json with any package.json changes. Keep package provenance explicit and exercise the actual frontend consumer.
  Confirmed dependency baseline: frontend currently vendors only @oods/tokens and @oods/tw-variants. It does not yet declare @oods/components-react or @oods/component-styles. Add the actual required React/style/contract tarballs from the qualified Forge build when binding the Home composition, rather than assuming they are already installed.

UI binding notes from the actual Forge exports:
- @oods/components-react exports Card, Button, Badge, Text, Stack/Grid, DetailHeader, SearchInput, StatusBadge and StatusTimeline; React peer range >=18 <20 includes TraceLab 19.2.0. Components depend on both @oods/component-contracts 0.1.0 and @oods/component-styles 0.1.0; styles in turn depend on @oods/tokens 0.1.0. Install root file dependencies for the full needed closure, with vendor SHA provenance.
- Import @oods/component-styles/css before TraceLab globals in _app.tsx; it includes the package token CSS. Keep the existing global font binding so Forge structural previews’ serif default does not appear in production.
- Generic Badge/Banner default their status domain to subscription. Pass an explicit Mission status presentation/tone and truthful label; do not accidentally reuse billing vocabulary/colors. Review the exported StatusBadge contract before binding all seven Mission states.
- Report association is Mission.result_report_id, not Report.mission_id. Report.updated_at/created_at and Report.status are available; authorize the referenced report before exposing its title or link.

Implementation sketch to verify at UX-2 start (not yet accepted implementation):
- Preserve the locked favorites requirement with per-user pins for the visible entity types. Every favorites read and mutation must recheck current entity access; pin count must not expose inaccessible rows. No generic unbounded polymorphic read endpoint.
- Completed-review state should be explicit (a Mark reviewed action), private to the current user, and tied to the observed mission.updated_at revision. A new revision makes it eligible again. A stale acknowledgement should return 409; writing the review must not touch Mission.updated_at. Normalize naive DB timestamps as UTC at the API boundary.
- Do not add/modify mission-authoring fields for Home. Use a separate Home response and small review/favorite models, keeping the authoring contract stable.
- Aggregates should select/count columns directly, not load report bodies or rely on eager relationship joins. Resolve authorized parent labels and report links separately.
- No pre-existing stalled-queue threshold was found in current app/services or routes. Choose and document a server constant at implementation time (avoid a new env-var deploy obligation). Account for old queued_at values retained across reruns: label the testable condition accurately, such as waiting without updates, rather than inventing a reliable fresh queued_at.
- User intent favors explicit recents label 'Recently updated', and explicit unavailable progress over guessed elapsed-time percentages.
