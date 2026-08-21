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

The server exposes eight action-clustered tools:

| Tool | Actions |
| --- | --- |
| `tracelab_search` | `knowledge` |
| `tracelab_project` | `list`, `create`, `update`, `stats` |
| `tracelab_collection` | `list`, `get`, `export`, `create`, `add`, `synthesize` |
| `tracelab_report` | `create`, `list`, `get`, `export` |
| `tracelab_document` | `upload`, `get_content` |
| `tracelab_mission` | `create`, `list`, `get`, `update` |
| `tracelab_mission_execution` | `submit`, `status`, `preview` |
| `tracelab_evidence` | `capture`, `note`, `list`, `search`, `promote` |

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
action examples, authentication behavior, and troubleshooting.

## Contract authorities

- Mission authoring and the two serializer surfaces:
  [mission-authoring-contract.md](../cmos/contracts/mission-authoring-contract.md)
- Evidence capture, retrieval, and promotion:
  [evidence-ledger-contract.md](../cmos/contracts/evidence-ledger-contract.md)

The Python server under `app/mcp_server/` is retained for local development
and serializer-parity coverage. It is production-dark and is not the install
path for Codex, Claude, or other external MCP clients.
