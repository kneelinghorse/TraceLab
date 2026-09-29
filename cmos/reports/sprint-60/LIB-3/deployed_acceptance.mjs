// Named acceptance fixtures only; never print credentials or signed proposals.
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
const commit = process.env.LIB3_SERVING_COMMIT;
assert.match(commit || '', /^[a-f0-9]{40}$/);
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
async function request(route, method = 'GET', body) {
  const response = await fetch(api + '/api/v1' + route, { method, headers: { 'X-API-Key': credentials.key, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const data = await response.json();
  assert.equal(response.ok, true, `${method} ${route}: ${response.status} ${typeof data.detail === "string" ? data.detail : "request failed"}`);
  return data;
}
for (const endpoint of [api + '/api/v1/health', web + '/api/version']) {
  const response = await fetch(endpoint, { headers: { 'Cache-Control': 'no-cache' } });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).commit, commit);
}
const me = await request('/auth/me');
assert.notEqual(me.role, 'service');
const baseline = JSON.parse(await fs.readFile(path.join(out, '../REPORT-1/deployed-mcp.json'), 'utf8'));
const progressFile = path.join(out, 'deployed-progress.json');
let progress;
try { progress = JSON.parse(await fs.readFile(progressFile, 'utf8')); } catch { progress = {}; }
if (!progress.empty_project_id) {
  const project = await request('/projects', 'POST', { name: 'LIB-3 acceptance — planned onboarding study', description: 'A human planning brief for the LIB-3 acceptance fixture.' });
  progress.empty_project_id = project.id;
  await fs.writeFile(progressFile, JSON.stringify(progress, null, 2) + '\n');
}
const receipts = [];
for (const [basis, projectId, prompt] of [
  ['planning_brief', progress.empty_project_id, 'Describe a planned study of onboarding friction for researchers. This empty project has no findings yet. Use one concise paragraph about the intended audience and questions.'],
  ['corpus', baseline.project_id, 'Describe what the supplied research material in this project covers, in one concise paragraph. Cite each statement with its supplied numeric source marker. Do not claim complete coverage.'],
]) {
  const before = await request(`/librarian/descriptions/${projectId}`);
  const proposal = await request('/librarian/descriptions/draft', 'POST', { project_id: projectId, prompt });
  assert.equal(proposal.basis, basis);
  assert.ok(proposal.usage?.total_tokens > 0);
  const afterDraft = await request(`/librarian/descriptions/${projectId}`);
  assert.deepEqual(afterDraft, before);
  const payload = { project_id: projectId, proposal_token: proposal.proposal_token, description: proposal.description };
  const accepted = await request('/librarian/descriptions/accept', 'POST', payload);
  const sources = [];
  let restored;
  try {
  assert.equal(accepted.description, proposal.description);
  assert.equal(accepted.provenance.accepted_by, me.user_id);
  assert.equal(accepted.provenance.previous_value, before.description);
  assert.equal(accepted.provenance.current, true);
  assert.deepEqual(await request('/librarian/descriptions/accept', 'POST', payload), accepted);
  assert.deepEqual(await request(`/librarian/descriptions/${projectId}`), accepted);
  for (const citation of accepted.provenance.citations) {
    assert.equal(citation.available, true);
    const doc = await request(`/documents/${citation.document_id}`);
    assert.equal(doc.project_id, projectId);
    assert.equal((await fetch(web + citation.href)).status, 200);
    sources.push({ marker: citation.marker, document_id: citation.document_id, chunk_id: citation.chunk_id, href: citation.href });
  }
  if (basis === 'corpus') assert.ok(sources.length > 0);
  } finally {
  const restore = { project_id: projectId, proposal_id: accepted.provenance.proposal_id };
  restored = await request('/librarian/descriptions/restore', 'POST', restore);
  assert.equal(restored.description, before.description);
  assert.equal(restored.can_restore, false);
  assert.deepEqual(await request('/librarian/descriptions/restore', 'POST', restore), restored);
  }
  receipts.push({ basis, project_id: projectId, original_sha256: hash(before.description), accepted_sha256: hash(accepted.description), restored_sha256: hash(restored.description), proposal_id: accepted.provenance.proposal_id, model: proposal.model, usage: proposal.usage, coverage: proposal.coverage, source_links: sources, draft_no_write: true, accept_replay_no_write: true, restore_replay_no_write: true, accepted_revision: accepted.revision, restored_revision: restored.revision });
  await fs.writeFile(path.join(out, 'deployed-acceptance.json'), JSON.stringify({ verified_at: new Date().toISOString(), serving_commit: commit, receipts, verification: 'Agent acceptance, not Derek personal acceptance', original_descriptions_restored: true }, null, 2) + '\n');
}
console.log(JSON.stringify({ serving_commit: commit, projects_verified: receipts.length, source_links: receipts.reduce((n, r) => n + r.source_links.length, 0), original_descriptions_restored: true }));
