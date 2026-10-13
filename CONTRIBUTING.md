# Contributing to TraceLab

Start with the [README quickstart](README.md#run-locally) and [local development guide](docs/local-development.md). The project conventions and definition-of-done gates are in [agents.md](agents.md). Keep changes scoped to the issue, read existing callers before changing a contract, and include a regression test for changed behavior.

## Backend

For development tools and tests outside the API container, use Python 3.11:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,test]'
pytest -m unit -v
```

Integration tests need Docker for real PostgreSQL containers:

```bash
pytest tests/integration -v
```

Run `ruff check app/ tests/`. CI applies Ruff to changed files; **`ruff format` is not enforced**, and broad formatting churn should be avoided. Mypy is a local diagnostic, not a required CI gate. Before concluding runtime work, also run:

```bash
python cmos/scripts/validate_foundational_refs.py
```

The full serialized backend lane and its documented quarantine are defined in [backend-tests.yml](.github/workflows/backend-tests.yml) and the [CI baseline](.github/ci/README.md). Do not introduce skips to make a regression green.

## Frontend

Use Node.js 22.12 or newer:

```bash
cd frontend
npm ci
npm run test:unit -- --run
npm run lint
npm run type-check
npm run build
```

When changing dependencies, run `npm install` in `frontend/` and commit `package-lock.json` with `package.json`; deployment uses a locked install.

The production-build gate runs after `npm ci --omit=dev`, so TypeScript, its declarations and the CSS build tools are explicit `dependencies`. Test runners and lint tools stay in `devDependencies`; the build must not depend on Next.js auto-installing missing tools, which CI disables.

If an older npm crashes with `Cannot read properties of null (reading 'edgesOut')` while resolving Vitest's optional peers, run `npx --yes npm@11 install` to regenerate the lockfile. This is an [npm resolver issue](https://github.com/npm/cli/issues/9787); do not bypass peer checks with `--legacy-peer-deps` or force unrelated upgrades. Fresh `npm install` and `npm ci` with the committed lockfile are verified on Node 22.23.3 / npm 10.9.9.

Browser checks build and start the production frontend automatically:

```bash
cd frontend
npx playwright install chromium
npx playwright test tests/e2e/app-shell.spec.ts
```

The default owns port 3100 and refuses to reuse an existing server. Set
`PLAYWRIGHT_PORT` to use another port. To test a production build you have already
started, explicitly opt out of server management:

```bash
PLAYWRIGHT_SKIP_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 npx playwright test tests/e2e/app-shell.spec.ts
```

**New Playwright specs must be added to the explicit list in the required [production-build workflow](.github/workflows/frontend-production-build.yml)** (or the [production smoke workflow](.github/workflows/production-smoke.yml) for public deployed-route checks). A file under `tests/e2e/` alone does not make it run in CI. Keep synthetic account data in fixtures, and mask credentials and personal data in screenshots and diagnostic receipts.

## MCP and contracts

Follow the [MCP package guide](packages/tracelab-mcp/README.md). Rebuild after editing package source; never commit `packages/*/dist/`. Verify installable artifacts from an `npm pack` tarball installed in a clean directory. MCP surface changes need a regression through the MCP client, and mission-authoring changes must update the [boundary contract](cmos/contracts/mission-authoring-contract.md).

Keep application code, dependencies and generated packages outside `cmos/`. That directory holds the project record and historical receipts; PostgreSQL remains the application's database.
