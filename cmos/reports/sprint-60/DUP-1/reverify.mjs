// Recheck exact serving identities and read-only review after later accepted changes.
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
const commit = process.env.DUP1_SERVING_COMMIT;
assert.match(commit || '', /^[a-f0-9]{40}$/);
for (const url of [api + '/api/v1/health', 'https://tracelab.aquex.ai/api/version']) {
  const response = await fetch(url, { headers: { 'Cache-Control': 'no-cache' } });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).commit, commit);
}
async function read(route, payload) {
  const response = await fetch(api + '/api/v1' + route, { method: payload ? 'POST' : 'GET', headers: { 'X-API-Key': credentials.key, 'Content-Type': 'application/json' }, body: payload ? JSON.stringify(payload) : undefined });
  assert.equal(response.status, 200, route);
  return response.json();
}
async function snapshot() {
  const documents = [];
  for (const id of Object.values(baseline.documents)) {
    documents.push({ detail: await read(`/documents/${id}`), content: await read(`/documents/${id}/content`), graph: await read(`/graph/neighborhood?root_type=document&root_id=${id}&depth=1&per_relation_limit=50&max_nodes=150`) });
  }
  return { documents, collections: await read(`/collections?project_id=${baseline.project_id}&page_size=100`) };
}
const before = await snapshot();
const result = await read('/librarian/duplicates/scan', { project_id: baseline.project_id });
assert.deepEqual(result.candidates, baseline.candidates);
for (const pair of result.candidates) {
  const compared = await read('/librarian/duplicates/compare', { project_id: baseline.project_id, document_ids: pair.documents.map(doc => doc.id), candidate_id: pair.candidate_id });
  assert.deepEqual(compared.candidate, pair);
}
const after = await snapshot();
assert.deepEqual(after, before);
console.log(JSON.stringify({ verified_at: new Date().toISOString(), serving_commit: commit, baseline_commit: baseline.serving_commit, candidates: result.candidates.length, unchanged_snapshot_sha256: createHash('sha256').update(JSON.stringify(after)).digest('hex'), mutations: 0, model_calls: 0 }));
