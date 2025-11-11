# TraceLab Research Repository

Personal-scale research repository with RAG-powered semantic search, structured data organization, and quality-enforced workflows.

## Tech Stack

- **Backend**: Python 3.11+ with FastAPI
- **Database**: PostgreSQL 15
- **Migrations**: Alembic
- **Containerization**: Docker & Docker Compose

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development without Docker)

### Development Setup

1. **Clone the repository and navigate to the project:**
   ```bash
   cd TraceLab
   ```

2. **Copy environment file:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your configuration if needed.

3. **Start services with Docker Compose:**
   ```bash
   docker-compose up -d
   ```
   
   This will:
   - Start PostgreSQL on port 5432
   - Build and start the FastAPI application on port 8000

4. **Run database migrations:**
   ```bash
   docker-compose exec app alembic upgrade head
   ```

5. **Access the API:**
   - API docs: http://localhost:8000/docs
   - Health check: http://localhost:8000/api/v1/health
   - DB health check: http://localhost:8000/api/v1/health/db

### Local Development (Without Docker)

1. **Create virtual environment:**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start PostgreSQL** (ensure PostgreSQL is running locally or via Docker):
   ```bash
   docker-compose up -d postgres
   ```

4. **Run migrations:**
   ```bash
   alembic upgrade head
   ```

5. **Start the development server:**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

> Need the full local stack (Docker, scripts, frontend) in one place? See `docs/local-development.md`.

## Authentication & CORS

- The FastAPI backend exposes `/api/v1/auth/login` and `/api/v1/auth/refresh` for JWT issuance. Configure credentials with `AUTH_USERNAME` plus either `AUTH_PASSWORD` (stored securely via passlib) or `AUTH_PASSWORD_HASH`.
- Tokens are signed with `SECRET_KEY` and expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 60). Protected routes reject requests without the `Authorization: Bearer <token>` header.
- Frontend clients (Next.js in `frontend/`) persist the token locally and automatically attach it to mission and quality API calls. Users must sign in before accessing `/missions` routes.
- CORS settings are loaded from `CORS_ALLOWED_ORIGINS_DEV` and `CORS_ALLOWED_ORIGINS_PROD`, along with customizable headers/methods. See `docs/auth_and_cors_guidance.md` for deployment examples.

## Authentication Quickstart

1. **Configure credentials**
   ```bash
   cp .env.example .env
   # update AUTH_USERNAME, AUTH_PASSWORD, SECRET_KEY as needed
   ```
2. **Obtain a token**
   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"tracelab-admin","password":"changeme"}'
   ```
3. **Call a protected endpoint**
   ```bash
   TOKEN="eyJhbGciOiJIUzI1NiIs..."
   curl http://localhost:8000/api/v1/missions/ \
     -H "Authorization: Bearer ${TOKEN}"
   ```
4. **Smoke-test with the helper script**
   ```bash
   python examples/auth_examples.py --base-url http://localhost:8000
   ```
5. **Manual + automated verification**
   - Import `postman/TraceLab-Auth.json` and update the collection variables for quick demos.
   - Run `pytest tests/test_auth_flow.py tests/test_auth_api.py` to cover login, refresh, and downstream access.

See `docs/authentication.md` for a deeper walkthrough covering frontend usage, Postman workflows, and troubleshooting tips.

## Production URLs & Health Checks

- **UI (Cloudflare vanity domain):** `https://namozine.com/missions` points to the Railway Next.js frontend (`frontend-production-43c3.up.railway.app`). Verify availability with `curl -sS -o /dev/null -w "%{http_code}\n" https://namozine.com/missions` (expect `200`).
- **API domain:** `https://api.namozine.com` proxies to the FastAPI service on Railway (`tracelab-production.up.railway.app`); keep `NEXT_PUBLIC_API_BASE_URL` and related variables pointed at this root host (the UI appends `/api/v1` paths automatically). Validate the health route with `curl https://api.namozine.com/api/v1/health` (returns `{ "status": "healthy" }`).
- **CORS origins:** Add both `https://namozine.com` and `https://www.namozine.com` to `CORS_ALLOWED_ORIGINS_PROD` in your `.env` when running the backend in production mode. Keep `Full (Strict)` TLS enabled within Cloudflare to preserve end-to-end encryption.
- **Playwright smoke:** Run the production smoke suite from `frontend/` whenever DNS or env vars change:
  ```bash
  cd frontend
  PLAYWRIGHT_BASE_URL=https://namozine.com \
PLAYWRIGHT_API_BASE_URL=https://api.namozine.com \
PLAYWRIGHT_SKIP_SERVER=1 \
npx playwright test tests/e2e/production-smoke.spec.ts
```
  The suite loads `/missions` through Cloudflare and pings the `/api/v1/health` endpoint to prove the path is wired correctly.

## Project Structure

```
TraceLab/
├── app/
│   ├── api/           # API endpoints
│   │   └── v1/        # API v1 routes
│   ├── core/          # Core configuration and database
│   ├── models/        # SQLAlchemy models
│   ├── services/      # Business logic services
│   └── utils/         # Utility functions
├── alembic/           # Database migrations
├── tests/             # Test files
├── docker-compose.yml  # Docker Compose configuration
├── Dockerfile         # Application Dockerfile
└── requirements.txt   # Python dependencies
```

## Database Schema

The application uses the following core tables:

- `projects` - Research projects
- `documents` - Uploaded research documents
- `document_chunks` - Chunks for RAG embeddings
- `tags` - Tag taxonomy
- `document_tags` - Document-tag relationships
- `insights` - Synthesized findings
- `insight_sources` - Insight-source chunk relationships
- `missions` - Mission Protocol integration (JSONB)
- `quality_checks` - Quality audit trail

See `cmos/docs/technical_architecture.md` for detailed schema documentation.

## Migrations

### Create a new migration:
```bash
alembic revision --autogenerate -m "description"
```

### Apply migrations:
```bash
alembic upgrade head
```

### Rollback:
```bash
alembic downgrade -1
```

## Testing

Run health checks:
```bash
# Basic health
curl http://localhost:8000/api/v1/health

# Database health
curl http://localhost:8000/api/v1/health/db
```

## PII Redaction Guardrail

- Presidio dependencies have been removed. The `PresidioRedactionService` name now refers to a lightweight regex stub that only powers `/api/v1/redaction`.
- `DocumentIngestionService` skips PII redaction entirely and records `"redaction_enabled": false` in its processing audit trail.
- Run `pytest tests/test_presidio_redaction.py::test_redact_document_uses_pseudonymization_and_audit` and `pytest tests/test_rag_service.py::test_semantic_cache_hit_rate_reaches_target` whenever touching ingestion, cache metrics, or related guardrails.
- See `app/services/README_redaction.md` for the full guardrail checklist and migration notes.

## Synthetic Corpus Pipeline (B1.2)

Regenerate the synthetic UX research corpus (Markdown, TXT, DOCX, PDF, CSV) populated with locale-aware Faker PII:

```bash
python scripts/generate_corpus.py
```

Evaluate Presidio against the corpus and capture the baseline metrics artifact:

```bash
python scripts/evaluate_presidio.py
```

Package the corpus for secure upload (creates archive, manifest, and baseline copy):

```bash
python scripts/package_corpus.py
python scripts/upload_corpus.py --destination /secure/presidio/upload
```

Refer to `data/corpus/README.md` for detailed options (document counts, survey rows, research briefs) and storage guidance.

## Project & Document Read APIs

Authenticated callers now receive paginated envelopes when browsing the research library:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/projects?page=1&page_size=10&search=field"

curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/documents?project_id=$PROJECT_ID&processed=true&page=1&page_size=20"
```

Responses share the same shape:

```json
{
  "data": [ { "id": "…", "name": "…" } ],
  "pagination": { "page": 1, "page_size": 10, "total": 27, "pages": 3 }
}
```

- `GET /api/v1/projects` supports `page`, `page_size`, and `search`.
- `GET /api/v1/documents` adds `project_id`, `processed`, and `search` filters.

The CLI (`tracelab projects list`, `tracelab documents list --project-id …`) and the frontend
SWR hooks consume the same payload, ensuring UI selectors and filters stay in sync with the
underlying FastAPI service.

## Development Notes

- The application creates tables automatically in development mode
- Use Alembic migrations for production deployments
- Database connection settings are managed via environment variables
- JWT authentication is enforced for every API route except `/api/v1/health`; obtain a token via `/api/v1/auth/login` and include it as a bearer token in the `Authorization` header.
- Configure credentials with `AUTH_USERNAME` plus either `AUTH_PASSWORD` (auto-hashed at runtime) or `AUTH_PASSWORD_HASH`; override the signing key via `SECRET_KEY`.
- Explicit CORS configuration is required—set `CORS_ALLOWED_ORIGINS_DEV` for localhost (default: `http://localhost:3000`) and `CORS_ALLOWED_ORIGINS_PROD` for deployed UI domains along with `CORS_ALLOWED_METHODS` / `CORS_ALLOWED_HEADERS` if you need to extend the defaults.

## Next Steps

This repo now includes:
- B1.1: Core Service Bootstrap
- B1.2: Synthetic Corpus Pipeline (corpus generator, annotations, evaluation harness)

Upcoming missions:
- B1.3: Presidio Redaction Service
- B1.4: Document Ingestion Pipeline
- B1.5: Embedding & Qdrant Bootstrap
