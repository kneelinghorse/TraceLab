# Mission Protocol Frontend Architecture

TraceLab Sprint 03 introduces the Mission Protocol UI under `frontend/`, a Next.js 14 (Pages Router) application that visualizes the validation and quality gate pipeline described in `docs/quality_gates.md`.

## Layout

```
frontend/
├─ src/
│  ├─ pages/
│  │  ├─ missions/index.tsx   # Backlog + creation workspace
│  │  └─ missions/[id].tsx    # Mission detail + gate telemetry
│  ├─ components/
│  │  ├─ MissionProtocolForm.tsx
│  │  ├─ ProgressIndicator.tsx
│  │  ├─ QualityGatePanel.tsx
│  │  └─ EvidenceLinking.tsx
│  ├─ lib/
│  │  ├─ api/missions.ts      # REST client for FastAPI endpoints
│  │  └─ hooks/useMissions.ts # SWR data hooks + polling
│  ├─ types/
│  │  ├─ mission.ts           # Pydantic-aligned types
│  │  └─ forms.ts             # React Hook Form schema definition
│  └─ styles/globals.css      # Tailwind tokens + glassmorphism theme
└─ cypress/                   # E2E guardrails for critical flows
```

### Routing

- `/missions` renders the backlog dashboard. The hero references the quality gate spec and lets researchers toggle between **Create** and **Edit** modes for the Mission Protocol form.
- `/missions/[id]` loads a dedicated workspace for a mission, combining the edit form, progress ring, and live gate telemetry (polled every 15s from `/api/v1/quality/missions/:id/quality`).

### Components

| Component | Purpose | Quality Gate Tie-In |
|-----------|---------|---------------------|
| `MissionProtocolForm` | React Hook Form surface for Mission Protocol Draft data. Converts rich text inputs into the arrays required by the Pydantic models. | Ensures required research statement, synthesis, key insight, and evidence fields are populated before hitting the API. |
| `EvidenceLinking` | Nested form section dedicated to insight ↔ chunk traceability. | Maps directly to the `traceability` gate and enforces chunk/insight IDs per evidence entry. |
| `ProgressIndicator` | Circular progress ring driven by `completion_percentage` from the FastAPI backend. | Mirrors the `MissionProgressSnapshot` service to show readiness towards review/complete states. |
| `QualityGatePanel` | Visual status board for every gate with last evaluation time and failure notes. | Consumes `/quality` API responses to surface blocking gates with actionable feedback from `docs/quality_gates.md`. |

### Data Flow

1. `useMissionList` / `useMissionDetail` (SWR) call `frontend/src/lib/api/missions.ts`, which wraps `fetch` calls to the FastAPI service at `NEXT_PUBLIC_API_BASE_URL`.
2. The Mission form converts React Hook Form values ➜ `MissionCreatePayload`, invoking either `POST /api/v1/missions` or `PUT /api/v1/missions/{id}`.
3. After any write, hooks revalidate mission data and the UI re-renders progress + gate panels.
4. The Quality gate panel polls `/api/v1/quality/missions/{id}/quality`, ensuring UI state always matches the backend validators introduced in B3.3.

### Testing

`cypress/e2e/mission-protocol.cy.ts` stubs backend responses to guarantee:

- `/missions` renders backlog cards, quality hints, and React Hook Form validation errors.
- `/missions/[id]` displays live gate statuses and exposes the Mission update workflow.

Run the suite from `frontend/`:

```bash
npm run test:e2e
```

Set `CYPRESS_BASE_URL` if the UI runs on a non-default port.

### Configuration & Env

- `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`) must point at the FastAPI service.
- Optional `NEXT_PUBLIC_DEFAULT_PROJECT_ID` seeds the Mission form’s project selector.
- Tailwind tokens live in `src/styles/globals.css` for palette + glassmorphism helpers.

Refer back to `docs/quality_gates.md` whenever adding UI functionality—the components intentionally mirror those validation heuristics to keep the Mission Protocol experience trustworthy.
