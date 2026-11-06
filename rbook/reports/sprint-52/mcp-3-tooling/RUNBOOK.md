# MCP-3 publish runbook (@aquex/tracelab-mcp 1.2.0)

State when this was written: the release PR is merged on main and tagged
`tracelab-mcp-v1.2.0`; CI and both Railway deployments are recorded in
`cmos/reports/sprint-52/mcp-3-release.json`. The npm publish has NOT run
because `npm whoami` returns 401 on the build machine (decision #425
anticipated this).

## Derek: publish (about two minutes)

```bash
cd /Users/systemsystems/portfolio/TraceLab
git fetch origin && git checkout tracelab-mcp-v1.2.0   # the release merge commit
cd packages/tracelab-mcp
npm whoami                                             # must print your npm user
npm ci
npm publish                                            # prepublishOnly builds dist/
npm view @aquex/tracelab-mcp version                   # expect 1.2.0
git checkout main
```

Record the ISO timestamp `npm publish` finished (or read it from
`npm view @aquex/tracelab-mcp time --json`).

## Agent (next session): finish MCP-3

1. `MCP_VERSION=1.2.0 UI_OUT=<scratch> node cmos/reports/sprint-52/mcp-3-tooling/npx-smoke.mjs`
   (fresh `npx -y @aquex/tracelab-mcp@1.2.0`, listTools vs manifest, one read per
   tool, canonical links must resolve 200). Never print the credential.
2. Collect the release merge facts already archived in `mcp-3-release.json`
   (runs, jobs, railway, public smoke, tables check) into the assembler's OUT dir,
   then run `build-receipt-mcp3.py` with `PUBLISHED_BY=Derek` and
   `PUBLISH_TIMESTAMP=<iso>`.
3. Open the receipt PR (mcp-3-validation.json + mcp-3-production-smoke.json),
   merge it, verify the carrier main push and both Railway deployments, then
   `cmos_mission_transition(action="complete", missionId="MCP-3", ...)`.
