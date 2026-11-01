// Read-only receipt verification after a documentation-only final merge.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const out = path.dirname(fileURLToPath(import.meta.url));
const receipt = JSON.parse(await fs.readFile(path.join(out, 'deployed-mcp.json'), 'utf8'));
const creds = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
const api = 'https://api.tracelab.aquex.ai';
const web = 'https://tracelab.aquex.ai';
const commit = process.env.REPORT1_SERVING_COMMIT;
assert.match(commit || '', /^[a-f0-9]{40}$/);
assert.equal(creds.apiBaseUrl.replace(/\/$/, ''), api);
for (const url of [api + '/api/v1/health', web + '/api/version']) {
  const response = await fetch(url, { headers: { 'Cache-Control': 'no-cache' } });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).commit, commit);
}
async function read(route) {
  const response = await fetch(api + '/api/v1' + route, { headers: { 'X-API-Key': creds.key } });
  assert.equal(response.status, 200);
  return response;
}
const report = await (await read('/reports/' + receipt.report_id)).json();
assert.equal(report.citation_status, 'validated');
assert.deepEqual(report.citations.map(({ excerpt, ...row }) => row), receipt.citations);
for (const citation of report.citations) {
  assert.equal((await fetch(web + citation.href)).status, 200);
}
for (const [format, baseline] of Object.entries(receipt.exports)) {
  const value = await (await read(`/reports/${receipt.report_id}/export?format=${format}`)).text();
  assert.equal(createHash('sha256').update(value).digest('hex'), baseline.sha256);
}
console.log(JSON.stringify({ verified_at: new Date().toISOString(), serving_commit: commit,
  baseline_commit: receipt.serving_commit, report_id: receipt.report_id,
  citations: report.citations.length, all_export_hashes_unchanged: true, mutations: 0 }));
