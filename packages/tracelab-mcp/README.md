# @aquex/tracelab-mcp

MCP server for [TraceLab](https://github.com/kneelinghorse/TraceLab). Lets AI
agents run complete research-to-output loops — semantic search, project and
collection management, mission authoring, DeepSearch execution, and report
generation, plus cross-session evidence capture — against a TraceLab knowledge
base.

- **8 action-clustered tools** (one tool per noun, dispatched by `action`)
- **RFC 8628 device-code login** — install, run, click a link, you're in
- Works out of the box with **Claude Desktop**, **Claude Code**, and any
  Model Context Protocol client over stdio

Requirements: Node ≥ 18 and a reachable TraceLab API endpoint.

---

## Install

The fastest path is `npx` — no global install, always picks up the latest
published version:

```bash
npx @aquex/tracelab-mcp
```

Global install if you'd rather pin once:

```bash
npm install -g @aquex/tracelab-mcp
tracelab-mcp
```

From source (development):

```bash
git clone https://github.com/kneelinghorse/TraceLab.git
cd TraceLab/packages/tracelab-mcp
npm install
npm run build
node dist/index.js
```

---

## First-time login

The first time you launch `tracelab-mcp` against an account that has never
issued an MCP credential, the server runs an RFC 8628 device-authorization
flow. You'll see this on stderr:

```
────────────────────────────────────────────────────────────
[tracelab-mcp] Login required
────────────────────────────────────────────────────────────
Open:  https://tracelab.aquex.ai/device?code=WDJB-MJHT
Code:  WDJB-MJHT
(Code expires in 600s; this client will poll every 5s.)
────────────────────────────────────────────────────────────
```

1. Open the URL in any browser where you're logged in to TraceLab.
2. Confirm the User-Agent shown matches the install you started, then click
   **Approve**.
3. The MCP client picks up the freshly minted API key within ~5 seconds and
   continues startup.

The minted key is stored at `~/.config/tracelab-mcp/credentials.json`
(`chmod 600`). Subsequent launches reuse it; you never see the login prompt
again on that machine.

To revoke a key, delete the credential file *and* delete the key from your
TraceLab account at `/profile` → API Keys. To force a re-login, delete the
credential file and relaunch.

---

## Configure your MCP client

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tracelab": {
      "command": "npx",
      "args": ["-y", "@aquex/tracelab-mcp"],
      "env": {
        "TRACELAB_API_URL": "https://tracelab.aquex.ai"
      }
    }
  }
}
```

Restart Claude Desktop. The first invocation triggers the device-code flow
on stderr (visible in Claude Desktop's MCP server logs).

### Claude Code

```bash
claude mcp add tracelab -- npx -y @aquex/tracelab-mcp
```

Then set the API URL:

```bash
claude mcp env tracelab TRACELAB_API_URL https://tracelab.aquex.ai
```

### Other MCP clients

The server speaks stdio. Any MCP-compatible client that can launch a
subprocess will work — point it at `tracelab-mcp` (or `npx
@aquex/tracelab-mcp`) and pass `TRACELAB_API_URL` in the environment.

---

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRACELAB_API_URL` | `http://localhost:8000` | TraceLab API base URL (the FastAPI service, not the frontend). |
| `TRACELAB_TOKEN` | *(unset)* | Optional JWT bearer. Wins over device-code credential when set. Useful for short-lived CI runs. |
| `TRACELAB_API_KEY` | *(unset)* | Optional `tl_*` API key. Wins over device-code credential when set. Useful when you've already minted a key via the web UI and want to skip the flow. |

Auth resolution order at startup:

1. `TRACELAB_TOKEN` env var (JWT).
2. `TRACELAB_API_KEY` env var (`tl_*` key).
3. Stored credential at `~/.config/tracelab-mcp/credentials.json`, **only
   if** its `apiBaseUrl` matches `TRACELAB_API_URL`.
4. Interactive device-code flow (mints a fresh key, persists it).

Step 3's URL match means switching `TRACELAB_API_URL` between (e.g.) prod
and a local dev server forces a fresh login per environment — credentials
never leak across deployments.

---

## Tools

Eight action-clustered tools. Each cluster exposes multiple actions
selected via the `action` parameter.

| Cluster | Actions | Purpose |
| --- | --- | --- |
| `tracelab_search` | `knowledge` | Semantic search across the knowledge base. |
| `tracelab_project` | `list`, `create`, `update`, `stats` | Project CRUD + aggregate stats. |
| `tracelab_collection` | `list`, `get`, `export`, `create`, `add`, `synthesize` | Curate chunks into collections, then synthesize. |
| `tracelab_report` | `create`, `list`, `get`, `export` | Persistent named research reports. |
| `tracelab_document` | `upload`, `get_content` | Document ingestion + full-text fetch. |
| `tracelab_mission` | `create`, `list`, `get`, `update` | Mission CRUD against the DeepSearch authoring contract. |
| `tracelab_mission_execution` | `submit`, `status`, `preview` | DeepSearch lifecycle: queue, poll status, preview the compiled contract. |
| `tracelab_evidence` | `capture`, `note`, `list`, `search`, `promote` | Capture sourced findings and working notes, reuse them across sessions, and promote a session to a report or document. |

### Example calls

Semantic search:

```json
{
  "name": "tracelab_search",
  "arguments": {
    "action": "knowledge",
    "query": "user onboarding best practices",
    "limit": 10
  }
}
```

Create a mission and submit it to DeepSearch:

```json
{
  "name": "tracelab_mission",
  "arguments": {
    "action": "create",
    "mission_id": "RESEARCH-001",
    "title": "Hosted code-execution platforms",
    "objective": "Compare serverless container platforms for evaluation",
    "success_criteria": ["≥5 platforms covered", "Latency benchmarks cited"],
    "project_id": "fbd3bd03-5ddc-49ee-8013-529163a99290",
    "required_entities": ["AWS Lambda", "Google Cloud Run", "Vercel", "Fly.io"],
    "deliverable_format": "comparison table"
  }
}
```

```json
{
  "name": "tracelab_mission_execution",
  "arguments": {
    "action": "submit",
    "mission_id": "RESEARCH-001"
  }
}
```

Synthesize a collection into a report:

```json
{
  "name": "tracelab_collection",
  "arguments": {
    "action": "synthesize",
    "collection_id": "11111111-1111-1111-1111-111111111111",
    "synthesis_prompt": "Compare the platforms on cold-start latency and cost."
  }
}
```

Capture sourced findings for reuse in later sessions:

```json
{
  "name": "tracelab_evidence",
  "arguments": {
    "action": "capture",
    "project_id": "fbd3bd03-5ddc-49ee-8013-529163a99290",
    "session_key": "competitive-scan-2026-08-20",
    "entries": [
      {
        "claim": "The vendor publishes a documented data-retention limit.",
        "source_url": "https://example.com/security/retention",
        "snippet": "Customer content is retained for no more than 30 days.",
        "query": "vendor data retention policy",
        "disposition": "supporting",
        "tags": ["security", "retention"]
      }
    ]
  }
}
```

Search the project ledger before repeating research:

```json
{
  "name": "tracelab_evidence",
  "arguments": {
    "action": "search",
    "project_id": "fbd3bd03-5ddc-49ee-8013-529163a99290",
    "q": "data retention"
  }
}
```

### Search before research

Use the two search surfaces in this order:

1. Call `tracelab_evidence(action="search")` with the project ID to reuse raw
   findings from earlier sessions. These results retain the source URL,
   disposition, canonical `source_id`, and `source_sighting_count`.
2. Call `tracelab_search(action="knowledge")` when you need semantic matches
   from the ingested document corpus.
3. Capture material new findings with `tracelab_evidence(action="capture")`,
   including contradictory and rejected evidence rather than silently dropping
   it.

Raw ledger entries do not automatically appear in `tracelab_search`. When a
reviewed session should join the document corpus, promote it explicitly:

```json
{
  "name": "tracelab_evidence",
  "arguments": {
    "action": "promote",
    "project_id": "fbd3bd03-5ddc-49ee-8013-529163a99290",
    "session_key": "competitive-scan-2026-08-20",
    "target": "document"
  }
}
```

Document promotion is the bridge into TraceLab's normal ingestion, chunking,
embedding, Qdrant, and PEDR/preflight paths. Report-only promotion preserves a
durable report but does not add its content to document search.

Evidence required text and tags are trimmed and must remain nonblank. Working
note keys may contain ordinary encoded path characters (including `/`), but
the dot-only keys `.` and `..` are reserved because URL parsers treat them as
navigation segments.

---

## Migration from earlier names

If you previously used the un-published `@tracelab/mcp-server` name from
this repo, the only change is the package name on install. Tool names,
schemas, and behavior are unchanged. The flat `~24` tool surface from
sprint-40 was collapsed into 7 clusters in sprint-41 (T41.7), then extended
to 8 by the additive Evidence Ledger cluster in LEDGER-1;
calls to the legacy names return a friendly migration error pointing at
the cluster equivalent.

---

## Troubleshooting

**Login times out / `expired_token`** — the device code is valid for 10
minutes. Approve faster, or relaunch to mint a new code.

**`access_denied` immediately** — someone clicked **Deny** on the web
`/device` page (possibly you, possibly not). Relaunch and re-approve.

**`slow_down` errors in logs** — harmless. The server enforces a polling
interval; the client bumps its sleep by 5 seconds and continues.

**MCP tools not showing up in Claude Desktop** — check the MCP server logs
(Settings → Developer → MCP Server Logs in Claude Desktop). The first launch
must complete the device-code flow before tools register.

**Stale credential after server URL change** — if you switched
`TRACELAB_API_URL` between deployments, the client logs *"Stored credential
targets X, but TRACELAB_API_URL is Y. Re-running device login."* and
prompts again. Expected behavior.

**Stored credential leak / suspected compromise** — delete
`~/.config/tracelab-mcp/credentials.json` *and* revoke the key in TraceLab
at `/profile` → API Keys. Then relaunch to mint a fresh one.

**Want to skip the device flow on CI** — set `TRACELAB_API_KEY` (or
`TRACELAB_TOKEN`) in the environment. Both win over the stored credential
and skip the interactive flow.

---

## Development

Build:

```bash
cd packages/tracelab-mcp
npm install
npm run build
```

Watch mode:

```bash
npm run dev
```

Tests:

```bash
npm test           # watch mode
npm run test:run   # one-shot
```

Lint:

```bash
npm run lint
```

`packages/*/dist/` is `.gitignore`d at the repo root; a pre-commit hook
(`scripts/check_no_mcp_dist.sh`) blocks accidentally-staged build output.
`prepublishOnly` rebuilds from `src/` before every `npm publish`, so the
published tarball never contains stale builds.

---

## License

MIT. See [LICENSE](https://github.com/kneelinghorse/TraceLab/blob/main/LICENSE).

## Links

- TraceLab — <https://github.com/kneelinghorse/TraceLab>
- Issue tracker — <https://github.com/kneelinghorse/TraceLab/issues>
- Changelog — [CHANGELOG.md](./CHANGELOG.md)
- Model Context Protocol spec — <https://modelcontextprotocol.io>
