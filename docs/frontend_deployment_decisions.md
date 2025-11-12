
# Frontend Deployment Decisions

This document records key decisions made regarding the deployment of the frontend application.

## Next.js Runtime

After reviewing the frontend application's code, specifically the use of API routes and SWR polling in `frontend/src/lib/api/missions.ts`, we have decided to use the **Node.js server mode** for the Next.js application.

This decision is based on the following factors:

*   **Dynamic functionality:** The application relies on server-side rendering and API routes to provide dynamic functionality, which is not possible with a static export.
*   **Existing implementation:** The current implementation is already set up to run in a Node.js environment.
*   **Railway support:** Railway has excellent support for running Node.js applications, including Next.js applications in server mode.

We will not be using the static export feature of Next.js.

## Railway Service Configuration

- **Root Directory:** Set the Railway service’s root to `frontend/` so builds only include the Next.js workspace.
- **Builder:** Use the default Nixpacks builder with the explicit command captured in `railway.frontend.json`.
- **Build Command:** `npm install && npm run build` ensures dependencies install with the repo lockfile before production compilation.
- **Start Command:** `npm run start -- --hostname 0.0.0.0 --port $PORT` binds to the port injected by Railway and listens on all interfaces so the health check can reach `/missions`.
- **Health Check:** The service definition monitors `/missions` with a 30-second timeout to fail fast on regressions.

## Environment Variables

The `.env.production.example` file under `frontend/` is the canonical checklist for Railway variables:

| Variable | Purpose | Notes |
| --- | --- | --- |
| `NODE_ENV=production` | Enables production optimisations | Keep synced with build environment |
| `NEXT_TELEMETRY_DISABLED=1` | Disables Next.js telemetry uploads | Required per security guardrails |
| `NEXT_PUBLIC_API_BASE_URL` | Points UI calls at the FastAPI backend (`https://<api-domain>`) | Host only; use `NEXT_PUBLIC_API_PATH_PREFIX` for suffixes |
| `NEXT_PUBLIC_API_PATH_PREFIX=/api/v1` | Declares the path segment inserted before every API call | Set to `""` when the backend lives at the domain root |
| `NEXT_PUBLIC_DEFAULT_PROJECT_ID` | Seeds the Mission Protocol form | Query `GET /projects` (respecting the configured prefix) to capture the UUID |
| `PORT=3000` | Local parity with Railway’s port injection | Set manually for local smoke tests |

## Deploy & Smoke Test Runbook

1. Connect the Railway project to this repository and choose the `frontend/` root directory.
2. Upload `railway.frontend.json` via the Railway UI or `railway service update --json`.
3. Add the environment variables above, mirroring `docs/frontend_architecture.md` defaults for local parity.
4. Trigger a deploy. Confirm build logs show `npm run build` and runtime logs show `Ready on 0.0.0.0:${PORT}`.
5. Smoke test: `curl https://<service>.up.railway.app/missions` (200 OK + HTML response) and optionally run `PLAYWRIGHT_BASE_URL=https://<service>.up.railway.app npm run test:e2e`.
6. Append a telemetry record to `cmos/telemetry/events/sprint-05-frontend-deployment.jsonl` capturing the timestamp, service URL, build command, and smoke-test result.

## Cloudflare Domain Wiring

- **Root & www:** `namozine.com` and `www.namozine.com` are proxied (orange-cloud) CNAMEs that terminate at `frontend-production-43c3.up.railway.app`. Keep SSL/TLS mode on **Full (Strict)** so Cloudflare validates Railway's managed certificate. Run `dig namozine.com CNAME +short` (should surface the Railway target behind Cloudflare flattening) and `curl -I https://namozine.com/missions` (expect `HTTP/2 200`).
- **API subdomain:** `api.namozine.com` proxies to `tracelab-production.up.railway.app` without rewriting the path prefix. Validate health with `curl https://api.namozine.com/api/v1/health` (adjust the `/api/v1` segment to match `NEXT_PUBLIC_API_PATH_PREFIX`) and confirm `access-control-allow-origin: https://namozine.com` is present on the CORS pre-flight response.
- **Allowed origins:** When promoting a new vanity domain, append both `https://<domain>` and `https://www.<domain>` to `CORS_ALLOWED_ORIGINS_PROD` so the FastAPI middleware mirrors Cloudflare's hostnames. Production smoke tests (`PLAYWRIGHT_BASE_URL=https://namozine.com PLAYWRIGHT_API_BASE_URL=https://api.namozine.com PLAYWRIGHT_SKIP_SERVER=1 npx playwright test tests/e2e/production-smoke.spec.ts`) provide an automated proof that DNS, TLS, and the API are in sync.
- **Fallback strategy:** Keep the native Railway URLs (`https://frontend-production-43c3.up.railway.app` and `https://tracelab-production.up.railway.app/api/v1`) documented for emergency cutovers. Disable the Cloudflare proxy temporarily if you need to validate origin certificates directly.

## Rollback Plan

- Use Railway’s **Revert Deployment** button to instantly roll back to the last healthy build.
- If configuration changed (env vars, start command), restore the previous commit of `railway.frontend.json` and redeploy.
- Document any rollback activity in the mission notes and telemetry trail so future agents understand the action history.
