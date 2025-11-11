# Authentication Guide

Comprehensive instructions for configuring TraceLab's JWT authentication, obtaining tokens, and verifying access across the CLI, frontend, and automated tests. Use this guide together with `docs/auth_and_cors_guidance.md`, which covers deployment hardening and CORS policy details.

## Overview

TraceLab secures every API route except `/api/v1/health` with bearer tokens. The FastAPI backend issues JSON Web Tokens (JWT) from the `/api/v1/auth/login` endpoint using credentials stored in environment variables. Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 60) and can be refreshed via `/api/v1/auth/refresh` without re-sending credentials. Frontend and CLI clients must attach `Authorization: Bearer <token>` to call protected endpoints.

## Environment Configuration

| Variable | Purpose | Example |
| --- | --- | --- |
| `AUTH_USERNAME` | Service account username issued to clients | `tracelab-admin` |
| `AUTH_PASSWORD` | Plain-text password hashed at startup (development only) | `changeme` |
| `AUTH_PASSWORD_HASH` | Pre-computed hash for production deployments | `$2b$12$...` |
| `SECRET_KEY` | Signing key for JWTs (must be at least 32 bytes) | `super-secret-change-me` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime in minutes | `60` |
| `JWT_ALGORITHM` | Signing algorithm | `HS256` |
| `CORS_ALLOWED_ORIGINS_DEV` / `CORS_ALLOWED_ORIGINS_PROD` | Origins permitted to call the API | `["http://localhost:3000"]` |

**Local defaults:** Copy `.env.example` to `.env` and edit the values above as needed. Development stacks automatically hash `AUTH_PASSWORD`, so you only need the plain text secret. For production, prefer supplying `AUTH_PASSWORD_HASH` plus a strong `SECRET_KEY`.

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
     -d '{"username":"tracelab-admin","password":"changeme"}'
   ```
   Response:
   ```json
   {
     "access_token": "eyJhbGciOiJIUzI1NiIs...",
     "token_type": "bearer",
     "expires_in": 3600,
     "user": {"username": "tracelab-admin"}
   }
   ```
2. **Call protected APIs**
   ```bash
   TOKEN="eyJhbGciOiJIUzI1NiIs..."
   curl http://localhost:8000/api/v1/missions/ \
     -H "Authorization: Bearer ${TOKEN}"
   ```
3. **Refresh before expiration**
   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/refresh \
     -H "Authorization: Bearer ${TOKEN}"
   ```

All failures return structured 401 responses (`missing token`, `invalid username or password`, or `token subject is not recognized`). When developing against the frontend, ensure the browser origin matches the configured CORS list to avoid pre-flight rejections.

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
