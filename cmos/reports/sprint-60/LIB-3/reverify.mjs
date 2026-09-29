// Verify the recorded acceptance after a documentation-only final merge; no writes or generation.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const out = path.dirname(fileURLToPath(import.meta.url));
const baseline = JSON.parse(await fs.readFile(path.join(out, 'deployed-acceptance.json'), 'utf8'));
const credentials = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
const api = 'https://api.tracelab.aquex.ai';
assert.equal(credentials.apiBaseUrl.replace(/\/$/, ''), api);
const commit = process.env.LIB3_SERVING_COMMIT;
assert.match(commit || '', /^[a-f0-9]{40}$/);
for (const url of [api + '/api/v1/health', 'https://tracelab.aquex.ai/api/version']) {
  const response = await fetch(url, { headers: { 'Cache-Control': 'no-cache' } });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).commit, commit);
}
for (const receipt of baseline.receipts) {
  const response = await fetch(api + '/api/v1/librarian/descriptions/' + receipt.project_id, { headers: { 'X-API-Key': credentials.key } });
  assert.equal(response.status, 200);
  const state = await response.json();
  assert.equal(createHash('sha256').update(JSON.stringify(state.description)).digest('hex'), receipt.original_sha256);
  assert.equal(state.provenance.proposal_id, receipt.proposal_id);
  assert.equal(state.revision, receipt.restored_revision);
  assert.equal(state.can_restore, false);
}
console.log(JSON.stringify({ verified_at: new Date().toISOString(), serving_commit: commit, baseline_commit: baseline.serving_commit, projects: baseline.receipts.length, original_descriptions_restored: true, mutations: 0, model_calls: 0 }));
