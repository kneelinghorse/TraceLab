# TraceLab

TraceLab is a research workspace for collecting evidence, running DeepSearch missions, and producing cited reports.

Keep documents, claims, sources and research results together, then use the Librarian to work with that material through a web interface or an MCP client.

## What it does

- **Librarian:** ask questions of your research with citations, draft project descriptions, review duplicate documents, and propose collections and reports for human review.
- **DeepSearch missions:** author research scope, preview the compiled contract, follow execution, and inspect the resulting evidence and reports. A separate DeepSearch worker executes the research.
- **Evidence Ledger:** retain sourced claims, supporting snippets, dispositions and research-session context, including contradictory and rejected findings.
- **Cited reports:** synthesize collections while keeping links back to source excerpts.
- **MCP:** use the same research workflows from compatible AI clients through [`@aquex/tracelab-mcp`](packages/tracelab-mcp/README.md).

## Hosted access

The [hosted app](https://tracelab.aquex.ai) is invite-only. Use the invite code supplied by the person inviting you when you register. Existing users sign in with their email address and password. API keys and additional invite codes are available in Settings.

## Run locally

The quickstart runs PostgreSQL, Qdrant and the FastAPI API in Docker, with the Next.js UI on the host. It requires Docker with Compose v2, Node.js **22.12 or newer**, npm, and free ports **3000, 8000 and 6333**. PostgreSQL uses host port **5433**, with an alternate-port option below. Python 3.11 is supplied by the API container.

**Research execution requires a DeepSearch worker.** That worker is a separate project and is not publicly available while its repository is private; cloning TraceLab alone does not provide an end-to-end autonomous research runner. Provider-backed Librarian answers, embeddings and report generation also need provider credentials. The startup and health checks below require no paid provider calls.

1. Clone and create the local environment file:

   ```bash
   git clone https://github.com/kneelinghorse/TraceLab.git
   cd TraceLab
   cp .env.example .env
   ```

2. Choose a Compose project name for this checkout. It gives its containers and data volumes a separate namespace; use an unused name for a fresh database. Reusing a name intentionally retains that stack's data.

   ```bash
   export COMPOSE_PROJECT_NAME=tracelab-local
   ```

3. If another application already uses PostgreSQL port 5433, choose a free host port before starting:

   ```bash
   export TRACELAB_POSTGRES_PORT=55433
   ```

   This changes only the local Docker port mapping. The API still connects to PostgreSQL on port 5432 inside Docker. Host-side database tools must use the selected host port.

4. Start the stack and UI:

   ```bash
   bash scripts/dev-setup.sh
   ```

   The script builds and starts the Docker services, applies Alembic migrations, installs frontend dependencies and starts Next.js. Leave this terminal running. Open [localhost:3000](http://localhost:3000).

   The example environment provisions `tracelab-admin@example.com` with password `changeme` on the first migration. These are local development defaults. Before deploying a real instance, set `AUTH_USERNAME` to the owner's full email address and configure `AUTH_PASSWORD` or `AUTH_PASSWORD_HASH`, `SECRET_KEY`, and the appropriate CORS origins in `.env`. Changing bootstrap credentials later does not reset an existing database user's password; use Settings or password recovery.

5. In another terminal, check both services:

   ```bash
   curl --fail --silent --show-error --write-out '\nAPI HTTP %{http_code}\n' http://localhost:8000/api/v1/health
   curl --fail --silent --show-error --output /dev/null --write-out 'UI HTTP %{http_code}\n' http://localhost:3000
   ```

   Both should report HTTP 200. API documentation is at [localhost:8000/docs](http://localhost:8000/docs).

Stop the UI with Ctrl-C. In that same terminal (where `COMPOSE_PROJECT_NAME` is still set), stop the Docker services while retaining their data:

```bash
docker compose -f docker-compose.dev.yml down
```

See the [local development guide](docs/local-development.md) for separate service startup and the [authentication guide](docs/authentication.md) for account and deployment configuration. Python dependencies come from `pyproject.toml`; contributor installation uses `pip install -e '.[dev,test]'`.

## Repository map

| Path | Contents |
| --- | --- |
| [`app/`](app/) | FastAPI routes, services, models, ports and adapters |
| [`frontend/`](frontend/) | Next.js web UI |
| [`alembic/`](alembic/) | PostgreSQL schema migrations |
| [`packages/tracelab-mcp/`](packages/tracelab-mcp/) | Supported MCP package |
| [`tests/`](tests/) and [`frontend/tests/`](frontend/tests/) | Backend and browser tests |
| [`docs/`](docs/) | Developer and operations documentation |
| [`cmos/`](cmos/) | Reasonbook project record, planning documents and acceptance receipts |

The tracked checkout alone is about 1 GB, mostly development history and screenshot receipts under `cmos/`; a full clone also includes Git history. The record is a development workbench, separate from the research data stored by the application in PostgreSQL and Qdrant. Its local SQLite database is ignored by Git. Application code lives outside `cmos/`.

Useful references: [frontend architecture](docs/frontend_architecture.md), [architecture decisions](docs/adr/), [MCP tool reference](docs/mcp-tools.md), and [mission-authoring contract](cmos/contracts/mission-authoring-contract.md).

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) for setup, tests and CI expectations. Report vulnerabilities privately using the process in [SECURITY.md](SECURITY.md).

## License

TraceLab's code, including the MCP package and vendored DeepSearch contract compiler, is available under the [MIT license](LICENSE). The bundled `@oods/tokens` and `@oods/tw-variants` packages retain **PolyForm Noncommercial 1.0.0**. Their separate license terms are identified in [NOTICE](NOTICE) and included in the vendored archives.
