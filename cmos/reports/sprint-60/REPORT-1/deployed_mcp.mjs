// REPORT-1: one explicit acceptance report, generated through the published MCP.
// Credentials stay in process memory; receipts contain only artifact identities.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const out = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(out, '../../../..');
const require = createRequire(path.join(root, 'packages/tracelab-mcp/package.json'));
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
assert.match(process.env.REPORT1_SERVING_COMMIT || '', /^[a-f0-9]{40}$/, 'Exact serving commit is required');
const api = 'https://api.tracelab.aquex.ai';
const web = 'https://tracelab.aquex.ai';
const projectId = '0afcc588-e722-45bd-8320-f486601b877c';
const documentId = '04ffc800-85cf-4a49-bcec-a856644796a8';
const creds = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
assert.equal(creds.apiBaseUrl.replace(/\/$/, ''), api);
async function rest(route, asText = false) {
  const response = await fetch(api + '/api/v1' + route, { headers: { 'X-API-Key': creds.key } });
  assert.ok(response.ok, `REST ${route.split('?')[0]} returned ${response.status}`);
  return asText ? response.text() : response.json();
}
const project = await rest('/projects/' + projectId);
assert.equal(project.name, 'TraceLab Research');
const document = await rest('/documents/' + documentId);
assert.equal(document.project_id, projectId);
const chunks = (await rest(`/documents/${documentId}/chunks?page_size=3`)).data;
assert.equal(chunks.length, 3);
const fresh = await fs.mkdtemp(path.join(os.tmpdir(), 'report1-published-mcp-'));
const transport = new StdioClientTransport({ command: 'npx', args: ['-y', '@aquex/tracelab-mcp@2.1.0'], cwd: fresh,
  env: { PATH: process.env.PATH, HOME: process.env.HOME, TRACELAB_API_URL: api, TRACELAB_API_KEY: creds.key, TRACELAB_FRONTEND_URL: web }, stderr: 'pipe' });
const client = new Client({ name: 'report1-deployed-contract', version: '1.0.0' });
async function call(action, args) {
  const result = await client.callTool({ name: 'tracelab_report', arguments: { action, ...args } });
  assert.ok(!result.isError, 'MCP report action failed: ' + action);
  return action === 'export' ? result.content[0].text : JSON.parse(result.content[0].text);
}
let receipt;
try {
  await client.connect(transport);
  let reportId = process.env.REPORT1_REPORT_ID;
  let created;
  if (!reportId) {
    created = (await call('create', { title: 'REPORT-1 acceptance — durable source citations', project_id: projectId,
      chunk_ids: chunks.map(c => c.id), format: 'summary',
      prompt: 'Summarize only the supplied source excerpts in one short paragraph. Cite every sentence with the supplied numbered markers. Do not add headings, preamble, advice or outside facts.' })).report;
    reportId = created.id;
    // Persist identity immediately so a failed follow-up never causes an accidental second generation.
    await fs.writeFile(path.join(out, 'acceptance-report-id.txt'), reportId + '\n');
  }
  const reopened = await call('get', { report_id: reportId });
  const detail = await rest('/reports/' + reportId);
  assert.equal(detail.citation_status, 'validated');
  assert.ok(detail.citations.length > 0);
  assert.deepEqual(reopened.citations, detail.citations);
  if (created) assert.deepEqual(created.citations, reopened.citations);
  assert.equal(reopened.content, detail.content);
  const supplied = new Set(chunks.map(c => c.id));
  for (const citation of detail.citations) {
    assert.ok(citation.available && Number.isInteger(citation.marker));
    assert.ok(supplied.has(citation.chunk_id));
    assert.equal(citation.document_id, documentId);
    assert.ok(detail.content.includes(`[${citation.marker}]`));
    const response = await fetch(web + citation.href);
    assert.equal(response.status, 200);
    const live = await rest(`/documents/${citation.document_id}/chunks?page_size=100`);
    assert.ok(live.data.some(c => c.id === citation.chunk_id));
  }
  const exports = {};
  for (const format of ['md', 'json', 'txt']) {
    const output = await call('export', { report_id: reportId, format });
    assert.equal(output, await rest(`/reports/${reportId}/export?format=${format}`, true));
    if (format === 'json') assert.deepEqual(JSON.parse(output).citations, detail.citations);
    else for (const citation of detail.citations) assert.ok(output.includes(`[${citation.marker}] ${web}${citation.href}`));
    exports[format] = { bytes: Buffer.byteLength(output), sha256: createHash('sha256').update(output).digest('hex') };
  }
  receipt = { verified_at: new Date().toISOString(), serving_commit: process.env.REPORT1_SERVING_COMMIT,
    package_version: client.getServerVersion()?.version, project_id: projectId, document_id: documentId, report_id: reportId,
    report_url: `${web}/reports/${reportId}`, citations: detail.citations.map(({ excerpt, ...identity }) => identity), exports,
    checks: ['published MCP create/get preserve mapping', 'fresh REST read agrees', 'source identities are live and supplied', 'source destinations resolve', 'published MCP exports equal REST bytes'],
    no_package_source_change: true, personal_user_acceptance: false };
  await fs.writeFile(path.join(out, 'deployed-mcp.json'), JSON.stringify(receipt, null, 2) + '\n');
} finally { await client.close(); }
console.log(JSON.stringify(receipt));
