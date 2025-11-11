#!/usr/bin/env bash

set -euo pipefail

function usage() {
  cat <<'USAGE'
TraceLab Local Development Bootstrap

Usage:
  scripts/dev-setup.sh [--skip-frontend]

Options:
  --skip-frontend   Only start the Docker stack (Postgres, Qdrant, FastAPI).
  -h, --help        Show this message.
USAGE
}

SKIP_FRONTEND=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-frontend)
      SKIP_FRONTEND=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.dev.yml"
ENV_FILE="${REPO_ROOT}/.env"
ENV_EXAMPLE="${REPO_ROOT}/.env.example"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "docker-compose.dev.yml is missing. Cannot start stack." >&2
  exit 1
fi

function ensure_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command '$1' not found in PATH." >&2
    exit 1
  fi
}

ensure_command docker

if docker compose version >/dev/null 2>&1; then
  COMPOSE_BIN=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_BIN=(docker-compose)
else
  echo "Docker Compose v2 (docker compose) or docker-compose is required." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  if [[ -f "${ENV_EXAMPLE}" ]]; then
    echo "Creating .env from .env.example"
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  else
    echo ".env is missing and .env.example could not be found." >&2
    exit 1
  fi
fi

echo "Starting PostgreSQL, Qdrant, and FastAPI services..."
"${COMPOSE_BIN[@]}" -f "${COMPOSE_FILE}" up -d --build

echo "Applying database migrations..."
"${COMPOSE_BIN[@]}" -f "${COMPOSE_FILE}" exec -T backend alembic upgrade head

echo "Stack is running:"
echo "  - API:       http://localhost:8000"
echo "  - Postgres:  localhost:5433 (user: postgres / pass: postgres)"
echo "  - Qdrant:    http://localhost:6333"

if [[ "${SKIP_FRONTEND}" -eq 1 ]]; then
  echo "Frontend start skipped. Run 'npm run dev:frontend' later if needed."
  exit 0
fi

ensure_command npm

pushd "${REPO_ROOT}/frontend" >/dev/null
if [[ ! -d node_modules ]]; then
  echo "Installing frontend dependencies..."
  npm install
fi

export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8000}"
export NEXT_PUBLIC_DEFAULT_PROJECT_ID="${NEXT_PUBLIC_DEFAULT_PROJECT_ID:-}"

function finish_message() {
  popd >/dev/null 2>&1 || true
  echo
  echo "Frontend dev server stopped. The Docker stack is still running."
  echo "Run 'npm run dev:down' from the repository root to stop all services."
}
trap finish_message EXIT

echo "Starting Next.js dev server on http://localhost:3000 ..."
npm run dev
