# Changelog

All notable changes to `@aquex/tracelab-mcp` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.1] — 2026-04-30

Hotfix release. The 1.0.0 build crashed on startup for every fresh
install. Anyone who ran `npx -y @aquex/tracelab-mcp` or
`npm install -g @aquex/tracelab-mcp` against the 1.0.0 tarball got an
immediate `ReferenceError: __dirname is not defined` before any
device-code prompt could appear.

### Fixed

- **ESM/CJS mismatch in `auth/device-code.ts`.** The package ships as
  ESM (`"type": "module"`) but `readPackageVersion()` referenced the
  CommonJS-only `__dirname` global. Replaced with the standard ESM
  derivation (`fileURLToPath(import.meta.url)`). The User-Agent string
  sent to `/api/v1/auth/device/code` once again carries the correct
  package version.

Local smoke test against `https://api.tracelab.aquex.ai` confirmed the full
device-code flow now completes: prompt prints → user approves → key
mints → MCP server starts → authenticated `/missions` call returns.

## [1.0.0] — 2026-04-29

First public release on npm. The package shipped previously inside the
TraceLab repo under the un-published name `@tracelab/mcp-server`; v1.0.0
re-publishes it as the public `@aquex/tracelab-mcp` on the post-T42.4
modernized auth base.

### Added

- **RFC 8628 device-code login.** First launch on a fresh machine prints a
  short user code + URL to stderr; the user approves on the TraceLab
  `/device` page and the MCP picks up a freshly minted API key within
  seconds. Persists at `~/.config/tracelab-mcp/credentials.json`
  (`chmod 600`). Replaces the prior hand-paste-an-API-key install UX.
- **Credential store** with stored-vs-effective `TRACELAB_API_URL`
  comparison; switching between deployments forces a fresh login per
  environment instead of leaking credentials across them.
- **Action-clustered tool surface.** Seven tools — `tracelab_search`,
  `tracelab_project`, `tracelab_collection`, `tracelab_report`,
  `tracelab_document`, `tracelab_mission`, `tracelab_mission_execution`
  — each dispatched by an `action` parameter. Replaces the earlier flat
  ~24-tool layout.

### Auth resolution order

1. `TRACELAB_TOKEN` env var (JWT).
2. `TRACELAB_API_KEY` env var (`tl_*` key).
3. Stored credential, only if its `apiBaseUrl` matches the effective URL.
4. Interactive device-code flow.

### Compatibility

- Node ≥ 18.
- Targets the TraceLab FastAPI service (any deployment that ships
  alembic migrations through 029).
- Tool input/output shapes match `cmos/contracts/mission-authoring-contract.md`
  at the pin recorded in the TraceLab repo.

### Migration

If you used the un-published `@tracelab/mcp-server` from a local checkout,
swap the install line to `npm install -g @aquex/tracelab-mcp` (or `npx
@aquex/tracelab-mcp`). Tool names, schemas, and behavior are unchanged.
Calls against legacy flat tool names continue to return a friendly
migration error pointing at the cluster equivalent.

[1.0.0]: https://github.com/kneelinghorse/TraceLab/releases/tag/tracelab-mcp-v1.0.0
