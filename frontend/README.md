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

Use `.env.production.example` as the source of truth for Railway/production deployments (`NODE_ENV`, `NEXT_TELEMETRY_DISABLED`, and the public `NEXT_PUBLIC_*` variables).

Playwright reads `PLAYWRIGHT_BASE_URL` / `PLAYWRIGHT_PORT` when the UI runs on a non-default port.

## Railway Deployment

1. Create a new Railway service that points at this repository and set the **Root Directory** to `frontend/`.
2. Railway loads `frontend/railway.json` as the live service configuration. Keep the root `railway.frontend.json` synchronized only as a fallback/template.
3. Add the environment variables listed in `.env.production.example`. Retrieve `NEXT_PUBLIC_DEFAULT_PROJECT_ID` by calling `GET /api/v1/projects` on the FastAPI backend and selecting the default project UUID.
4. Trigger a deploy and verify logs show a successful build + `Ready` state. Railway will expose a domain such as `https://<service>.up.railway.app`.
5. Smoke test the configured health route with `curl https://<service>.up.railway.app/admin/users` (or run `PLAYWRIGHT_BASE_URL=https://<service>.up.railway.app npm run test:e2e`). A passing route check proves that page is served, but not that Railway is running the latest commit.
6. For redeploys or rollback, redeploy the previous build from Railway’s deployment history or push the prior git commit—document the action in mission telemetry per `docs/frontend_deployment_decisions.md`.

## Architecture

- UI routes live under `src/pages/missions`.
- Mission CRUD, progress indicator, and quality gate panel reside in `src/components`.
- API helpers + SWR hooks live under `src/lib`.
- Type definitions mirroring the Pydantic models are in `src/types`.
- E2E guardrails under `tests/e2e/` stub the FastAPI endpoints to validate form behavior and telemetry rendering.

Refer to `docs/frontend_architecture.md` for a deeper dive into component responsibilities and data flow.
