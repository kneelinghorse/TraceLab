// Read-only deployed regression through the real MCP client and HTTP transport.
// Usage: node scripts/check_claim_display_contract.mjs [installed dist/index.js]
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(path.join(root, 'packages/tracelab-mcp/package.json'));
const { Client } = await import(require.resolve('@modelcontextprotocol/sdk/client/index.js'));
const { StdioClientTransport } = await import(require.resolve('@modelcontextprotocol/sdk/client/stdio.js'));
const fixtures = JSON.parse(await fs.readFile(path.join(root, 'frontend/tests/fixtures/evidence_display_claims.json'), 'utf8'));
const credentials = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
const api = 'https://api.tracelab.aquex.ai';
assert.equal(credentials.apiBaseUrl.replace(/\/$/, ''), api);
const entrypoint = path.resolve(process.argv[2] ?? path.join(root, 'packages/tracelab-mcp/dist/index.js'));
const transport = new StdioClientTransport({ command: process.execPath, args: [entrypoint], stderr: 'pipe',
  env: { ...process.env, TRACELAB_API_URL: api, TRACELAB_API_KEY: credentials.key, TRACELAB_TOKEN: '' } });
const client = new Client({ name: 's67-claims-read-only-contract', version: '1.0.0' });
const checks = [];
async function call(name, args) {
  const result = await client.callTool({ name, arguments: args });
  assert.ok(!result.isError, `${name}.${args.action} returned an error`);
  return JSON.parse(result.content[0].text);
}
try {
  await client.connect(transport);
  for (const fixture of fixtures.cases) {
    const detail = await call('tracelab_evidence', { action: 'get', entry_id: fixture.id });
    assert.equal(detail.entry.claim, fixture.claim, 'MCP ledger claims must stay exact');
    checks.push({ action: 'tracelab_evidence.get', entry_id: fixture.id, rawClaimUnchanged: true });
  }
  const fixture = fixtures.cases[9];
  const graph = await call('tracelab_project', { action: 'neighborhood', root_type: 'evidence', root_id: fixture.id });
  assert.equal(graph.root.title, fixture.display);
  assert.equal(graph.nodes.find(node => node.id === fixture.id).title, fixture.display);
  checks.push({ action: 'tracelab_project.neighborhood', readableRootAndNode: true });
  const navigation = await call('tracelab_search', { action: 'navigate', q: fixture.claim, entity_type: 'evidence', page_size: 50 });
  assert.equal(navigation.groups[0].items.find(item => item.id === fixture.id).title, fixture.display);
  checks.push({ action: 'tracelab_search.navigate', rawQueryMatched: true, readableTitle: true });
  console.log(JSON.stringify({ checkedAt: new Date().toISOString(), api, entrypoint, readOnly: true, checks }, null, 2));
} finally {
  await client.close();
}
