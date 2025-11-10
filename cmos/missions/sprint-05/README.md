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

## Definition of Done
- Hosted UI reachable at the Cloudflare vanity domain, serving `/missions` without console errors.
- Backend enforces JWT authentication + explicit CORS origins; anonymous calls rejected per spec.
- DNS, Railway, and env var settings documented so future agents can redeploy without guesswork.
- Telemetry + validation scripts recorded in `cmos/telemetry/events/` and referenced in mission notes.
