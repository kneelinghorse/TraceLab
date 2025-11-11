# Local Development Guide

TraceLab ships both a FastAPI backend and a Next.js frontend. This guide standardizes the
local developer workflow so every contributor can bootstrap the stack with a single command.

## Prerequisites

- Docker Desktop 4.x (or Docker Engine + Compose v2)
- Python 3.11 (only required if you plan to run FastAPI outside Docker)
- Node.js 18+ and npm (for the frontend dev server)
- 10 GB of free disk space for Docker volumes / node modules

Verify requirements:

```bash
docker --version
docker compose version  # falls back to docker-compose if needed
node --version          # >= 18.x
npm --version
```

## Environment Files

1. **Backend:** Copy `.env.example` to `.env` and adjust any secrets.
2. **Frontend:** Copy `frontend/.env.production.example` to `frontend/.env.local` and set:
   ```bash
   NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
   NEXT_PUBLIC_DEFAULT_PROJECT_ID=<uuid from GET /api/v1/projects>
   ```
   The `NEXT_PUBLIC_*` values power both client and server-side requests.

## One-Command Startup

The repository now provides a single entry point that orchestrates Docker services, database
migrations, and the Next.js development server.

```bash
npm run dev:all
```

What the script does:

1. Creates `.env` from `.env.example` if it does not exist.
2. Uses `docker-compose.dev.yml` to start PostgreSQL (5433), Qdrant (6333), and the FastAPI backend (8000).
3. Runs `alembic upgrade head` inside the backend container.
4. Installs frontend dependencies (if missing) and launches `npm run dev` from `frontend/`.

Use the optional flag when you only need backend services:

```bash
bash scripts/dev-setup.sh --skip-frontend
```

Auxiliary scripts:

- `npm run dev:stack` – start only the Docker stack.
- `npm run dev:frontend` – run the Next.js dev server (requires `frontend/.env.local`).
- `npm run dev:down` – stop and remove the Docker stack/volumes.

## Service Map

| Service   | Port | Container | Notes |
|-----------|------|-----------|-------|
| Postgres  | 5433 | `tracelab_dev_postgres` | Credentials `postgres/postgres`. Use `psql -h localhost -p 5433`. |
| Qdrant    | 6333 | `tracelab_dev_qdrant`   | Vector DB for RAG runs. |
| FastAPI   | 8000 | `tracelab_dev_backend`  | Hot reload enabled via volume mount. |
| Frontend  | 3000 | Host process            | Started by `npm run dev:all` unless skipped. |

## Verification Checklist

After the stack starts, run:

```bash
# API health
curl http://localhost:8000/api/v1/health

# Database health
curl http://localhost:8000/api/v1/health/db

# Frontend (in browser)
http://localhost:3000/missions
```

## Troubleshooting

- **Ports already in use** – stop existing Postgres/Qdrant instances or change the forwarded
  ports in `docker-compose.dev.yml`.
- **Frontend cannot reach API** – confirm `NEXT_PUBLIC_API_BASE_URL` inside
  `frontend/.env.local` or exported in your shell. The value must be reachable by the browser
  (e.g., `http://localhost:8000`).
- **Qdrant startup lag** – the first launch creates the storage volume; rerun `npm run dev:all`
  if the backend retries due to connection errors.
- **Clean reset** – `npm run dev:down`, then run `docker volume ls | grep tracelab` and remove the listed volumes with `docker volume rm <name>` to drop persisted data after schema resets.

## Related References

- `README.md` – architecture overview and production smoke guidance.
- `docs/auth_and_cors_guidance.md` – environment variable explanations for API + UI parity.
- `cmos/docs/operations-guide.md` – automation, telemetry, and validation policy.
