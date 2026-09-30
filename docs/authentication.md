# Authentication Guide

Comprehensive instructions for configuring TraceLab's JWT authentication, obtaining tokens, and verifying access across the CLI, frontend, and automated tests. Use this guide together with `docs/auth_and_cors_guidance.md`, which covers deployment hardening and CORS policy details.

## Overview

TraceLab authenticates users from the `users` table by normalized email and password at
`POST /api/v1/auth/login`. Protected endpoints accept a bearer JWT or a user-owned
`X-API-Key`; health, registration, device initiation/polling and password recovery have
explicit public routes. Human routes deny service principals. Roles and active state
are resolved from the database for each request, never cached in a JWT.

JWTs contain `sub`, `exp` and `credential_version`. A legacy token without the revision
means zero and works only while the user's stored revision is still zero. Recovery
increments that revision; header authentication, refresh, SSE query authentication,
and already-open mission event streams reject the invalidated session. Login, refresh,
API-key creation and device approval serialize against recovery on the user row, so an
old in-flight credential cannot mint a session or key at the new revision.

## Forgotten-password recovery (AUTH-1)

The sign-in screen links to `/forgot-password`; delivered mail links to
`/reset-password#token=…`. Only those two recovery pages bypass the login shell, even
when another account is signed in. Opening a link never changes credentials. The
bootstrap script captures its fragment in memory and immediately strips the URL before
Next routing. Recovery pages set `Referrer-Policy: no-referrer`; no token goes into
persistent browser storage. Reloading a consumed in-memory page requires reopening the
email or requesting a fresh link. Submit the new password twice (8 characters minimum,
72 UTF-8 bytes maximum). Completion signs out the current browser and returns to ordinary
login, without automatic sign-in.

- `POST /api/v1/auth/password-reset/request` accepts only `email`, normalized as login.
  Eligible and ineligible accounts get the same 202 message. Background dispatch starts
  after the response, including the database lookup: 202 is not mailbox delivery proof.
  Missing Resend configuration or an unsafe destination returns the same 503 for all.
- `POST /api/v1/auth/password-reset/confirm` accepts `token`, `new_password` and
  `confirm_password`. Invalid, expired, replayed, disabled and superseded links share a
  400 response. Validation never reflects submitted values. There is no GET redemption.
- The token is 32 random bytes (43 URL-safe characters); only its SHA-256 digest is stored.
  Migration `056_password_recovery` adds one replaceable recovery row per user and the
  credential revision. Expiry is 30 minutes. A new issuance supersedes the previous link;
  a failed or uncertain send invalidates the new link as well. A pending link cannot
  redeem until provider acceptance has been persisted. The user can request again
  after the cooldown. A process crash can lose an in-flight email; no plaintext durable
  queue is introduced. The bounded row is replaced on retry and deleted on reset, a
  Settings password change, or account deletion. Expired rows cannot redeem.
- A successful reset atomically consumes the link, changes the hash and revision, deletes
  the recovering human's approved device grants before their API keys, and clears local
  pending-key delivery. Other users, the DeepSearch service principal and unowned pending
  device codes remain unchanged. New device approval requires a valid post-reset session.
  The existing Settings flow still requires the current password and invalidates recovery
  links without signing out sessions or revoking keys.

Recovery uses the existing `RESEND_API_KEY`, `RESEND_FROM_ADDRESS` and an HTTPS
`FRONTEND_URL` (no caller-supplied destination), independently of mission email switches
and per-user notification preferences. No new environment variable is introduced.
Provider errors are logged by outcome/status only: never provider bodies, reset links,
passwords or token-bearing exceptions. Internal delivery status means provider acceptance,
not confirmed inbox receipt. Debug SQL logging should remain disabled on deployments.

Limits: independent request IP budget 5/minute, confirmation IP budget 10/minute, and
HMAC-normalized recipient budget 3/15 minutes. IPs use the existing trusted-proxy policy.
Each in-process limiter stores at most 4,096 keys and refuses new keys at capacity after
pruning expired entries. IP/recipient budgets reset on restart and multiply with replicas;
a database-backed 60-second per-user send cooldown additionally serializes sends across
replicas. Recipient throttling uses the generic 202, so it reveals no account existence.
Requests never lock normal password login. This is the current single-instance deployment
contract; multi-replica abuse limits would require a shared limiter.

Before release acceptance, use an agreed dedicated mailbox/account to prove actual email
receipt, reset, new login and revoked credentials on the exact deployed build. A provider
acknowledgement or local mock is insufficient. Keep acceptance receipts free of links and
credentials, and disable/revoke the temporary fixture afterward.

### Admin-assisted recovery

Admins and owners can choose **Send password reset link** in User management,
confirm the named account and its stored mailbox, and await provider acceptance.
`POST /api/v1/admin/users/{user_id}/password-reset` takes an empty JSON object;
recipient, redirect and password overrides are rejected. Members, viewers,
service principals and anonymous callers are denied. Disabled, service and
non-deliverable targets receive explicit refusals and are never reactivated.

This uses the same recovery service, recipient budget, database cooldown and
newest-link policy as public recovery. A provider failure invalidates that
issuance; retry explicitly after the cooldown. Sending changes no credentials.
The recipient still chooses the password through the public link. Provider
acceptance is not proof that the mailbox received the email.

`password_recovery_audits` records historical actor/target UUIDs, request and
completion times and a fixed outcome (`pending`, `accepted`, `failed`,
`ineligible`, `not_found`, `rate_limited`). It contains no address, token, link,
password/hash or provider response. Identity snapshots intentionally have no
user foreign keys, so purging an account retains the audit. An interrupted send
can leave a `pending` audit and unusable pending token; never relabel it as
accepted without a provider acknowledgement. Global configuration/IP denials
happen before preparing a target request and do not create an audit row.

## Environment Configuration

| Variable | Purpose | Example |
| --- | --- | --- |
| `AUTH_USERNAME` | Explicit full email for bootstrap owner provisioning; not a runtime login override | `owner@example.com` |
| `AUTH_PASSWORD` / `AUTH_PASSWORD_HASH` | Initial bootstrap credential; changing it does not reset an existing user | Set privately |
| `SECRET_KEY` | Signing key for JWTs (must be at least 32 bytes) | `super-secret-change-me` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime in minutes | `60` |
| `JWT_ALGORITHM` | Signing algorithm | `HS256` |
| `CORS_ALLOWED_ORIGINS_DEV` / `CORS_ALLOWED_ORIGINS_PROD` | Origins permitted to call the API | `["http://localhost:3000"]` |

**Local setup:** Copy `.env.example` to `.env` and configure bootstrap identity and the signing secret. Runtime login checks the database password hash. Use Settings with the current password, or recovery below, to change an existing account. Never rotate the shared signing secret to reset one person.

### Ingestion CLI Credentials

The ingestion CLI reads credentials in the following order: CLI flags ➜ `INGEST_CLI_*` variables ➜
`AUTH_*` variables ➜ FastAPI settings defaults. Exporting dedicated ingestion variables lets you keep
CLI automation isolated from the service account used elsewhere.

| Variable | Purpose | Example |
| --- | --- | --- |
| `INGEST_CLI_USERNAME` | Overrides the username for `scripts/ingest_cli.py` | `tracelab-admin` |
| `INGEST_CLI_PASSWORD` | Overrides the password for the ingestion CLI | `changeme` |
| `INGEST_CLI_TOKEN` | Supply a pre-issued JWT to skip the login request | `eyJhbGciOiJIUzI1N...` |

## Token Lifecycle

1. **Login for an access token**
   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"owner@example.com","password":"<your-password>"}'
   ```
   Response:
   ```json
   {
     "access_token": "<access-token>",
     "token_type": "bearer",
     "expires_in": 3600,
     "user": {"user_id": "<uuid>", "email": "owner@example.com", "display_name": "Owner", "username": "Owner"}
   }
   ```
2. **Call protected APIs**
   ```bash
   TOKEN="<access-token>"
   curl http://localhost:8000/api/v1/missions/ \
     -H "Authorization: Bearer ${TOKEN}"
   ```
3. **Refresh before expiration**
   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/refresh \
     -H "Authorization: Bearer ${TOKEN}"
   ```

Invalid or missing credentials return 401; disabled accounts return 403 and exhausted authentication budgets return 429 with Retry-After. Recovery response codes are described above. When developing against the frontend, ensure the browser origin matches the configured CORS list to avoid pre-flight rejections.

## CLI & Script Examples

`examples/auth_examples.py` demonstrates the full flow using `requests`:

```python
from examples.auth_examples import login, refresh_token, fetch_missions

token = login("http://localhost:8000", "tracelab-admin", "changeme")
new_token = refresh_token("http://localhost:8000", token)
missions = fetch_missions("http://localhost:8000", new_token)
```

Run it with:

```bash
python examples/auth_examples.py --base-url http://localhost:8000 \
  --username tracelab-admin --password changeme
```

The script prints each step and exits with non-zero status on failures, making it suitable for smoke-testing new deployments.

### Ingestion CLI Authentication

`scripts/ingest_cli.py` now authenticates automatically before uploading files. Provide credentials
via env vars or pass them explicitly:

```bash
export AUTH_USERNAME=tracelab-admin
export AUTH_PASSWORD=changeme
# or export INGEST_CLI_USERNAME / INGEST_CLI_PASSWORD for CLI-only overrides

python scripts/ingest_cli.py ./examples/markdown/sample.md $PROJECT_ID \
  --base-url http://localhost:8000 \
  --username "$AUTH_USERNAME" --password "$AUTH_PASSWORD"

# Supply an already-issued token instead of logging in
python scripts/ingest_cli.py ./docs/sample.md $PROJECT_ID \
  --offline --token "$ACCESS_TOKEN"
```

The CLI obtains a token from `/api/v1/auth/login`, attaches the `Authorization: Bearer <token>`
header to every ingestion request, and fails fast if the document never reaches `processed` and
`chunked` status.

## Frontend Usage

The Next.js workspace (`frontend/`) stores tokens in local storage via the shared API client. Configure:

- `NEXT_PUBLIC_API_BASE_URL` – Root API host (omit `/api/v1`).
- `NEXT_PUBLIC_DEFAULT_PROJECT_ID` – Project identifier requested after login.

When running locally, `npm run dev` automatically prompts for the credentials described above. In production, rotate credentials via environment variables and redeploy both services. See `docs/frontend_deployment_decisions.md` for UI-specific details.

## Manual Testing Collections

Import `postman/TraceLab-Auth.json` into Postman or Insomnia:

1. Set the `baseUrl`, `username`, and `password` variables in the collection.
2. Send **Auth/Login** to capture a token (stored as `accessToken` in the collection variables).
3. Use **Auth/Refresh** or **Missions/List** (protected route) to confirm access.

This collection mirrors the curl commands above and is useful for demos or support investigations.

## Automated Verification

Run the dedicated auth suite plus existing coverage:

```bash
pytest tests/test_auth_flow.py tests/test_auth_api.py
```

`tests/test_auth_flow.py` exercises login, refresh, error paths, and ensures protected routes accept valid tokens only. Pair it with `tests/test_auth_api.py` for broader regression coverage (CORS, anonymous rejection, etc.). Both tests rely on the defaults exported by `.env` or the overrides in `tests/conftest.py`.

## Troubleshooting

- **401 Missing Authorization header** – Ensure the `Authorization` header exactly matches `Bearer <token>` and that the token is not surrounded by quotes.
- **401 Token subject is not recognized** – Indicates stale credentials; redeploy with matching `AUTH_USERNAME` across the backend and clients.
- **422 Unprocessable Entity** – The request body is malformed. Verify the JSON structure matches the schemas in `app/schemas/auth.py`.
- **CORS errors in browser** – Update `CORS_ALLOWED_ORIGINS_DEV/PROD` and restart the FastAPI service so middleware reflects the new origins.
- **Token immediately expires** – Set `ACCESS_TOKEN_EXPIRE_MINUTES` to a positive integer and confirm the container clock is synchronized (UTC recommended).

Refer to `docs/auth_and_cors_guidance.md` for production hardening and additional deployment examples once the basics here are verified.

## Service Accounts & DeepSearch Integration

### Service-Role Tier & trusted-origin writes (T47.4)

> The "Architecture / Production Credentials / Future Multi-User Support" notes
> below this subsection are **historical** (they describe the original single-user
> env-var model). TraceLab now has a DB-backed users table with roles
> (viewer/member/admin/owner) plus a **service** role. This subsection is the
> current authority for how machine callers authenticate. (Full doc refresh is
> tracked in T47.6.)

Some writes are **service-to-service**, not per-user. They are gated to a
**service principal** — a user whose role is `service` — via
`authorize_service_or_403` (`app/core/authorization.py`), which is **stricter**
than the per-user `authorize()`: only `role == "service"` passes; *every* human
role (including owner/admin) is denied. A service principal is rejected by the
shared human-route authentication dependency everywhere else, regardless of
`RBAC_ENABLED`, resource ownership, or Space membership. It can therefore do
nothing but the explicit service writes below plus `GET /api/v1/auth/me`, which
is intentionally available for startup role verification. Legacy log ingest
retains the feature-flag no-op for flip-back compatibility. The evidence
projection passes `enforce_when_disabled=True`, so its service-role boundary is
unconditional even when `RBAC_ENABLED` is off.

**Service / trusted-origin surfaces (the carve-out — kept explicit so it cannot
silently widen; guarded by `tests/test_rbac_flip_regression.py::TestServiceCarveOutBoundary`):**

| Surface | Auth mechanism | Notes |
| --- | --- | --- |
| `GET /api/v1/auth/me` (startup role verification) | Any authenticated principal | Read-only exception: returns the caller's live database role so a worker can fail closed unless it resolves to `service`. |
| `POST /missions/{id}/logs` (runner log ingest) | **service principal** (`role=service`) when `RBAC_ENABLED` on; authn-only when off | Accepts only canonical/transitional runner log batches. |
| `POST /missions/events/cmos` (CMOS event bridge) | **service principal** when `RBAC_ENABLED` on; authn-only when off | Emits operational CMOS transition events. |
| `POST /missions/{id}/evidence` (DeepSearch ledger projection) | **service principal** (`role=service`) in every feature-flag state | Triggers idempotent projection of the exact persisted terminal mission/job result; every human role is denied and the request cannot supply evidence, project, session, or origin fields. |
| `POST /api/v1/webhooks/deepsearch` | HMAC-SHA256 shared secret (env `DEEPSEARCH_TRACELAB_SERVICE_SECRET`, legacy fallback `DEEPSEARCH_WEBHOOK_SECRET`) | Never user-authed; structural carve-out (never calls `authorize()`). ⚠️ If neither is set, HMAC validation is **skipped** (dev-only mode) — must be set in prod. |
| `app/mcp_server/**` (in-repo Python MCP) | in-process DB access | Production-dark; structural carve-out. |
| `packages/tracelab-mcp` (published npm MCP client) | human JWT or `tl_` API key over HTTP | The real production MCP surface; must always present a credential. |

**⚠️ Rollout dependency:** the DeepSearch runner must use a dedicated
`role=service` principal before invoking `POST /missions/{id}/evidence`, and
before `RBAC_ENABLED` is flipped on for `POST /missions/{id}/logs`. Provision
the service account and give the runner a revocable API key first:

```bash
# As owner/admin, mint the runner's service principal:
POST /api/v1/admin/users  { "email": "...", "password": "...", "display_name": "deepsearch-runner", "role": "service" }
# Then set DeepSearch's TRACELAB_API_KEY to a key minted for that account.
```

The `s92-m05` runner integration must verify `/api/v1/auth/me` at startup and
fail closed unless that key resolves to the service role. TraceLab must deploy
the evidence endpoint before that integration is enabled. This sequencing is
owned by the T47.6 post-flip rollout runbook and the LEDGER-2 cross-service
handoff.

### Architecture

TraceLab uses **single-user auth via environment variables** - not a database of users. The `AUTH_USERNAME` and `AUTH_PASSWORD` env vars define the ONE account that can authenticate.

This is intentional for an internal single-builder tool. Both human operators and DeepSearch agents share the same credentials.

### Production Credentials

```bash
# Railway environment variables (example — never commit production values)
AUTH_USERNAME=<admin-email>
AUTH_PASSWORD=<set-in-Railway-secret-store>
```

### Usage (from DeepSearch)

```python
import requests

# Login with shared credentials
resp = requests.post(
    "https://api.tracelab.aquex.ai/api/v1/auth/login",
    json={"email": "<admin-email>", "password": "<strong-unique-password>"}
)
token = resp.json()["access_token"]

# Use token for API calls
headers = {"Authorization": f"Bearer {token}"}
preflight = requests.post(
    "https://api.tracelab.aquex.ai/api/v1/pedr/preflight",
    headers=headers,
    json={"query": "passwordless authentication", "top_k": 5}
)
```

**Token Expiry:** Configured via `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60 min, production uses 1440 = 24 hours)

### Future Multi-User Support

If separate service accounts are needed later:
1. Modify `app/core/security.py` to support credential list or DB lookup
2. Add user management endpoints
3. Update Railway with multiple accounts

For now, shared credentials are appropriate.

**Cross-Reference:**
- DeepSearch integration: `DeepSearch.alpha/cmos/planning/Answers-from-tracelab-sprint12.md`
- Sprint 12 mission: `cmos/missions/sprint-12/B12.3_Create-Service-Account-Production.yaml`


### Restored operational routes (RECOVER-1)

Following the authorization design in `foundational-docs/tech_arch_template.md`,
`POST /missions/events/cmos` is a trusted machine write: under RBAC it requires a
service principal, just like mission logs. A human owner/admin token cannot
publish CMOS transitions while RBAC is enabled. Its legacy flag-off behavior
matches the log-write gate. Configure the CMOS bridge with a service credential.
The bridge uses a separate router mount and `require_authenticated_principal`,
matching mission log/evidence ingestion. The human-route dependency remains on
event reads and rejects service credentials in both RBAC states. Regression tests
exercise the actual JWT and API-key authentication paths for this boundary.

`GET /missions/events/recent` and `/missions/events/stream` scope mission events
by current mission ownership/Space membership. They resolve the human mission ID
emitted by MissionService and row UUIDs; UUID-shaped aliases cannot grant access
to another mission. Unscoped CMOS/PEDR events are only visible to owner/admin
principals under RBAC. The stream rechecks grants for each event, applies the
limit after filtering replay history, and supports EventSource query-token auth.

All `/decisions/linked` reads and evidence writes require owner/admin access
unconditionally. CMOS decisions are global operational records with no TraceLab
owner/Space field; ordinary users and service principals cannot read or alter
them. Router-level authentication protects every restored route independently
of the RBAC feature flag.
