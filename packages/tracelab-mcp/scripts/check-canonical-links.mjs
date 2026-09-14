// Exercise the actual stdio entrypoint and HTTP verbs, including from an installed tarball.
import assert from 'node:assert/strict';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const root = fileURLToPath(new URL('../', import.meta.url));
const entrypoint = path.resolve(process.argv[2] ?? path.join(root, 'dist/index.js'));
const web = 'https://tracelab.aquex.ai';
const ids = Object.fromEntries(['project', 'document', 'mission', 'report', 'collection', 'evidence', 'chunk', 'note'].map((kind, i) => [kind, `00000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`]));
const archivedUrl = web + '/console/missions/ARCHIVED-1?q=original';
const markdown = `# Authored evidence\n\n[Original reference](${archivedUrl})\n`;
const references = [{ title: 'Original reference', url: archivedUrl }];
const pagination = { page: 1, page_size: 20, total: 1, pages: 1 };
const project = { id: ids.project, project_id: ids.project, name: 'Project', status: 'active' };
const document = { id: ids.document, name: 'Document', project_id: ids.project, file_type: 'md' };
const chunk = { chunk_id: ids.chunk, document_id: ids.document, content: markdown, score: 0.9, chunk_index: 0 };
const collection = { id: ids.collection, name: 'Collection', item_count: 1, items: [{ id: ids.chunk, chunk_id: ids.chunk, document_id: ids.document, chunk_content: markdown }] };
const report = { id: ids.report, title: 'Report', content: markdown, citations: references, sources: [] };
const mission = { id: ids.mission, mission_id: 'MIGRATION-1', title: 'Mission', objective: 'Preserve authored evidence', status: 'completed', project_id: ids.project, context: { references }, references, success_criteria: ['Canonical navigation'], result_report_id: ids.report, result_document_ids: [ids.document] };
const evidence = { id: ids.evidence, project_id: ids.project, claim: 'Sourced claim', source_url: archivedUrl, disposition: 'supporting' };
const note = { id: ids.note, project_id: ids.project, content: markdown };
const preview = { mission_id: mission.mission_id, mission_uuid: ids.mission, objectives: [], evidence_slots: [], acceptance_checks: [], deliverable_schemas: [], references };
const calls = [];
const routes = new Map();
const route = (method, pathname, payload) => routes.set(method + ' ' + pathname, payload);
route('POST', '/retrieval/search', { results: [chunk] });
route('GET', '/projects', { data: [project], pagination });
route('POST', '/projects', project);
route('PUT', `/projects/${ids.project}`, project);
route('GET', `/projects/${ids.project}/stats`, project);
route('GET', '/collections', { data: [collection], total: 1 });
route('GET', `/collections/${ids.collection}`, collection);
route('POST', '/collections', collection);
route('POST', `/collections/${ids.collection}/chunks`, collection.items[0]);
route('GET', `/collections/${ids.collection}/export`, markdown);
route('POST', '/synthesize', { content: markdown, citations: references, report_id: ids.report });
route('GET', '/reports', { items: [report], ...pagination });
route('GET', `/reports/${ids.report}`, report);
route('POST', '/reports', report);
route('GET', `/documents/${ids.document}`, document);
route('GET', `/documents/${ids.document}/chunks`, { data: [chunk], pagination });
route('POST', '/documents/upload', document);
route('GET', '/missions', { data: [mission], pagination });
route('GET', `/missions/${ids.mission}`, mission);
route('POST', '/missions', mission);
route('PATCH', `/missions/${ids.mission}`, mission);
route('POST', `/missions/${ids.mission}/submit`, { uuid: ids.mission, mission_id: mission.mission_id, status: 'queued', mode: 'worker' });
route('GET', `/missions/${ids.mission}/status`, mission);
route('GET', `/missions/${ids.mission}/contract-preview`, preview);
route('GET', '/evidence', { entries: [evidence], notes: [note], entry_total: 1, note_total: 1 });
route('GET', '/evidence/search', { entries: [evidence], total: 1 });
route('POST', '/evidence/capture', { entries: [evidence], count: 1 });
route('PUT', '/evidence/notes/working', note);
route('POST', '/evidence/promote', { project_id: ids.project, report_id: ids.report, document_id: ids.document, target: 'document' });

const server = http.createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const pathname = new URL(request.url, 'http://localhost').pathname.replace(/^\/api\/v1/, '');
  const key = request.method + ' ' + pathname;
  calls.push({ key, authenticated: request.headers['x-api-key'] === 'tl_contract_test', body: request.headers['content-type']?.includes('application/json') ? JSON.parse(Buffer.concat(chunks).toString() || 'null') : null });
  if (!routes.has(key)) { response.writeHead(405); response.end('Unexpected HTTP verb or route'); return; }
  const payload = routes.get(key);
  response.writeHead(200, { 'Content-Type': typeof payload === 'string' ? 'text/markdown' : 'application/json' });
  response.end(typeof payload === 'string' ? payload : JSON.stringify(payload));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const api = `http://127.0.0.1:${server.address().port}`;
const transport = new StdioClientTransport({ command: process.execPath, args: [entrypoint], env: { TRACELAB_API_URL: api, TRACELAB_FRONTEND_URL: web, TRACELAB_API_KEY: 'tl_contract_test' }, stderr: 'pipe' });
transport.stderr?.on('data', () => {});
const client = new Client({ name: 'canonical-link-contract', version: '1.0.0' });
const checks = [];
const url = (kind) => `${web}/${kind === 'evidence' ? kind : kind + 's'}/${ids[kind]}`;
async function check(tool, args, expectedCalls, links, verify) {
  const start = calls.length;
  const result = await client.callTool({ name: `tracelab_${tool}`, arguments: args });
  assert.ok(!result.isError, `${tool}/${args.action}: ${JSON.stringify(result)}`);
  assert.deepEqual(calls.slice(start).map(call => call.key), expectedCalls);
  assert.ok(calls.slice(start).every(call => call.authenticated), 'Every HTTP request uses the MCP API-key credential');
  const value = args.action === 'export' ? result.content[0].text : JSON.parse(result.content[0].text);
  for (const [field, target] of Object.entries(links)) {
    const actual = field.split('.').reduce((node, key) => node?.[key], value);
    assert.equal(actual, target, `${tool}/${args.action} canonical ${field}`);
  }
  verify?.(value);
  checks.push({ tool, action: args.action, links: Object.keys(links).length, http: expectedCalls });
}
try {
  await client.connect(transport);
  assert.equal((await client.listTools()).tools.length, 8);
  await check('search', { action: 'knowledge', query: 'provenance' }, ['POST /retrieval/search'], { 'results.0.document_url': url('document') });
  await check('project', { action: 'list' }, ['GET /projects'], { 'projects.0.url': url('project') });
  await check('project', { action: 'create', name: 'Project' }, ['POST /projects'], { 'project.url': url('project') });
  await check('project', { action: 'update', project_id: ids.project, name: 'Project' }, [`PUT /projects/${ids.project}`], { 'project.url': url('project') });
  await check('project', { action: 'stats', project_id: ids.project }, [`GET /projects/${ids.project}/stats`], { url: url('project') });
  await check('collection', { action: 'list' }, ['GET /collections'], { 'collections.0.url': url('collection') });
  await check('collection', { action: 'get', collection_id: ids.collection }, [`GET /collections/${ids.collection}`], { url: url('collection'), 'items.0.document_url': url('document') });
  await check('collection', { action: 'create', name: 'Collection' }, ['POST /collections'], { 'collection.url': url('collection') });
  await check('collection', { action: 'add', collection_id: ids.collection, chunk_id: ids.chunk }, [`POST /collections/${ids.collection}/chunks`], { collection_url: url('collection') });
  await check('collection', { action: 'synthesize', collection_id: ids.collection, save_as_report: true, report_title: 'Report' }, ['POST /synthesize'], { collection_url: url('collection'), report_url: url('report') }, value => assert.equal(value.synthesis, markdown));
  await check('collection', { action: 'export', collection_id: ids.collection }, [`GET /collections/${ids.collection}/export`], {}, value => assert.equal(value, markdown));
  await check('report', { action: 'list' }, ['GET /reports'], { 'reports.0.url': url('report') });
  await check('report', { action: 'get', report_id: ids.report }, [`GET /reports/${ids.report}`], { url: url('report') }, value => { assert.equal(value.content, markdown); assert.deepEqual(value.citations, references); });
  await check('report', { action: 'create', title: 'Report', collection_id: ids.collection }, ['POST /reports'], { 'report.url': url('report') });
  await check('report', { action: 'export', report_id: ids.report }, [`GET /reports/${ids.report}`], {}, value => assert.equal(value, markdown));
  await check('document', { action: 'get_content', document_id: ids.document }, [`GET /documents/${ids.document}`, `GET /documents/${ids.document}/chunks`], { url: url('document') }, value => assert.equal(value.content, markdown));
  await check('document', { action: 'upload', project_id: ids.project, name: 'Document', content: Buffer.from(markdown).toString('base64'), content_type: 'text/markdown' }, ['POST /documents/upload'], { 'document.url': url('document') });
  await check('mission', { action: 'list' }, ['GET /missions'], { 'missions.0.url': url('mission') }, value => assert.deepEqual(value.missions[0].references, references));
  await check('mission', { action: 'get', mission_id: ids.mission }, [`GET /missions/${ids.mission}`], { url: url('mission') }, value => { assert.deepEqual(value.references, references); assert.deepEqual(value.context, mission.context); });
  await check('mission', { action: 'create', mission_id: 'MIGRATION-1', title: 'Mission', objective: mission.objective, success_criteria: mission.success_criteria, project_id: ids.project, references }, ['POST /missions'], { 'mission.url': url('mission') }, () => assert.deepEqual(calls.at(-1).body.references, references));
  await check('mission', { action: 'update', mission_id: ids.mission, title: 'Mission', references }, [`PATCH /missions/${ids.mission}`], { 'mission.url': url('mission') }, () => assert.deepEqual(calls.at(-1).body.references, references));
  await check('mission_execution', { action: 'submit', mission_id: ids.mission }, [`POST /missions/${ids.mission}/submit`], { url: url('mission') });
  await check('mission_execution', { action: 'status', mission_id: ids.mission }, [`GET /missions/${ids.mission}/status`], { url: url('mission') });
  await check('mission_execution', { action: 'preview', mission_id: ids.mission }, [`GET /missions/${ids.mission}/contract-preview`], { 'preview.url': url('mission') }, value => assert.deepEqual(value.full, preview));
  await check('evidence', { action: 'list', project_id: ids.project }, ['GET /evidence'], { 'entries.0.url': url('evidence'), 'notes.0.project_url': url('project') }, value => assert.equal(value.entries[0].source_url, archivedUrl));
  await check('evidence', { action: 'search', project_id: ids.project, q: 'claim' }, ['GET /evidence/search'], { 'entries.0.url': url('evidence') }, value => assert.equal(value.entries[0].source_url, archivedUrl));
  await check('evidence', { action: 'capture', project_id: ids.project, session_key: 'test', entries: [{ claim: 'Claim', source_url: archivedUrl, disposition: 'supporting' }] }, ['POST /evidence/capture'], { 'entries.0.url': url('evidence') });
  await check('evidence', { action: 'note', project_id: ids.project, session_key: 'test', note_key: 'working', content: markdown }, ['PUT /evidence/notes/working'], { project_url: url('project') }, value => assert.equal(value.content, markdown));
  await check('evidence', { action: 'promote', project_id: ids.project, session_key: 'test', target: 'document' }, ['POST /evidence/promote'], { report_url: url('report'), document_url: url('document') });
  console.log(JSON.stringify({ passed: checks.length, generatedLinks: checks.reduce((sum, row) => sum + row.links, 0), httpRequests: calls.length, checks }, null, 2));
} finally {
  await client.close();
  await transport.close();
  await new Promise(resolve => server.close(resolve));
}
