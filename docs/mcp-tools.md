# TraceLab MCP Tools

TraceLab's supported production MCP server is the public npm package
`@aquex/tracelab-mcp`. It runs as a local stdio subprocess and calls the
authenticated TraceLab FastAPI service over HTTPS.

TraceLab does not expose a remote SSE MCP endpoint. In particular,
`https://aquex.ai/mcp` is not a TraceLab MCP server URL.

## Install and configure

Run the current package directly:

```bash
npx -y @aquex/tracelab-mcp
```

`TRACELAB_API_URL` must be the API origin without `/api/v1`; the package adds
that prefix to request paths. Production uses:

```bash
TRACELAB_API_URL=https://api.tracelab.aquex.ai \
  npx -y @aquex/tracelab-mcp
```

For Codex desktop, CLI, and IDE, add this to `~/.codex/config.toml` and restart
Codex:

```toml
[mcp_servers.tracelab]
command = "npx"
args = ["-y", "@aquex/tracelab-mcp"]
startup_timeout_sec = 30

[mcp_servers.tracelab.env]
TRACELAB_API_URL = "https://api.tracelab.aquex.ai"
```

The first launch uses device-code login. A successfully minted credential is
stored at `~/.config/tracelab-mcp/credentials.json` with mode `0600` and is
reused only when its API base matches `TRACELAB_API_URL`. Automation may set
`TRACELAB_API_KEY` or `TRACELAB_TOKEN` instead.

## Tool surface

Version 1.2.0 exposes nine action-clustered tools / 51 actions:

| Tool | Actions |
| --- | --- |
| `tracelab_search` | `knowledge`, `navigate`, `pedr` |
| `tracelab_project` | `list`, `get`, `create`, `update`, `stats`, `neighborhood` |
| `tracelab_collection` | `list`, `get`, `export`, `create`, `add`, `synthesize`, `documents`, `mission_seed`, `update`, `add_document` |
| `tracelab_report` | `create`, `list`, `get`, `export`, `update` |
| `tracelab_document` | `upload`, `get_content`, `list`, `process` |
| `tracelab_mission` | `create`, `list`, `get`, `update`, `views` |
| `tracelab_mission_execution` | `submit`, `status`, `preview`, `logs`, `events`, `cancel`, `promote_report` |
| `tracelab_evidence` | `capture`, `note`, `list`, `search`, `promote`, `get` |
| `tracelab_home` | `snapshot`, `favorites`, `attention`, `inbox_summary`, `inbox_list` |


Sprint 52 additions ship in **1.2.0**, the single publish that decision #425
called for after every Sprint 52 MCP change landed. Installing 1.1.1 from npm
does not provide these actions.

Each call names one cluster and selects an operation with `action`. For
example, a mission list call is:

```json
{
  "name": "tracelab_mission",
  "arguments": {
    "action": "list",
    "project_id": "<project-uuid>",
    "page": 1,
    "page_size": 20
  }
}
```

See the package [README](../packages/tracelab-mcp/README.md) for full setup,
action examples, authentication behavior, and troubleshooting. Its
[Sprint 52 read parameter table](../packages/tracelab-mcp/README.md#sprint-52-read-parameters-120)
documents the eleven MCP-1 reads and the existing action extensions, and its
[Sprint 52 actions and reads table](../packages/tracelab-mcp/README.md#sprint-52-actions-and-reads-mcp-2-120)
covers the MCP-2 actions and reads. Per-user acknowledgements and every DELETE
route stay in the web UI by decision #426.
`knowledge` keeps plain retrieval; optional `pedr` exposes multi-layer and graph
diagnostics. Logs/events are persisted snapshots and explicitly report empty
results; they do not promise live streaming.

## Contract authorities

- Mission authoring and the two serializer surfaces:
  [mission-authoring-contract.md](../cmos/contracts/mission-authoring-contract.md)
- Evidence capture, retrieval, and promotion:
  [evidence-ledger-contract.md](../cmos/contracts/evidence-ledger-contract.md)

The Python server under `app/mcp_server/` is retained for local development
and serializer-parity coverage. It is production-dark and is not the install
path for Codex, Claude, or other external MCP clients.

The [UI parity manifest](../cmos/contracts/mcp-parity-manifest.json) classifies
every frontend API operation. Run `node scripts/mcp_parity_audit.mjs` from the
repository root after installing MCP package dependencies. CI rejects new
unclassified operations, stale consumers and mappings to absent source actions.
