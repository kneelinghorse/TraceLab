# TraceLab Mission Protocol UI

Next.js 14 (Pages Router) workspace that exposes the Mission Protocol CRUD + quality gate experience delivered in Sprint 03. The UI mirrors the validation heuristics documented in `docs/quality_gates.md` and relies on the FastAPI backend under `/api/v1/missions`.

## Prerequisites

- Node.js v18+ (repo uses v24.6.0 via local toolchain)
- FastAPI backend running locally on port `8000` (or provide `NEXT_PUBLIC_API_BASE_URL`)

## Scripts

```bash
npm run dev         # Start Next.js dev server (http://localhost:3000)
npm run build       # Production build
npm run start       # Production server (after build)
npm run lint        # next lint (uses eslint.config.mjs)
npm run type-check  # tsc --noEmit
npm run test:e2e    # Playwright runner with stubbed API fixtures
```

## Environment

Create `.env.local` with:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_DEFAULT_PROJECT_ID=<uuid from projects table>
```

Playwright reads `PLAYWRIGHT_BASE_URL` / `PLAYWRIGHT_PORT` when the UI runs on a non-default port.

## Architecture

- UI routes live under `src/pages/missions`.
- Mission CRUD, progress indicator, and quality gate panel reside in `src/components`.
- API helpers + SWR hooks live under `src/lib`.
- Type definitions mirroring the Pydantic models are in `src/types`.
- E2E guardrails under `tests/e2e/` stub the FastAPI endpoints to validate form behavior and telemetry rendering.

Refer to `docs/frontend_architecture.md` for a deeper dive into component responsibilities and data flow.
