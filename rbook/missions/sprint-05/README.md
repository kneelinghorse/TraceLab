# Sprint 05: Hosted Frontend & Production Security Readiness

**Sprint Goal:** Deploy the Mission Protocol UI as a managed Railway service, harden API authentication/CORS, and wire production domains/telemetry so external stakeholders can use the platform without local setup.

**Duration:** target 1–1.5 weeks (5–7 focus days)

**Status:** Planned (backlog staged in SQLite)

**Foundational References:**
- `docs/frontend_deployment_decisions.md` – Node.js server mode decision for Next.js (lines 6-16)
- `docs/auth_and_cors_guidance.md` – production CORS + JWT approach (lines 2-82)
- `docs/implementation_guide.md` – Railway configuration + runtime expectations (lines 1018-1088)
- `docs/frontend_architecture.md` – component/data-flow expectations (lines 3-70)

## Missions

1. **B5.1 – Railway Frontend Service Deployment**
   - Scope: Package the Next.js workspace as its own Railway service, configure build/start commands, inject `NEXT_PUBLIC_*` env vars, document deploy runbook, and capture smoke-test telemetry.
   - Dependencies: none; unblocks the auth/CORS work by providing a canonical domain.

2. **B5.2 – FastAPI Auth & CORS Hardening**
   - Scope: Implement JWT login/refresh endpoints, wire dependency-based auth guards, tighten production CORS to the hosted UI domain(s), and update the frontend to store/forward tokens per the new guidance.
   - Dependencies: requires B5.1 domain + env configuration so we can encode allowed origins and test cross-origin requests.

3. **B5.3 – Domain Wiring & Telemetry Validation**
   - Scope: Point Cloudflare DNS at the hosted frontend, expose an API subdomain, update env vars + docs, rerun parity/tests, and add telemetry/health checks proving the production path works end-to-end.
   - Dependencies: requires auth/CORS changes from B5.2.
   - DNS results (2025-11-10):
     | Hostname | Record | Target | Mode | Notes |
     | --- | --- | --- | --- | --- |
     | `tracelab.aquex.ai` | CNAME | `frontend-production-43c3.up.railway.app` | Proxied | `curl https://tracelab.aquex.ai/missions` → `HTTP/2 200`, `x-railway-edge` present |
     | `www.tracelab.aquex.ai` | CNAME | `frontend-production-43c3.up.railway.app` | Proxied | Enable Always-Use-HTTPS redirect so `/missions` resolves identically to apex |
     | `api.tracelab.aquex.ai` | CNAME | `tracelab-production.up.railway.app` | Proxied | `curl https://api.tracelab.aquex.ai/api/v1/health` → `{"status":"healthy"}` |
   - TLS: Cloudflare universal cert (`issuer=Google Trust Services WE1`, `notBefore=2025-11-08`, `notAfter=2026-02-06`) with **Full (Strict)** mode to maintain encrypted hops between Cloudflare and Railway.
   - Env templates updated (`frontend/.env.production.example`, `frontend/.env.production.local`) so `NEXT_PUBLIC_API_BASE_URL` defaults to `https://api.tracelab.aquex.ai/api/v1`; `.env` snippets in `docs/auth_and_cors_guidance.md` show the matching CORS origins (`https://tracelab.aquex.ai`, `https://www.tracelab.aquex.ai`).
   - Telemetry: `cmos/telemetry/events/sprint-05-domain-wiring.jsonl` captures parity + smoke commands plus the Playwright production suite execution ID.

## Definition of Done
- Hosted UI reachable at the Cloudflare vanity domain, serving `/missions` without console errors.
- Backend enforces JWT authentication + explicit CORS origins; anonymous calls rejected per spec.
- DNS, Railway, and env var settings documented so future agents can redeploy without guesswork.
- Telemetry + validation scripts recorded in `cmos/telemetry/events/` and referenced in mission notes.
