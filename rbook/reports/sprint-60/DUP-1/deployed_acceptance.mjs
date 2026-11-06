// Controlled fixture setup, then read-only duplicate review against the exact deployed build.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const out = path.dirname(fileURLToPath(import.meta.url));
const api = 'https://api.tracelab.aquex.ai';
const web = 'https://tracelab.aquex.ai';
const credentials = JSON.parse(await fs.readFile(path.join(os.homedir(), '.config/tracelab-mcp/credentials.json'), 'utf8'));
assert.equal(credentials.apiBaseUrl.replace(/\/$/, ''), api);
const commit = process.env.DUP1_SERVING_COMMIT;
assert.match(commit || '', /^[a-f0-9]{40}$/);
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export async function request(route, method = 'GET', body) {
  const multipart = body instanceof FormData;
  const response = await fetch(api + '/api/v1' + route, { method, headers: { 'X-API-Key': credentials.key, ...(multipart ? {} : { 'Content-Type': 'application/json' }) }, body: body ? multipart ? body : JSON.stringify(body) : undefined });
  const data = await response.json();
  assert.equal(response.ok, true, `${method} ${route}: ${response.status} ${typeof data.detail === 'string' ? data.detail : 'request failed'}`);
  return data;
}
for (const endpoint of [api + '/api/v1/health', web + '/api/version']) {
  const response = await fetch(endpoint, { headers: { 'Cache-Control': 'no-cache' } });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).commit, commit);
}
const me = await request('/auth/me');
assert.notEqual(me.role, 'service');
const fixture = JSON.parse(await fs.readFile(path.resolve(out, '../../../../tests/fixtures/librarian_duplicate_calibration.json'), 'utf8'));
const progressFile = path.join(out, 'deployed-progress.json');
let progress;
try { progress = JSON.parse(await fs.readFile(progressFile, 'utf8')); } catch { progress = { documents: {} }; }
const saveProgress = () => fs.writeFile(progressFile, JSON.stringify(progress, null, 2) + '\n');
if (!progress.project_id) {
  const project = await request('/projects', 'POST', { name: 'Sprint 60 Librarian acceptance — onboarding feedback', description: 'Controlled user-feedback fixtures for duplicate, collection and report acceptance.' });
  progress.project_id = project.id;
  await saveProgress();
}
const specifications = [
  ['original', 'user-feedback.txt', fixture.feedback],
  ['copy', 'user-feedback-copy.txt', fixture.feedback],
  ['edited', 'user-feedback-edit.txt', fixture.feedback.replace('confusing', 'unclear').replace('second session', 'later session')],
  ['distinct', 'user-feedback.txt', fixture.distinct],
  ['boilerplate_a', 'field-notes-a.txt', fixture.boilerplate + '\n\nResearchers could not find the upload button during onboarding and requested a clearer project header with a visible destination selector.'],
  ['boilerplate_b', 'field-notes-b.txt', fixture.boilerplate + '\n\nMechanics could not locate replacement door seals during inspections and requested an accurate warehouse inventory with regional availability and compatibility information.'],
];
for (const [key, name, content] of specifications) {
  if (!progress.documents[key]) {
    const body = new FormData(); body.append('file', new Blob([content], { type: 'text/plain' }), name);
    const doc = await request(`/documents/upload?project_id=${progress.project_id}&file_type=notes&source_type=interview`, 'POST', body);
    progress.documents[key] = { id: doc.id, processed: false };
    await saveProgress();
  }
  const stored = progress.documents[key];
  if (!stored.processed) {
    const processed = await request(`/documents/${stored.id}/process`, 'POST');
    assert.notEqual(processed.status, 'failed');
    const read = await request(`/documents/${stored.id}/content`);
    assert.equal(read.content.trim(), content.trim());
    stored.processed = true;
    await saveProgress();
  }
}
async function snapshot() {
  const documents = [];
  for (const { id } of Object.values(progress.documents)) {
    documents.push({ detail: await request(`/documents/${id}`), content: await request(`/documents/${id}/content`), graph: await request(`/graph/neighborhood?root_type=document&root_id=${id}&depth=1&per_relation_limit=50&max_nodes=150`) });
  }
  return { documents, project: await request(`/projects/${progress.project_id}`), collections: await request(`/collections?project_id=${progress.project_id}&page_size=100`) };
}
const before = await snapshot();
const result = await request('/librarian/duplicates/scan', 'POST', { project_id: progress.project_id });
assert.equal(result.coverage.readable_documents, 6);
assert.equal(result.coverage.examined_documents, 6);
assert.equal(result.coverage.limited, false);
const identities = pair => pair.documents.map(doc => doc.id).sort().join(',');
const expected = new Map([
  [[progress.documents.original.id, progress.documents.copy.id].sort().join(','), 'exact_text'],
  [[progress.documents.original.id, progress.documents.edited.id].sort().join(','), 'probable_overlap'],
  [[progress.documents.copy.id, progress.documents.edited.id].sort().join(','), 'probable_overlap'],
]);
assert.equal(result.candidates.length, expected.size);
for (const pair of result.candidates) {
  assert.equal(pair.kind, expected.get(identities(pair)));
  const comparison = await request('/librarian/duplicates/compare', 'POST', { project_id: progress.project_id, document_ids: pair.documents.map(doc => doc.id), candidate_id: pair.candidate_id });
  assert.deepEqual(comparison.candidate, pair);
  for (const document of comparison.documents) {
    assert.equal(document.content, before.documents.find(doc => doc.detail.id === document.id).content.content);
    assert.equal((await fetch(web + document.href)).status, 200);
  }
}
const repeated = await request('/librarian/duplicates/scan', 'POST', { project_id: progress.project_id });
assert.deepEqual(repeated.candidates, result.candidates);
const after = await snapshot();
assert.deepEqual(after, before);
await fs.writeFile(path.join(out, 'deployed-acceptance.json'), JSON.stringify({
  verified_at: new Date().toISOString(), serving_commit: commit, project_id: progress.project_id, caller_role: me.role,
  fixture_setup: 'Six named synthetic text uploads processed through the existing ingestion pipeline before the read-only snapshot.',
  documents: Object.fromEntries(Object.entries(progress.documents).map(([key, value]) => [key, value.id])),
  candidates: result.candidates, coverage: result.coverage, before_sha256: hash(before), after_sha256: hash(after),
  documents_chunks_relationships_collections_unchanged: true, model_calls_for_duplicate_review: 0,
  verification: 'Agent acceptance, not Derek personal acceptance',
}, null, 2) + '\n');
console.log(JSON.stringify({ serving_commit: commit, documents: 6, exact_pairs: 1, probable_pairs: 2, state_unchanged: true }));
