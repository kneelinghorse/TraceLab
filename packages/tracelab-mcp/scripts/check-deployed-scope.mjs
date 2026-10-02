// Read-only acceptance of the installed MCP against the deployed scope boundary.
// A local allowlist proxy forwards only these GETs; credentials stay in memory.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const [entrypoint, output] = process.argv.slice(2);
assert.ok(entrypoint && output, 'Usage: node check-deployed-scope.mjs <installed entrypoint> <receipt>');
const api = 'https://api.tracelab.aquex.ai';
const credentials = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
assert.equal(credentials.apiBaseUrl.replace(/\/$/, ''), api);
const missionId = '3f5c2641-7a47-45ed-a092-feebe9143ed1';
const missionPath = `/api/v1/missions/${missionId}`;
const allowed = new Set([missionPath, missionPath + '/contract-preview']);
const calls = [], blocked = [];
async function get(url) {
  const response = await fetch(api + url, { headers: { 'X-API-Key': credentials.key } });
  assert.ok(response.ok, `Read-only API returned ${response.status}`);
  return response.json();
}
const before = await get(missionPath);
const expectedPreview = await get(missionPath + '/contract-preview');
const proxy = http.createServer(async (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  if (request.method !== 'GET' || !allowed.has(url.pathname) || url.search) {
    blocked.push({ method: request.method, path: url.pathname });
    response.writeHead(405); response.end('Read-only acceptance allowlist'); return;
  }
  calls.push({ method: request.method, path: url.pathname });
  try { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(await get(url.pathname))); }
  catch { response.writeHead(502); response.end('Read-only upstream request failed'); }
});
await new Promise(resolve => proxy.listen(0, '127.0.0.1', resolve));
const transport = new StdioClientTransport({ command: process.execPath, args: [path.resolve(entrypoint)], env: { TRACELAB_API_URL: `http://127.0.0.1:${proxy.address().port}`, TRACELAB_API_KEY: 'tl_read_only_acceptance', TRACELAB_FRONTEND_URL: 'https://tracelab.aquex.ai' }, stderr: 'pipe' });
transport.stderr?.on('data', () => {});
const client = new Client({ name: 'scope-deployed-acceptance', version: '1.0.0' });
const sha = value => createHash('sha256').update(value).digest('hex');
try {
  await client.connect(transport);
  async function call(name, args) {
    const result = await client.callTool({ name, arguments: args });
    assert.ok(!result.isError, `${name}: call failed`);
    return JSON.parse(result.content[0].text);
  }
  const preview = await call('tracelab_mission_execution', { action: 'preview', mission_id: missionId });
  assert.deepEqual(preview.full, expectedPreview);
  for (const key of ['authored_scope', 'canonical_contract_id', 'canonical_contract_sha256', 'compiler_semantic_revision', 'compiler_source_revision']) assert.deepEqual(preview.preview[key], expectedPreview[key]);
  assert.equal(expectedPreview.contract_version, '1.2');
  assert.equal(expectedPreview.compiler_semantic_revision, 3);
  assert.equal(expectedPreview.compiler_source_revision, '79ef84842fb84259bafe59924b21fe2f5ad05d7d');
  assert.equal(expectedPreview.fidelity, 'structural_only');
  assert.equal(expectedPreview.authored_scope.max_words, 500);
  assert.equal(expectedPreview.authored_scope.max_sources, 2);
  const result = await call('tracelab_mission', { action: 'get', mission_id: missionId, include_execution_metadata: true });
  assert.equal(result.result_markdown, before.result_markdown);
  assert.deepEqual(result.result_protocol, before.result_protocol);
  assert.deepEqual(result.execution_metadata, before.execution_metadata);
  const after = await get(missionPath);
  for (const key of ['status', 'deepsearch_attempt_count', 'deepsearch_job_id', 'result_markdown', 'result_protocol', 'execution_metadata']) assert.deepEqual(after[key], before[key]);
  assert.deepEqual(blocked, []);
  const receipt = { accepted_at: new Date().toISOString(), installed_version: client.getServerVersion(), mission_id: missionId, calls, blocked, read_only: true, research_dispatched: false, preview: expectedPreview, retained_status: after.status, markdown_sha256: sha(after.result_markdown || ''), protocol_sha256: sha(JSON.stringify(after.result_protocol)), historical_audit_present: Boolean(after.execution_metadata?.final_outcome?.authored_scope_validation), worker_delivery_proven: false };
  await fs.writeFile(output, JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify({ passed: true, calls: calls.length, version: receipt.installed_version, historical_audit_present: receipt.historical_audit_present }));
} finally {
  await client.close(); await new Promise(resolve => proxy.close(resolve));
}
